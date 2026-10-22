"""Content-based recommender built on real movie genres and business history.

The provider is pure inference: static genre statistics come from the sealed
model sidecar, while each viewer's taste profile is read from the existing
business feedback adapter. No evaluation file and no static recommendation list
is used.
"""
from __future__ import annotations

import json
import math
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

COSINE_WEIGHT = 0.75
PRIOR_WEIGHT = 0.25
SCORE_DECIMALS = 6


class ContentProvider:
    """Genre-profile provider; the API validates the sidecar before each call."""

    def __init__(self, model_manifest_path: str | Path, history_loader=None):
        self.model_manifest_path = Path(model_manifest_path)
        # Business instances read the live feedback table; the offline evaluation
        # entry injects a loader backed by evaluation/train.csv instead.
        self.history_loader = history_loader

    def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        require(self.history_loader is not None or request.runtime_mode == "business",
                "业务内容推荐不支持评价模式", "DATA_MODE_INVALID")
        model = _load_model(self.model_manifest_path)
        history = (self.history_loader or read_history)(request)

        profile: dict[str, float] = {}
        watched: set[str] = set()
        for feedback in history.ratings:
            watched.add(feedback.movie_id)
            item = model["items"].get(feedback.movie_id)
            if item is None:
                continue
            # Ratings below 2.5 push the profile away from a genre; strong
            # ratings accumulate taste in that genre.
            weight = float(feedback.rating) - 2.5
            for genre in item["genres"]:
                profile[genre] = profile.get(genre, 0.0) + weight * model["genre_idf"].get(genre, 1.0)

        profile_norm = math.sqrt(sum(value * value for value in profile.values()))
        items: list[RecommendationItem] = []
        if profile_norm > 0:
            scored: list[tuple[float, str]] = []
            for movie_id, item in model["items"].items():
                if movie_id in watched:
                    continue
                dot = sum(model["genre_idf"].get(genre, 1.0) * profile.get(genre, 0.0)
                          for genre in item["genres"])
                if dot <= 0:
                    continue
                cosine = dot / (profile_norm * item["norm"])
                prior = math.log1p(item["support"]) / model["max_log_support"]
                # Round first so that ordering and the emitted score agree,
                # which keeps the contract's same-score ordering rule.
                score = round(COSINE_WEIGHT * cosine + PRIOR_WEIGHT * prior, SCORE_DECIMALS)
                if score <= 0:
                    continue
                scored.append((score, movie_id))
            scored.sort(key=lambda pair: (-pair[0], int(pair[1])))
            for rank, (score, movie_id) in enumerate(scored[: request.limit], 1):
                items.append(RecommendationItem(
                    movie_id=movie_id,
                    rank=rank,
                    algorithm=Algorithm.content,
                    model_version=model["model_version"],
                    score=score,
                    recall_sources=["genre-profile"],
                ))

        return RecommendationResult(
            algorithm=Algorithm.content,
            model_version=model["model_version"],
            dataset_version=request.dataset_version,
            split_version=request.split_version,
            runtime_mode=request.runtime_mode,
            generated_at=datetime.now(timezone.utc),
            items=items,
        )


@lru_cache(maxsize=4)
def _load_model(manifest_path: Path) -> dict:
    manifest_path = manifest_path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContractError("MODEL_BINDING_INVALID", "内容模型清单缺失或格式非法") from None
    require(manifest.get("algorithm") == Algorithm.content.value and
            isinstance(manifest.get("model_version"), str), "内容模型清单标识不符", "MODEL_BINDING_INVALID")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, dict) and len(artifacts) == 1 and "item-features.json" in artifacts,
            "内容模型工件清单不符", "MODEL_BINDING_INVALID")
    artifact_path = (manifest_path.parent / "item-features.json").resolve()
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        genre_idf = {str(genre): float(value) for genre, value in artifact["genre_idf"].items()}
        max_log_support = float(artifact["max_log_support"])
        items = {}
        for movie_id, entry in artifact["items"].items():
            genres = tuple(str(genre) for genre in entry["genres"])
            norm = math.sqrt(sum(genre_idf.get(genre, 1.0) ** 2 for genre in genres))
            if genres and norm > 0:
                items[str(movie_id)] = {"genres": genres, "support": int(entry["support"]), "norm": norm}
    except (OSError, ValueError, KeyError, TypeError):
        raise ContractError("MODEL_BINDING_INVALID", "内容模型工件无法读取") from None
    require(bool(items) and max_log_support > 0, "内容模型工件为空", "MODEL_BINDING_INVALID")
    return {"model_version": manifest["model_version"], "genre_idf": genre_idf,
            "max_log_support": max_log_support, "items": items}
