"""Item-based collaborative filtering over the real business rating history.

Similarity comes from a cosine item-item matrix fitted on the approved rating
snapshot. A viewer's score for an unseen movie is the sum of neighbour
similarities weighted by how far each of the viewer's own ratings sits above
the 2.5 midpoint, so only positive evidence propagates and rated movies never
appear again.
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
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = json.loads((manifest_path.parent / "item-neighbours.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "ItemCF 模型工件无法读取") from None
    require(manifest.get("algorithm") == "itemcf",
            "ItemCF 模型清单标识不符", "MODEL_BINDING_INVALID")
    try:
        neighbours = {str(key): tuple((str(pair[0]), float(pair[1])) for pair in value)
                      for key, value in artifact["items"].items()}
    except (KeyError, TypeError, ValueError, IndexError):
        raise ContractError("MODEL_BINDING_INVALID", "ItemCF 模型工件结构不符") from None
    require(bool(neighbours), "ItemCF 模型工件为空", "MODEL_BINDING_INVALID")
    return {"model_version": manifest["model_version"], "neighbours": neighbours}


class ItemCFProvider:
    def __init__(self, model_manifest_path: str | Path, history_loader=None):
        self.model_manifest_path = Path(model_manifest_path)
        # Business instances read the live feedback table; the offline evaluation
        # entry injects a loader backed by evaluation/train.csv instead.
        self.history_loader = history_loader

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(self.history_loader is not None or request.runtime_mode == "business",
                "ItemCF 不支持评价模式", "DATA_MODE_INVALID")
        model = _load_model(str(self.model_manifest_path))
        history = (self.history_loader or read_history)(request)
        watched = {feedback.movie_id for feedback in history.ratings}
        scores: dict[str, float] = {}
        for feedback in history.ratings:
            weight = float(feedback.rating) - RATING_MIDPOINT
            if weight <= 0:
                continue
            for neighbour, similarity in model["neighbours"].get(feedback.movie_id, ()):
                if neighbour in watched:
                    continue
                scores[neighbour] = scores.get(neighbour, 0.0) + similarity * weight
        ranked = sorted(((round(score, SCORE_DECIMALS), movie_id) for movie_id, score in scores.items()),
                        key=lambda entry: (-entry[0], int(entry[1])))[: request.limit]
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.itemcf,
                                    model_version=model["model_version"], score=score,
                                    recall_sources=["itemcf-neighbours"])
                 for rank, (score, movie_id) in enumerate(ranked, 1)]
        return RecommendationResult(algorithm=Algorithm.itemcf, model_version=model["model_version"],
                                    dataset_version=request.dataset_version,
                                    split_version=request.split_version,
                                    runtime_mode=request.runtime_mode,
                                    generated_at=datetime.now(timezone.utc), items=items)
