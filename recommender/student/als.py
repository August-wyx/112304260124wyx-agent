"""Spark MLlib ALS inference over exported latent factors.

Training happens offline in ``build_als_models.py``; this provider only loads
the sealed factor artifact and serves pure inference. A registered history user
is scored with their learned factor, while a business account without a learned
factor folds in from the items it rated (weighted by rating minus the 2.5
midpoint). Rated movies never appear in the output.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import (
    Algorithm,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResult,
)
from recommender.data import ContractError, require

RATING_MIDPOINT = 2.5
SCORE_DECIMALS = 6


@lru_cache(maxsize=4)
def _load_model(manifest_path: str) -> dict:
    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        artifact = json.loads((path.parent / "als-factors.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "ALS 模型工件无法读取") from None
    require(manifest.get("algorithm") == "als", "ALS 模型清单标识不符", "MODEL_BINDING_INVALID")
    try:
        user_ids = [str(value) for value in artifact["user_ids"]]
        item_ids = [str(value) for value in artifact["item_ids"]]
        user_factors = [[float(value) for value in row] for row in artifact["user_factors"]]
        item_factors = [[float(value) for value in row] for row in artifact["item_factors"]]
    except (KeyError, TypeError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "ALS 模型工件结构不符") from None
    rank = int(artifact["rank"])
    require(bool(user_ids) and bool(item_ids) and len(item_ids) == len(item_factors) and
            len(user_ids) == len(user_factors) and rank > 0 and
            all(len(row) == rank for row in user_factors) and
            all(len(row) == rank for row in item_factors),
            "ALS 因子矩阵形状不符", "MODEL_BINDING_INVALID")
    return {"model_version": manifest["model_version"], "rank": rank,
            "user_rows": {user_id: position for position, user_id in enumerate(user_ids)},
            "user_factors": user_factors, "item_ids": item_ids, "item_factors": item_factors,
            "item_rows": {movie_id: position for position, movie_id in enumerate(item_ids)}}


class ALSProvider:
    def __init__(self, model_manifest_path: str | Path, history_loader=None):
        self.model_manifest_path = Path(model_manifest_path)
        # Business instances read the live feedback table; the offline evaluation
        # entry injects a loader backed by evaluation/train.csv instead.
        self.history_loader = history_loader

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(self.history_loader is not None or request.runtime_mode == "business",
                "业务ALS不支持评价模式", "DATA_MODE_INVALID")
        model = _load_model(str(self.model_manifest_path))
        history = (self.history_loader or read_history)(request)
        watched = {feedback.movie_id for feedback in history.ratings}

        position = model["user_rows"].get(str(request.subject_id))
        sources = ["als-user-factors"]
        if position is None:
            # Fold-in for accounts registered in the app but absent from training.
            vector = [0.0] * model["rank"]
            weight_sum = 0.0
            for feedback in history.ratings:
                weight = float(feedback.rating) - RATING_MIDPOINT
                if weight <= 0:
                    continue
                item_position = model["item_rows"].get(feedback.movie_id)
                if item_position is None:
                    continue
                factors = model["item_factors"][item_position]
                for index in range(model["rank"]):
                    vector[index] += weight * factors[index]
                weight_sum += weight
            if weight_sum <= 0:
                return _result(request, model, [])
            vector = [value / weight_sum for value in vector]
            sources = ["als-fold-in"]
        else:
            vector = model["user_factors"][position]

        ranked = []
        for index, movie_id in enumerate(model["item_ids"]):
            if movie_id in watched:
                continue
            factors = model["item_factors"][index]
            score = 0.0
            for left, right in zip(factors, vector):
                score += left * right
            ranked.append((round(score, SCORE_DECIMALS), movie_id))
        ranked.sort(key=lambda entry: (-entry[0], int(entry[1])))
        return _result(request, model, ranked[: request.limit], sources)


def _result(request: RecommendationRequest, model: dict, ranked, sources=("als-user-factors",)) -> RecommendationResult:
    items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.als,
                                model_version=model["model_version"], score=score,
                                recall_sources=list(sources))
             for rank, (score, movie_id) in enumerate(ranked, 1)]
    return RecommendationResult(algorithm=Algorithm.als, model_version=model["model_version"],
                                dataset_version=request.dataset_version,
                                split_version=request.split_version,
                                runtime_mode=request.runtime_mode,
                                generated_at=datetime.now(timezone.utc), items=items)
