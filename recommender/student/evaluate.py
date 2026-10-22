"""Compute the course evaluation metrics for content, itemcf and ALS.

Training and inference use only ``evaluation/train.csv``; the held-out
``validation`` split provides relevance labels (rating >= 4.0). Every eligible
user gets one prediction row, exactly as the frozen protocol requires.

    python -m recommender.student.evaluate --partition validation

Outputs land under ``models/evaluation`` (git-ignored) plus the summary consumed
by the experiments API at ``backend/app/evaluation-results.json``.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from recommender.contracts import Algorithm, PROVIDERS, RecommendationRequest
from recommender.data import DATASET, SCHEMA, SPLIT, FrozenData, require, sha256
from recommender.evaluation import EvaluationResult, eligible_users, task
from recommender.validation import check_model, check_result

import recommender.student.evaluation_entry  # noqa: F401  registers evaluation providers

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models/evaluation"
ALGORITHMS = {"content": "content-v1", "itemcf": "itemcf-v1", "als": "als-v1"}
POSITIVE_THRESHOLD = 4.0
TOP_K = 10


def labels_for(data: FrozenData, partition: str, users: set[str], catalog: set[str]) -> dict[str, set[str]]:
    """Relevant targets = held-out rating >= 4.0 that is inside this user's candidates."""
    train_rated = {uid: set() for uid in users}
    for row in data.training():
        if row["userId"] in train_rated:
            train_rated[row["userId"]].add(row["movieId"])
    labels = {uid: set() for uid in users}
    for row in data.rows(f"evaluation/{partition}.csv", evaluation=True):
        uid = row["userId"]
        if uid not in labels:
            continue
        movie_id = row["movieId"]
        if float(row["rating"]) >= POSITIVE_THRESHOLD and movie_id in catalog and movie_id not in train_rated[uid]:
            labels[uid].add(movie_id)
    for uid in users:
        require(bool(labels[uid]), "固定有效用户缺少相关目标", "EVALUATION_INPUT_INVALID")
    return labels


def evaluate(data: FrozenData, partition: str, algorithm: str, users: set[str],
             labels: dict[str, set[str]], catalog: set[str]):
    model_path = MODELS / ALGORITHMS[algorithm] / "manifest.json"
    # Identity and artifact digests are checked once per model; every prediction
    # below is still validated against the RecommendationResult contract.
    model = check_model(model_path, "evaluation", algorithm, data)
    provider = PROVIDERS[Algorithm(algorithm)]
    predictions_dir = MODELS / "predictions"
    predictions_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = predictions_dir / f"{algorithm}-{partition}.jsonl"

    precision_sum = 0.0
    recall_sum = 0.0
    ordered = sorted(users, key=int)
    with predictions_path.open("w", encoding="utf-8") as stream:
        for count, uid in enumerate(ordered, 1):
            request = RecommendationRequest("ml", int(uid), TOP_K, "evaluation", DATASET, SPLIT)
            result = check_result(provider.recommend(request), request, Algorithm(algorithm),
                                  catalog, model.model_version)
            stream.write(json.dumps({"ml_user_id": uid, "result": result.model_dump(mode="json")},
                                    ensure_ascii=False) + "\n")
            hits = len({item.movie_id for item in result.items} & labels[uid])
            precision_sum += hits / TOP_K
            recall_sum += hits / len(labels[uid])
            if count % 1000 == 0:
                print(json.dumps({"partition": partition, "algorithm": algorithm, "progress": count}), flush=True)

    user_count = len(ordered)
    precision = round(precision_sum / user_count, 8)
    recall = round(recall_sum / user_count, 8)
    result = EvaluationResult(
        status="completed", runtime_mode="evaluation", algorithm=algorithm,
        model_version=model.model_version, task_sha256=task(data, partition)["task_sha256"],
        model_manifest_sha256=sha256(model_path),
        dataset_version=DATASET, split_version=SPLIT, schema_version=SCHEMA,
        partition=partition, user_count=user_count,
        precision_at_10=precision, recall_at_10=recall)
    results_dir = MODELS / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    result_path = results_dir / f"{algorithm}-{partition}.json"
    result_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    summary = {"algorithm": algorithm, "model_version": model.model_version,
               "model_manifest_sha256": result.model_manifest_sha256,
               "precision_at_10": precision, "recall_at_10": recall,
               "user_count": user_count, "predictions": str(predictions_path.relative_to(ROOT)),
               "result": str(result_path.relative_to(ROOT))}
    print(json.dumps({"status": "evaluated", "partition": partition, **summary}, ensure_ascii=False), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", default="validation",
                        choices=["validation", "test", "cold-k0", "cold-k1", "cold-k5", "cold-k10"])
    parser.add_argument("--algorithms", nargs="+", default=["content", "itemcf", "als"], choices=list(ALGORITHMS))
    args = parser.parse_args()

    data = FrozenData()
    users = eligible_users(data, args.partition)
    catalog = data.catalog()
    labels = labels_for(data, args.partition, users, catalog)
    summaries = [evaluate(data, args.partition, algorithm, users, labels, catalog)
                 for algorithm in args.algorithms]

    summary = {
        "status": "completed", "partition": args.partition, "runtime_mode": "evaluation",
        "dataset_version": DATASET, "split_version": SPLIT, "schema_version": SCHEMA,
        "task_sha256": task(data, args.partition)["task_sha256"],
        "user_count": len(users), "positive_threshold": POSITIVE_THRESHOLD, "top_k": TOP_K,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "algorithms": summaries,
    }
    # The student build ships only .py files, so the API imports a generated
    # module rather than opening a JSON sidecar at runtime.
    target = ROOT / "backend/app/evaluation_results.py"
    module = ('"""Generated by ``python -m recommender.student.evaluate``; do not edit by hand.\n\n'
              'Provenance: partition, task_sha256, model manifest digests and per-user counts\n'
              'come from the frozen protocol; metrics are macro averages over real predictions.\n'
              '"""\n\n'
              'SUMMARY = ' + json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    target.write_text(module, encoding="utf-8")
    print(json.dumps({"status": "completed", "summary": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
