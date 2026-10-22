"""Cold-start recommender for accounts without any behaviour yet.

Strategy: a zero-history viewer falls back to the fitted popularity ranking.
If the viewer optionally picks interest genres, the same candidate pool is
re-ranked by a genre prior learned from real business ratings, so the fallback
and the interest-aware result both come from data rather than a static list.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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
from .popular import _popularity_score

INTEREST_WEIGHT = 0.75
POPULARITY_WEIGHT = 0.25
SCORE_DECIMALS = 6


@dataclass(frozen=True)
class ColdStartRequest(RecommendationRequest):
    """Business request extended with optional interest genres (bonus feature)."""

    interests: tuple[str, ...] = ()


@lru_cache(maxsize=4)
def _load_model(manifest_path: str) -> dict:
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = json.loads((manifest_path.parent / "cold-start-features.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "冷启动模型工件无法读取") from None
    require(manifest.get("algorithm") == "cold_start" and manifest.get("runtime_mode") == "business",
            "冷启动模型清单与业务模式不符", "MODEL_BINDING_INVALID")
    try:
        items = {str(key): {"genres": tuple(str(genre) for genre in value["genres"]),
                            "count": int(value["count"]), "mean": float(value["mean"])}
                 for key, value in artifact["items"].items()}
        genre_prior = {str(genre): float(value) for genre, value in artifact["genre_prior"].items()}
    except (KeyError, TypeError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "冷启动模型工件结构不符") from None
    require(bool(items) and bool(genre_prior), "冷启动模型工件为空", "MODEL_BINDING_INVALID")
    return {"model_version": manifest["model_version"], "items": items, "genre_prior": genre_prior,
            "global_mean": float(artifact["global_mean"]),
            "prior_count": float(artifact["bayes_prior_count"]), "max_count": int(artifact["max_count"])}


def normalise_interests(interests, model: dict) -> tuple[str, ...]:
    mapping = {genre.lower(): genre for genre in model["genre_prior"]}
    chosen: list[str] = []
    for raw in interests or ():
        genre = mapping.get(str(raw).strip().lower())
        if genre and genre not in chosen:
            chosen.append(genre)
    require(len(chosen) <= 8, "兴趣类型最多选择8个", "REQUEST_CONTEXT_INVALID")
    return tuple(chosen)


class ColdStartProvider:
    def __init__(self, model_manifest_path: str | Path):
        self.model_manifest_path = Path(model_manifest_path)

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(request.runtime_mode == "business", "冷启动推荐不支持评价模式", "DATA_MODE_INVALID")
        model = _load_model(str(self.model_manifest_path))
        history = read_history(request)
        watched = {feedback.movie_id for feedback in history.ratings}
        interests = normalise_interests(getattr(request, "interests", ()), model)
        ranked = []
        for movie_id, entry in model["items"].items():
            if movie_id in watched:
                continue
            popularity = _popularity_score(entry["count"], entry["mean"], model)
            if interests:
                matched = [model["genre_prior"][genre] for genre in entry["genres"] if genre in interests]
                affinity = sum(matched) / len(matched) if matched else 0.0
                score = round(INTEREST_WEIGHT * affinity + POPULARITY_WEIGHT * popularity, SCORE_DECIMALS)
            else:
                score = popularity
            ranked.append((score, movie_id))
        ranked.sort(key=lambda entry: (-entry[0], int(entry[1])))
        sources = ["interest-profile", "popular-fallback"] if interests else ["popular-fallback"]
        items = [RecommendationItem(movie_id=movie_id, rank=rank, algorithm=Algorithm.cold_start,
                                    model_version=model["model_version"], score=score, recall_sources=sources)
                 for rank, (score, movie_id) in enumerate(ranked[: request.limit], 1)]
        return RecommendationResult(algorithm=Algorithm.cold_start, model_version=model["model_version"],
                                    dataset_version=request.dataset_version,
                                    split_version=request.split_version,
                                    runtime_mode=request.runtime_mode,
                                    generated_at=datetime.now(timezone.utc), items=items)
