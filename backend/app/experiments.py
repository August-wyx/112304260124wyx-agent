from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import text

from recommender.contracts import Algorithm, AlgorithmNotImplemented, RecommendationRequest, RecommendationResult, PROVIDERS, recommend
from recommender.data import ContractError
from recommender.student.cold_start import ColdStartRequest
from recommender.student.explain import explain as generate_explanations
from .config import DATASET, SPLIT
from .errors import APIError
from .schemas import IdPath, Input, identifier
from .security import ActorDependency

router = APIRouter(tags=["学生算法预留边界"])


class RecommendationQuery(Input):
    limit: int = Field(default=10, ge=1, le=50)
    interests: str | None = Field(default=None, max_length=200)


def invoke(algorithm: Algorithm, kind: str, uid: int, limit: int, interests: tuple[str, ...] = ()):
    request = RecommendationRequest(kind, uid, limit, "business", DATASET, SPLIT)
    if algorithm == Algorithm.cold_start and interests:
        request = ColdStartRequest(kind, uid, limit, "business", DATASET, SPLIT, tuple(interests))
    try:
        return recommend(algorithm, request)
    except AlgorithmNotImplemented:
        raise APIError(501, "ALGORITHM_NOT_IMPLEMENTED", "此推荐算法留给学生实现", {
            "status": "not_implemented", "algorithm": algorithm.value, "subject_key": kind + ":" + str(uid),
            "dataset_version": DATASET, "split_version": SPLIT, "runtime_mode": "business",
            "model_version": None, "batch_id": None, "items": []}) from None
    except ContractError as exc:
        raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID", "DATA_MODE_INVALID"} else 500,
            exc.code, str(exc)) from None


@router.get("/experiments/algorithms")
def algorithms():
    return {"items": [{"algorithm": algorithm.value, "status": "registered" if algorithm in PROVIDERS else "not_implemented"} for algorithm in Algorithm]}


@router.get("/experiments/evaluations")
def evaluations():
    # The business API never imports an evaluation provider or opens evaluation
    # data; it only returns the summary recorded by the isolated offline run.
    from .evaluation_results import SUMMARY
    return SUMMARY


@router.get("/me/recommendations/{algorithm}", response_model=RecommendationResult)
def my_recommendations(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    selected = tuple(part.strip() for part in (query.interests or "").split(",") if part.strip())
    if selected and algorithm != Algorithm.cold_start:
        raise APIError(422, "INVALID_INTERESTS", "只有冷启动算法支持兴趣类型")
    return invoke(algorithm, "app", actor.account_id, query.limit, selected)


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}", response_model=RecommendationResult)
def history_recommendations(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                            query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    return invoke(algorithm, "ml", uid, query.limit)


@router.get("/me/recommendations/{algorithm}/explain")
def my_explanations(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    """Return verifiable personalized explanations for each recommended movie.

    Internally runs the real recommendation first (bound to the same request
    contract), then generates an explanation grounded in the actual model
    evidence — ItemCF neighbour similarities, Content genre fits, ALS scores,
    Popular popularity counts, and the viewer's real history ratings.
    """
    selected = tuple(part.strip() for part in (query.interests or "").split(",") if part.strip())
    result = invoke(algorithm, "app", actor.account_id, query.limit, selected)
    request = RecommendationRequest("app", actor.account_id, query.limit, "business", DATASET, SPLIT)
    try:
        explanations = generate_explanations(request, algorithm, [item.model_dump() for item in result.items])
    except ContractError as exc:
        raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID"} else 500,
            exc.code, str(exc)) from None
    return {"algorithm": algorithm.value, "model_version": result.model_version,
            "generated_at": result.generated_at.isoformat(), "limit": query.limit,
            "total": len(explanations), "items": explanations}


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}/explain")
def history_explanations(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                         query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    result = invoke(algorithm, "ml", uid, query.limit)
    explanation_request = RecommendationRequest("ml", uid, query.limit, "business", DATASET, SPLIT)
    try:
        explanations = generate_explanations(explanation_request, algorithm, [item.model_dump() for item in result.items])
    except ContractError as exc:
        raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID"} else 500,
            exc.code, str(exc)) from None
    return {"algorithm": algorithm.value, "model_version": result.model_version,
            "generated_at": result.generated_at.isoformat(), "limit": query.limit,
            "total": len(explanations), "items": explanations}
