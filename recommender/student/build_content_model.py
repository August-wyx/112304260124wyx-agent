"""Build the content-genre-v1 business model sidecar from the frozen package.

Run from the project root on the host (no database, no HTTP):

    python -m recommender.student.build_content_model

The builder only reads static feature files (movies.csv, training-catalog.csv),
writes models/business/content-v1/item-features.json and a manifest that binds
the business history snapshot. It never trains on evaluation splits.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
OUTPUT = ROOT / "models/business/content-v1"
MODEL_VERSION = "content-genre-v1"
ALGORITHM = "content"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    package_manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    movies = read_rows("movies.csv")
    catalog = {row["movie_id"]: int(row["train_support"]) for row in read_rows("training-catalog.csv")}
    if {row["movie_id"] for row in movies} != set(catalog):
        raise SystemExit("movies.csv and training-catalog.csv ids differ")

    items: dict[str, dict] = {}
    document_frequency: dict[str, int] = {}
    for row in movies:
        movie_id = row["movie_id"]
        genres = sorted({g.strip() for g in (row["genres"] or "").split("|") if g.strip()})
        if not genres:
            continue
        for genre in genres:
            document_frequency[genre] = document_frequency.get(genre, 0) + 1
        items[movie_id] = {"genres": genres, "support": catalog[movie_id]}

    total = len(items)
    # Smooth IDF keeps common genres (Comedy, Drama) meaningful while rare genres
    # (Documentary, Film-Noir) distinguish a viewer's profile.
    genre_idf = {genre: round(math.log((total + 1) / (count + 1)) + 1.0, 8)
                 for genre, count in sorted(document_frequency.items())}
    max_support = max(entry["support"] for entry in items.values())
    artifact = {
        "schema_version": MODEL_VERSION,
        "item_count": total,
        "genre_idf": genre_idf,
        "max_log_support": round(math.log1p(max_support), 8),
        "items": items,
    }

    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifact_path = OUTPUT / "item-features.json"
    artifact_path.write_text(json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                             encoding="utf-8")

    manifest = {
        "algorithm": ALGORITHM,
        "model_version": MODEL_VERSION,
        "runtime_mode": "business",
        "dataset_version": package_manifest["dataset_version"],
        "split_version": package_manifest["split_version"],
        "schema_version": package_manifest["schema_version"],
        "manifest_sha256": sha256(PACKAGE / "manifest.json"),
        "training_files": {
            "business/history_ratings.csv": package_manifest["files"]["business/history_ratings.csv"]["sha256"],
        },
        "feature_files": {
            "movies.csv": package_manifest["files"]["movies.csv"]["sha256"],
            "training-catalog.csv": package_manifest["files"]["training-catalog.csv"]["sha256"],
        },
        "artifacts": {"item-features.json": sha256(artifact_path)},
        "parameters": {
            "feature": "genres",
            "genre_weighting": "smoothed-idf",
            "rating_weight": "rating-2.5",
            "similarity": "cosine",
            "cosine_weight": 0.75,
            "popularity_prior_weight": 0.25,
            "exclude_rated_movies": True,
            "score_decimals": 6,
        },
        "tool_versions": {
            "python": platform.python_version(),
            "model-builder": MODEL_VERSION,
        },
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    print(json.dumps({"status": "built", "model_version": MODEL_VERSION, "items": total,
                      "artifact_bytes": artifact_path.stat().st_size,
                      "artifact_sha256": manifest["artifacts"]["item-features.json"]}))


if __name__ == "__main__":
    main()
