"""Train Spark MLlib ALS for CineLab and export user/item factors.

Business mode fits ``business/history_ratings.csv`` (the API then serves pure
inference). Evaluation mode fits only ``evaluation/train.csv`` (the offline
evaluation entry then predicts validation users). Both write a factor artifact
plus a manifest whose identity matches the frozen package.

Run inside a Spark runtime (PySpark and Java are required):

    spark-submit recommender/student/build_als_models.py --mode business
    spark-submit recommender/student/build_als_models.py --mode evaluation
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
TRAIN_FILES = {"business": "business/history_ratings.csv", "evaluation": "evaluation/train.csv"}
OUTPUTS = {"business": ROOT / "models/business/als-v1",
           "evaluation": ROOT / "models/evaluation/als-v1"}
MODEL_VERSIONS = {"business": "als-spark-mllib-v1", "evaluation": "als-spark-mllib-eval-v1"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def catalog_ids() -> list[str]:
    with (PACKAGE / "training-catalog.csv").open(encoding="utf-8", newline="") as stream:
        return [row["movie_id"] for row in csv.DictReader(stream)]


def training_rows(mode: str, catalog: list[str]) -> tuple[list[tuple[int, int, float]], dict[str, int]]:
    index = {movie_id: position for position, movie_id in enumerate(catalog)}
    user_index: dict[str, int] = {}
    rows: list[tuple[int, int, float]] = []
    with (PACKAGE / TRAIN_FILES[mode]).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            movie_id = row["movieId"]
            if movie_id not in index:
                continue
            user = user_index.setdefault(row["userId"], len(user_index))
            rows.append((user, index[movie_id], float(row["rating"])))
    return rows, user_index


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["business", "evaluation"], required=True)
    parser.add_argument("--rank", type=int, default=20)
    parser.add_argument("--reg-param", type=float, default=0.1)
    parser.add_argument("--max-iter", type=int, default=15)
    parser.add_argument("--master", default="local[4]")
    args = parser.parse_args()

    from pyspark.ml.recommendation import ALS
    from pyspark.sql import SparkSession

    package = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    catalog = catalog_ids()
    rows, user_index = training_rows(args.mode, catalog)
    users = [None] * len(user_index)
    for user_id, position in user_index.items():
        users[position] = user_id

    spark = (SparkSession.builder.master(args.master).appName("cinelab-als-" + args.mode)
             .config("spark.ui.enabled", "false").config("spark.sql.shuffle.partitions", "8")
             .config("spark.driver.memory", "4g").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    frame = spark.createDataFrame(rows, ["userId", "itemId", "rating"])
    trainer = ALS(rank=args.rank, regParam=args.reg_param, maxIter=args.max_iter, seed=42,
                  userCol="userId", itemCol="itemId", ratingCol="rating",
                  coldStartStrategy="drop", implicitPrefs=False, nonnegative=False)
    model = trainer.fit(frame)

    user_factors = {int(row["id"]): [round(float(v), 6) for v in row["features"]]
                    for row in model.userFactors.collect()}
    item_factors = {int(row["id"]): [round(float(v), 6) for v in row["features"]]
                    for row in model.itemFactors.collect()}
    zero = [0.0] * args.rank
    artifact = {
        "schema_version": "als-factors-v1",
        "rank": args.rank,
        "reg_param": args.reg_param,
        "max_iter": args.max_iter,
        "trained_users": len(user_factors),
        "trained_items": len(item_factors),
        "user_ids": users,
        "user_factors": [user_factors.get(position, zero) for position in range(len(users))],
        "item_ids": catalog,
        "item_factors": [item_factors.get(position, zero) for position in range(len(catalog))],
    }
    directory = OUTPUTS[args.mode]
    directory.mkdir(parents=True, exist_ok=True)
    artifact_path = directory / "als-factors.json"
    artifact_path.write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")

    manifest = {
        "algorithm": "als",
        "model_version": MODEL_VERSIONS[args.mode],
        "runtime_mode": args.mode,
        "dataset_version": package["dataset_version"],
        "split_version": package["split_version"],
        "schema_version": package["schema_version"],
        "manifest_sha256": sha256(PACKAGE / "manifest.json"),
        "training_files": {TRAIN_FILES[args.mode]: package["files"][TRAIN_FILES[args.mode]]["sha256"]},
        "feature_files": {"training-catalog.csv": package["files"]["training-catalog.csv"]["sha256"]},
        "artifacts": {"als-factors.json": sha256(artifact_path)},
        "parameters": {"library": "spark-mllib-als", "rank": args.rank, "regParam": args.reg_param,
                       "maxIter": args.max_iter, "implicitPrefs": False, "coldStartStrategy": "drop",
                       "seed": 42, "rating_weight": "explicit", "score_decimals": 6},
        "tool_versions": {"spark": spark.version, "python": platform.python_version(),
                          "pyspark": __import__("pyspark").__version__},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    print(json.dumps({"status": "built", "mode": args.mode, "model_version": MODEL_VERSIONS[args.mode],
                      "rank": args.rank, "rows": len(rows), "users": len(users),
                      "items": len(catalog), "spark": spark.version,
                      "artifact_bytes": artifact_path.stat().st_size}))
    spark.stop()


if __name__ == "__main__":
    main()
