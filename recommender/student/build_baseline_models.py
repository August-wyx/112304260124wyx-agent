"""Build the popular / itemcf / cold-start business model sidecars.

Run from the project root on the host (no database, no HTTP):

    python -m recommender.student.build_baseline_models

Every artifact is fitted from the single approved business rating snapshot
``business/history_ratings.csv`` plus the static feature files. No evaluation
split, no hand-written list and no random score is used.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
from pathlib import Path

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
MODELS = ROOT / "models/business"
RATINGS = "business/history_ratings.csv"
NEIGHBOURS = 40
MIN_ITEM_SUPPORT = 5
BAYES_PRIOR_COUNT = 50.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_manifest(directory: Path, algorithm: str, model_version: str, package_manifest: dict,
                   feature_files: dict[str, str], artifacts: dict[str, str], parameters: dict) -> None:
    manifest = {
        "algorithm": algorithm,
        "model_version": model_version,
        "runtime_mode": "business",
        "dataset_version": package_manifest["dataset_version"],
        "split_version": package_manifest["split_version"],
        "schema_version": package_manifest["schema_version"],
        "manifest_sha256": sha256(PACKAGE / "manifest.json"),
        "training_files": {RATINGS: package_manifest["files"][RATINGS]["sha256"]},
        "feature_files": feature_files,
        "artifacts": artifacts,
        "parameters": parameters,
        "tool_versions": {"python": platform.python_version(), "model-builder": model_version},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")


def load_ratings(item_index: dict[str, int], user_index: dict[str, int]):
    """Parse the approved snapshot once into aligned numpy arrays."""
    user_ids: set[str] = set()
    rows: list[tuple[str, str, float]] = []
    with (PACKAGE / RATINGS).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            movie_id = row["movieId"]
            if movie_id not in item_index:
                continue
            user_ids.add(row["userId"])
            rows.append((row["userId"], movie_id, float(row["rating"])))
    for position, user_id in enumerate(sorted(user_ids)):
        user_index[user_id] = position
    users = np.fromiter((user_index[u] for u, _, _ in rows), dtype=np.int32, count=len(rows))
    items = np.fromiter((item_index[m] for _, m, _ in rows), dtype=np.int32, count=len(rows))
    values = np.fromiter((r for _, _, r in rows), dtype=np.float32, count=len(rows))
    return users, items, values


def build_popular(package_manifest: dict, catalog_ids: list[str], users, items, values, global_mean: float):
    counts = np.bincount(items, minlength=len(catalog_ids)).astype(np.int64)
    sums = np.bincount(items, weights=values, minlength=len(catalog_ids))
    max_count = int(counts.max())
    entries = {}
    for index, movie_id in enumerate(catalog_ids):
        count = int(counts[index])
        if count == 0:
            continue
        mean = round(float(sums[index] / count), 8)
        entries[movie_id] = {"count": count, "mean": mean}
    artifact = {
        "schema_version": "popular-stats-v1",
        "global_mean": round(global_mean, 8),
        "bayes_prior_count": BAYES_PRIOR_COUNT,
        "max_count": max_count,
        "items": entries,
    }
    directory = MODELS / "popular-v1"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "item-stats.json"
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    write_manifest(directory, "popular", "popular-stats-v1", package_manifest,
                   {"training-catalog.csv": package_manifest["files"]["training-catalog.csv"]["sha256"]},
                   {"item-stats.json": sha256(path)},
                   {"signal": ["rating-count", "rating-mean"], "bayes_prior_count": BAYES_PRIOR_COUNT,
                    "quality_weight": 0.7, "volume_weight": 0.3, "score_decimals": 6})
    print(json.dumps({"status": "built", "model_version": "popular-stats-v1",
                      "items": len(entries), "artifact_bytes": path.stat().st_size}))


def build_cold_start(package_manifest: dict, movies: list[dict[str, str]], catalog_ids: list[str],
                     users, items, values, global_mean: float):
    counts = np.bincount(items, minlength=len(catalog_ids)).astype(np.int64)
    sums = np.bincount(items, weights=values, minlength=len(catalog_ids))
    genre_sums: dict[str, float] = {}
    genre_counts: dict[str, int] = {}
    item_genres: dict[str, list[str]] = {}
    for row in movies:
        movie_id = row["movie_id"]
        genres = sorted({g.strip() for g in (row["genres"] or "").split("|") if g.strip()})
        item_genres[movie_id] = genres
    index_of = {movie_id: index for index, movie_id in enumerate(catalog_ids)}
    for user, item, rating in zip(users, items, values):
        for genre in item_genres[catalog_ids[item]]:
            genre_sums[genre] = genre_sums.get(genre, 0.0) + float(rating)
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
    genre_prior = {genre: round(((genre_sums[genre] / genre_counts[genre]) - 0.5) / 4.5, 8)
                   for genre in sorted(genre_sums)}
    entries = {}
    for movie_id in catalog_ids:
        index = index_of[movie_id]
        count = int(counts[index])
        if count == 0:
            continue
        entries[movie_id] = {"genres": item_genres[movie_id], "count": count,
                             "mean": round(float(sums[index] / count), 8)}
    artifact = {
        "schema_version": "cold-start-v1",
        "global_mean": round(global_mean, 8),
        "bayes_prior_count": BAYES_PRIOR_COUNT,
        "max_count": int(counts.max()),
        "genre_prior": genre_prior,
        "items": entries,
    }
    directory = MODELS / "cold-start-v1"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "cold-start-features.json"
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    write_manifest(directory, "cold_start", "cold-start-genre-v1", package_manifest,
                   {"movies.csv": package_manifest["files"]["movies.csv"]["sha256"],
                    "training-catalog.csv": package_manifest["files"]["training-catalog.csv"]["sha256"]},
                   {"cold-start-features.json": sha256(path)},
                   {"fallback": "popularity", "interest_feature": "genres",
                    "interest_weight": 0.7, "popularity_weight": 0.3, "score_decimals": 6})
    print(json.dumps({"status": "built", "model_version": "cold-start-genre-v1",
                      "items": len(entries), "artifact_bytes": path.stat().st_size}))


def build_itemcf(package_manifest: dict, catalog_ids: list[str], users, items, values):
    item_count = len(catalog_ids)
    supports = np.bincount(items, minlength=item_count)
    matrix = sparse.csr_matrix((values, (users, items)), shape=(int(users.max()) + 1, item_count),
                               dtype=np.float32)
    norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=0)).ravel())
    norms[norms == 0] = 1.0
    normalizer = sparse.diags((1.0 / norms).astype(np.float32))
    normalized = (matrix @ normalizer).tocsr()
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
            neighbours[catalog_ids[index]] = [[catalog_ids[n], score] for n, score in ranked]
    artifact = {
        "schema_version": "itemcf-v1",
        "neighbour_count": NEIGHBOURS,
        "min_item_support": MIN_ITEM_SUPPORT,
        "item_count": item_count,
        "rated_items": int((supports > 0).sum()),
        "items": neighbours,
    }
    directory = MODELS / "itemcf-v1"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "item-neighbours.json"
    path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    write_manifest(directory, "itemcf", "itemcf-cosine-v1", package_manifest,
                   {"training-catalog.csv": package_manifest["files"]["training-catalog.csv"]["sha256"]},
                   {"item-neighbours.json": sha256(path)},
                   {"similarity": "cosine", "neighbour_count": NEIGHBOURS,
                    "min_item_support": MIN_ITEM_SUPPORT, "rating_weight": "rating-2.5",
                    "exclude_rated_movies": True, "score_decimals": 6})
    print(json.dumps({"status": "built", "model_version": "itemcf-cosine-v1",
                      "items": len(neighbours), "artifact_bytes": path.stat().st_size}))


def main() -> None:
    package_manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    movies = read_rows("movies.csv")
    catalog_ids = [row["movie_id"] for row in read_rows("training-catalog.csv")]
    item_index = {movie_id: index for index, movie_id in enumerate(catalog_ids)}
    user_index: dict[str, int] = {}
    users, items, values = load_ratings(item_index, user_index)
    global_mean = float(values.mean())
    build_popular(package_manifest, catalog_ids, users, items, values, global_mean)
    build_cold_start(package_manifest, movies, catalog_ids, users, items, values, global_mean)
    build_itemcf(package_manifest, catalog_ids, users, items, values)


if __name__ == "__main__":
    main()
