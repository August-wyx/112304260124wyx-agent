"""Popularity baseline fitted on the approved business rating snapshot.

Popularity is a real statistic, not a hand-written list: every candidate score
combines the Bayesian average rating (quality) with the number of ratings
(volume). The provider is pure inference over the sealed sidecar.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from recommender.contracts import (
    Algorithm,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResult,
)
from recommender.data import ContractError, require

QUALITY_WEIGHT = 0.7
VOLUME_WEIGHT = 0.3
SCORE_DECIMALS = 6


@lru_cache(maxsize=4)
def _load_model(manifest_path: str) -> dict:
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = json.loads((manifest_path.parent / "item-stats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "热门模型工件无法读取") from None
    require(manifest.get("algorithm") == "popular" and manifest.get("runtime_mode") == "business",
            "热门模型清单与业务模式不符", "MODEL_BINDING_INVALID")
    try:
        items = {str(key): (int(value["count"]), float(value["mean"]))
                 for key, value in artifact["items"].items()}
        global_mean = float(artifact["global_mean"])
        prior_count = float(artifact["bayes_prior_count"])
        max_count = int(artifact["max_count"])
    except (KeyError, TypeError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "热门模型工件结构不符") from None
    require(bool(items) and max_count > 0 and prior_count > 0, "热门模型工件为空", "MODEL_BINDING_INVALID")
    return {"model_version": manifest["model_version"], "items": items, "global_mean": global_mean,
            "prior_count": prior_count, "max_count": max_count}


def _popularity_score(count: int, mean: float, model: dict) -> float:
    bayes = (mean * count + model["global_mean"] * model["prior_count"]) / (count + model["prior_count"])
    quality = bayes / 5.0
    volume = math.log1p(count) / math.log1p(model["max_count"])
    return round(QUALITY_WEIGHT * quality + VOLUME_WEIGHT * volume, SCORE_DECIMALS)


class PopularProvider:
    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business", "业务热门推荐不支持评价模式", "DATA_MODE_INVALID")
        model = _load_model(str(self.model_manifest_path))
        ranked = sorted(((_popularity_score(count, mean, model), movie_id)
                         for movie_id, (count, mean) in model["items"].items()),
                        key=lambda entry: (-entry[0], int(entry[1])))[: request.limit]
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.popular,
                                    model_version=model["model_version"], score=score,
                                    recall_sources=["rating-volume", "rating-quality"])
                 for rank, (score, movie_id) in enumerate(ranked, 1)]
        return RecommendationResult(algorithm=Algorithm.popular, model_version=model["model_version"],
                                    dataset_version=request.dataset_version,
                                    split_version=request.split_version,
                                    runtime_mode=request.runtime_mode,
                                    generated_at=datetime.now(timezone.utc), items=items)
