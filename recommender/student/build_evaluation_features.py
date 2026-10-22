"""Build evaluation-mode content and ItemCF artifacts from the frozen train split.

The evaluation entry may only fit on ``evaluation/train.csv``. This builder
validates every input through :class:`FrozenData`, fits the same genre profile
and cosine item-item models used in business mode, then writes manifests whose
``runtime_mode`` is ``evaluation``:

    python -m recommender.student.build_evaluation_features
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
from pathlib import Path

import numpy as np
from scipy import sparse

from recommender.data import FrozenData

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
OUTPUT = ROOT / "models/evaluation"
TRAIN_FILE = "evaluation/train.csv"
NEIGHBOURS = 40
MIN_ITEM_SUPPORT = 5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(directory: Path, algorithm: str, model_version: str, package: dict,
                   artifacts: dict, parameters: dict) -> None:
    manifest = {
        "algorithm": algorithm,
        "model_version": model_version,
        "runtime_mode": "evaluation",
        "dataset_version": package["dataset_version"],
        "split_version": package["split_version"],
        "schema_version": package["schema_version"],
        "manifest_sha256": sha256(PACKAGE / "manifest.json"),
        "training_files": {TRAIN_FILE: package["files"][TRAIN_FILE]["sha256"]},
        "feature_files": {
            "movies.csv": package["files"]["movies.csv"]["sha256"],
            "training-catalog.csv": package["files"]["training-catalog.csv"]["sha256"],
        },
        "artifacts": artifacts,
        "parameters": parameters,
        "tool_versions": {"python": platform.python_version(), "model-builder": model_version},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")


def catalog_ids(data: FrozenData) -> list[str]:
    return [row["movie_id"] for row in data.rows("training-catalog.csv")]


def train_arrays(data: FrozenData, catalog: list[str]):
    index = {movie_id: position for position, movie_id in enumerate(catalog)}
    users: dict[str, int] = {}
    rows = []
    for row in data.training():
        movie_id = row["movieId"]
        if movie_id not in index:
            continue
        users.setdefault(row["userId"], len(users))
        rows.append((users[row["userId"]], index[movie_id], float(row["rating"])))
    arrays = (
        np.fromiter((row[0] for row in rows), dtype=np.int32, count=len(rows)),
        np.fromiter((row[1] for row in rows), dtype=np.int32, count=len(rows)),
        np.fromiter((row[2] for row in rows), dtype=np.float32, count=len(rows)),
    )
    return arrays, len(users)


def build_content(data: FrozenData, catalog: list[str], arrays) -> None:
    users, items, _ = arrays
    supports = np.bincount(items, minlength=len(catalog))
    movies = {row["movie_id"]: row for row in data.rows("movies.csv")}
    index_of = {movie_id: position for position, movie_id in enumerate(catalog)}
    entries: dict[str, dict] = {}
    document_frequency: dict[str, int] = {}
    for movie_id in catalog:
        genres = sorted({g.strip() for g in (movies[movie_id]["genres"] or "").split("|") if g.strip()})
        if not genres:
            continue
        for genre in genres:
            document_frequency[genre] = document_frequency.get(genre, 0) + 1
        entries[movie_id] = {"genres": genres, "support": int(supports[index_of[movie_id]])}
    total = len(entries)
    genre_idf = {genre: round(math.log((total + 1) / (count + 1)) + 1.0, 8)
                 for genre, count in sorted(document_frequency.items())}
    max_support = max(entry["support"] for entry in entries.values())
    artifact = {
        "schema_version": "content-genre-eval-v1",
        "item_count": total,
        "genre_idf": genre_idf,
        "max_log_support": round(math.log1p(max_support), 8),
        "items": entries,
    }
    directory = OUTPUT / "content-v1"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "item-features.json"
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                    encoding="utf-8")
    write_manifest(directory, "content", "content-genre-eval-v1", data.manifest,
                   {"item-features.json": sha256(path)},
                   {"feature": "genres", "genre_weighting": "smoothed-idf",
                    "rating_weight": "rating-2.5", "similarity": "cosine",
                    "cosine_weight": 0.75, "popularity_prior_weight": 0.25,
                    "exclude_rated_movies": True, "score_decimals": 6})
    print(json.dumps({"status": "built", "model_version": "content-genre-eval-v1",
                      "items": total, "artifact_bytes": path.stat().st_size,
                      "train_users": int(users.max()) + 1}))


def build_itemcf(data: FrozenData, catalog: list[str], arrays) -> None:
    users, items, values = arrays
    item_count = len(catalog)
    supports = np.bincount(items, minlength=item_count)
    matrix = sparse.csr_matrix((values, (users, items)), shape=(int(users.max()) + 1, item_count),
                               dtype=np.float32)
    norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=0)).ravel())
    norms[norms == 0] = 1.0
    normalized = (matrix @ sparse.diags((1.0 / norms).astype(np.float32))).tocsr()
    neighbours: dict[str, list] = {}
    block = 512
    for start in range(0, item_count, block):
        stop = min(start + block, item_count)
        similarity = np.asarray((normalized[:, start:stop].T @ normalized).todense(), dtype=np.float32)
        for offset in range(stop - start):
            index = start + offset
            if supports[index] < MIN_ITEM_SUPPORT:
                continue
            row = similarity[offset]
            row[index] = 0.0
            candidates = np.flatnonzero(row > 1e-6)
            if not candidates.size:
                continue
            if candidates.size > NEIGHBOURS:
                cutoff = np.argpartition(row[candidates], -NEIGHBOURS)[-NEIGHBOURS:]
                candidates = candidates[cutoff]
            ranked = sorted(((int(n), round(float(row[n]), 8)) for n in candidates),
                            key=lambda entry: (-entry[1], entry[0]))[:NEIGHBOURS]
            neighbours[catalog[index]] = [[catalog[n], score] for n, score in ranked]
    artifact = {
        "schema_version": "itemcf-eval-v1",
        "neighbour_count": NEIGHBOURS,
        "min_item_support": MIN_ITEM_SUPPORT,
        "item_count": item_count,
        "rated_items": int((supports > 0).sum()),
        "items": neighbours,
    }
    directory = OUTPUT / "itemcf-v1"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "item-neighbours.json"
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    write_manifest(directory, "itemcf", "itemcf-cosine-eval-v1", data.manifest,
                   {"item-neighbours.json": sha256(path)},
                   {"similarity": "cosine", "neighbour_count": NEIGHBOURS,
                    "min_item_support": MIN_ITEM_SUPPORT, "rating_weight": "rating-2.5",
                    "exclude_rated_movies": True, "score_decimals": 6})
    print(json.dumps({"status": "built", "model_version": "itemcf-cosine-eval-v1",
                      "items": len(neighbours), "artifact_bytes": path.stat().st_size}))


def main() -> None:
    data = FrozenData()
    catalog = catalog_ids(data)
    arrays, user_count = train_arrays(data, catalog)
    print(json.dumps({"status": "loaded", "train_rows": len(arrays[0]), "train_users": user_count,
                      "catalog": len(catalog)}))
    build_content(data, catalog, arrays)
    build_itemcf(data, catalog, arrays)


if __name__ == "__main__":
    main()
