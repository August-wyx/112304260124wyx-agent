"""Offline evaluation entry: providers fitted only on ``evaluation/train.csv``.

The evaluation process is isolated from the business API. Importing this module
swaps the three evaluation providers into the shared ``PROVIDERS`` registry, so
``python -m recommender.check selfcheck --module recommender.student.evaluation_entry
--mode evaluation`` drives the same contract entry as the API does in business mode.

The API never imports this module; it keeps the business providers only.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from recommender.business import Feedback, UserHistory
from recommender.contracts import Algorithm, PROVIDERS
from recommender.data import FrozenData
from recommender.student.als import ALSProvider
from recommender.student.content import ContentProvider
from recommender.student.itemcf import ItemCFProvider

MODELS = Path("models/evaluation")


@lru_cache(maxsize=1)
def _training_histories() -> dict[int, tuple[Feedback, ...]]:
    """Group the frozen training split by user once; no other split is read."""
    grouped: dict[int, list[Feedback]] = {}
    for row in FrozenData().training():
        grouped.setdefault(int(row["userId"]), []).append(
            Feedback(row["movieId"], f"{float(row['rating']):.1f}"))
    return {user_id: tuple(items) for user_id, items in grouped.items()}


def training_history(request) -> UserHistory:
    ratings = _training_histories().get(request.subject_id, ())
    return UserHistory(f"{request.subject_kind}:{request.subject_id}", ratings, ())


PROVIDERS[Algorithm.content] = ContentProvider(
    MODELS / "content-v1/manifest.json", history_loader=training_history)
PROVIDERS[Algorithm.itemcf] = ItemCFProvider(
    MODELS / "itemcf-v1/manifest.json", history_loader=training_history)
PROVIDERS[Algorithm.als] = ALSProvider(
    MODELS / "als-v1/manifest.json", history_loader=training_history)
