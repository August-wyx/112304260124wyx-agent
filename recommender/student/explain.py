"""Personalized recommendation explanation generator.

For each recommended movie, extracts verifiable evidence from the underlying
algorithm (ItemCF neighbour similarities, Content genre matches, ALS latent
factors, Popular popularity stats) and the viewer's real history, then
renders a natural-language reason grounded in those numbers.

When Ark (Doubao) API credentials are available via ARK_API_KEY / ARK_ENDPOINT
environment variables, the raw evidence is additionally sent to the model for
a natural-language AI-generated explanation that can be shown alongside the
rule-based fallback. If the API is unavailable, template-rendered reasons are
returned unchanged — LLM never decides what to recommend, it only narrates.

Design rule: every reason must carry its raw evidence so that a reviewer
can trace each claim back to the model artifact or the history table. No
hard-coded copy, no simulated data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path

from recommender.business import read_history
from recommender.contracts import Algorithm, RecommendationRequest
from recommender.data import ContractError, require

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
ITEMCF_MANIFEST = ROOT / "models/business/itemcf-v1/manifest.json"
CONTENT_MANIFEST = ROOT / "models/business/content-v1/manifest.json"
ALS_MANIFEST = ROOT / "models/business/als-v1/manifest.json"
POPULAR_MANIFEST = ROOT / "models/business/popular-v1/manifest.json"


# ---------------------------------------------------------------------------
# Model artifact loaders (keep small, per-call)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=2)
def _catalog() -> dict[str, dict]:
    """movie_id -> {movielens_title, genres: list[str], release_year?}"""
    with (PACKAGE / "movies.csv").open(encoding="utf-8", newline="") as fh:
        return {row["movie_id"]: row for row in csv.DictReader(fh)}


@lru_cache(maxsize=2)
def _itemcf_neighbours() -> dict[str, tuple[tuple[str, float], ...]]:
    manifest = json.loads(ITEMCF_MANIFEST.read_text(encoding="utf-8"))
    artifact = json.loads((ITEMCF_MANIFEST.parent / "item-neighbours.json").read_text(encoding="utf-8"))
    require(manifest.get("algorithm") == "itemcf", "ItemCF manifest mismatch", "MODEL_BINDING_INVALID")
    return {str(k): tuple((str(p[0]), float(p[1])) for p in v) for k, v in artifact["items"].items()}


@lru_cache(maxsize=2)
def _content_items() -> dict[str, dict]:
    manifest = json.loads(CONTENT_MANIFEST.read_text(encoding="utf-8"))
    artifact = json.loads((CONTENT_MANIFEST.parent / "item-features.json").read_text(encoding="utf-8"))
    require(manifest.get("algorithm") == "content", "Content manifest mismatch", "MODEL_BINDING_INVALID")
    genre_idf = {str(k): float(v) for k, v in artifact["genre_idf"].items()}
    items = {}
    for mid, entry in artifact["items"].items():
        genres = tuple(str(g) for g in entry["genres"])
        items[str(mid)] = {"genres": genres, "support": int(entry["support"]),
                            "genre_idf_vector": {g: genre_idf.get(g, 1.0) for g in genres}}
    return items


@lru_cache(maxsize=2)
def _popular_stats() -> dict[str, dict]:
    manifest = json.loads(POPULAR_MANIFEST.read_text(encoding="utf-8"))
    artifact = json.loads((POPULAR_MANIFEST.parent / "item-stats.json").read_text(encoding="utf-8"))
    require(manifest.get("algorithm") == "popular", "Popular manifest mismatch", "MODEL_BINDING_INVALID")
    # item-stats has {"items": {mid: {"count": N, "avg": V}}, "quality_weight": ..., "hotness_weight": ...}
    return {"items": artifact["items"],
            "quality_weight": float(artifact.get("quality_weight", 0.7)),
            "hotness_weight": float(artifact.get("hotness_weight", 0.3))}


# ---------------------------------------------------------------------------
# Evidence extractors per algorithm
# ---------------------------------------------------------------------------

def _neighbour_evidence(movie_id: str, watched: dict[str, float]) -> list[dict]:
    """Return top-3 itemcf neighbours of movie_id that the user has rated."""
    try:
        neighbours = _itemcf_neighbours().get(movie_id, ())
    except (OSError, ValueError, ContractError):
        return []
    hits = []
    for nid, sim in neighbours:
        if nid in watched:
            hits.append({"neighbour_movie_id": nid, "similarity": round(sim, 4),
                         "user_rating": watched[nid]})
            if len(hits) >= 3:
                break
    return hits


def _content_evidence(movie_id: str, genre_profile: dict[str, float]) -> dict | None:
    """Return matched genres and profile fit score for a candidate movie."""
    try:
        items = _content_items()
    except (OSError, ValueError, ContractError):
        return None
    feature = items.get(movie_id)
    if not feature:
        return None
    matched = [(g, genre_profile[g]) for g in feature["genres"] if g in genre_profile and genre_profile[g] > 0]
    if not matched:
        return None
    # How well the candidate's genres align with the profile (weighted by IDF)
    dot = sum(feature["genre_idf_vector"].get(g, 1.0) * genre_profile.get(g, 0.0) for g in feature["genres"])
    profile_norm = math.sqrt(sum(v * v for v in genre_profile.values()))
    item_norm = math.sqrt(sum(feature["genre_idf_vector"].get(g, 1.0) ** 2 for g in feature["genres"]))
    cosine = round(dot / (profile_norm * item_norm), 4) if profile_norm and item_norm else 0.0
    return {"matched_genres": [g for g, _ in matched],
            "matched_weights": [round(w, 3) for _, w in matched],
            "cosine_fit": cosine}


def _popular_evidence(movie_id: str) -> dict | None:
    try:
        stats = _popular_stats()["items"].get(movie_id)
    except (OSError, ValueError, ContractError):
        return None
    if not stats:
        return None
    return {"rating_count": int(stats.get("count", 0)), "avg_rating": round(float(stats.get("avg", 0)), 2)}


def _build_genre_profile(ratings: list) -> dict[str, float]:
    """Build a user genre-profile from real history, weighted by (rating-2.5) * IDF."""
    try:
        items = _content_items()
    except (OSError, ValueError, ContractError):
        return {}
    profile: dict[str, float] = {}
    for fb in ratings:
        mid = str(fb.movie_id)
        feature = items.get(mid)
        if not feature:
            continue
        weight = float(fb.rating) - 2.5
        if weight <= 0:
            continue
        for genre in feature["genres"]:
            profile[genre] = profile.get(genre, 0.0) + weight * feature["genre_idf_vector"].get(genre, 1.0)
    return profile


# ---------------------------------------------------------------------------
# Chinese genre label
# ---------------------------------------------------------------------------

_GENRE_LABELS = {
    "Action": "动作", "Adventure": "冒险", "Animation": "动画", "Children": "儿童",
    "Comedy": "喜剧", "Crime": "犯罪", "Documentary": "纪录", "Drama": "剧情",
    "Fantasy": "奇幻", "Film-Noir": "黑色电影", "Horror": "恐怖", "Musical": "音乐",
    "Mystery": "悬疑", "Romance": "爱情", "Sci-Fi": "科幻", "Thriller": "惊悚",
    "War": "战争", "Western": "西部", "IMAX": "IMAX",
}


def _zh_genre(value: str) -> str:
    return _GENRE_LABELS.get(value, value)


# ---------------------------------------------------------------------------
# Natural-language reason rendering
# ---------------------------------------------------------------------------

def _render_itemcf(catalog: dict, evidence: list[dict]) -> list[dict]:
    """Render ItemCF-based reasons. Each reason carries raw evidence."""
    reasons = []
    for hit in evidence:
        nid = hit["neighbour_movie_id"]
        title = catalog.get(nid, {}).get("movielens_title", f"电影#{nid}")
        rating_str = f"{hit['user_rating']:.1f}"
        sim_pct = round(hit["similarity"] * 100)
        text = (f"你对《{title}》打了 {rating_str} 分，这部电影与它的内容相似度达 {sim_pct}%，"
                f"协同过滤算法因此推断你很可能也会喜欢这一部。")
        reasons.append({"type": "itemcf_neighbor", "evidence": hit, "text": text})
    return reasons


def _render_content(evidence: dict, catalog: dict, movie_id: str) -> list[dict]:
    reasons = []
    genre_labels = [_zh_genre(g) for g in evidence["matched_genres"]]
    genre_str = "、".join(genre_labels) if len(genre_labels) <= 3 else "、".join(genre_labels[:3]) + " 等"
    cos_pct = round(evidence["cosine_fit"] * 100)
    text = (f"这部电影的类型与你的口味画像高度吻合：{genre_str}。"
            f"内容相似度 {cos_pct}%，内容推荐算法将它优先推送给你。")
    reasons.append({"type": "content_genre", "evidence": evidence, "text": text})
    return reasons


def _render_popular(evidence: dict) -> list[dict]:
    text = (f"它是热门电影之一，有 {evidence['rating_count']} 人评分，"
            f"平均评分 {evidence['avg_rating']}，是贝叶斯质量与热度综合排名的结果。")
    return [{"type": "popularity", "evidence": evidence, "text": text}]


def _render_als(rec_score: float | None) -> list[dict]:
    if rec_score is None:
        return []
    text = (f"矩阵分解模型根据你历史评分的隐因子偏好推断，这部电影对你的匹配度得分为 "
            f"{round(rec_score, 4)}，因此被推送到推荐列表中。")
    return [{"type": "als_latent", "evidence": {"score": round(rec_score, 4)}, "text": text}]


def _render_coldstart(catalog: dict, movie_id: str, favorites: list[str] | None = None) -> list[dict]:
    item = catalog.get(movie_id)
    if not item:
        return []
    genres = item.get("genres", "").split("|")
    labels = [_zh_genre(g) for g in genres if g]
    text = (f"你还没有评分记录，当前根据你在冷启动时选择的兴趣类型——"
            f"{'、'.join(labels) if labels else '热门偏好'}——以及热门度综合推荐了这部电影。")
    return [{"type": "coldstart_fallback", "evidence": {"genres": labels}, "text": text}]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def explain(request: RecommendationRequest, algorithm: Algorithm, recommendation_items: list[dict]) -> list[dict]:
    """Generate a verifiable explanation for each recommended movie.

    recommendation_items is expected to be [{movie_id, score, rank, ...}, ...]
    (the items from a RecommendationResult). Returns a list of per-movie
    explanation dicts, each containing a list of reasons, every reason with
    raw evidence and natural-language text.
    """
    # Need business request to read history; build one if caller passed an eval request
    business_request = request
    if business_request.runtime_mode != "business":
        business_request = RecommendationRequest(
            subject_kind=request.subject_kind, subject_id=request.subject_id,
            limit=request.limit, runtime_mode="business",
            dataset_version=request.dataset_version, split_version=request.split_version,
        )
    history = read_history(business_request)
    watched = {str(fb.movie_id): float(fb.rating) for fb in history.ratings}
    favorites = list(history.favorite_movie_ids)
    catalog = _catalog()
    genre_profile = _build_genre_profile(history.ratings)

    explanations = []
    for item in recommendation_items:
        mid = str(item["movie_id"])
        movie_title = catalog.get(mid, {}).get("movielens_title", f"电影#{mid}")
        movie_genres_raw = catalog.get(mid, {}).get("genres", "")
        movie_genres = [_zh_genre(g) for g in movie_genres_raw.split("|") if g]
        score = item.get("score")
        rank = item.get("rank")

        reasons: list[dict] = []
        sources: list[str] = []

        if algorithm == Algorithm.itemcf:
            hits = _neighbour_evidence(mid, watched)
            reasons.extend(_render_itemcf(catalog, hits))
            sources.append("itemcf")

        elif algorithm == Algorithm.content:
            evidence = _content_evidence(mid, genre_profile)
            if evidence:
                reasons.extend(_render_content(evidence, catalog, mid))
            sources.append("content")

        elif algorithm == Algorithm.als:
            reasons.extend(_render_als(score))
            # ALS is opaque; supplement with ItemCF neighbour evidence when possible
            hits = _neighbour_evidence(mid, watched)
            if hits:
                reasons.extend(_render_itemcf(catalog, hits[:1]))
            sources.append("als")

        elif algorithm == Algorithm.popular:
            evidence = _popular_evidence(mid)
            if evidence:
                reasons.extend(_render_popular(evidence))
            sources.append("popular")

        elif algorithm == Algorithm.cold_start:
            reasons.extend(_render_coldstart(catalog, mid, favorites))
            sources.append("cold_start")

        if not reasons:
            # Fallback: we still attach the raw inputs so the explanation is not empty
            reasons.append({
                "type": "generic",
                "evidence": {"watched_count": len(watched), "genre_profile": dict(list(genre_profile.items())[:5])},
                "text": f"基于你的历史评分（共 {len(watched)} 部），{_algo_name(algorithm)} 算法推荐了这部电影。",
            })

        explanations.append({
            "movie_id": mid,
            "title": movie_title,
            "genres": movie_genres,
            "rank": rank,
            "score": round(score, 4) if score is not None else None,
            "reasons": reasons,
            "sources": sources,
            "evidence_hash": _hash_evidence(reasons),
        })

    return explanations


def _algo_name(algorithm: Algorithm) -> str:
    return {Algorithm.itemcf: "协同过滤", Algorithm.content: "内容推荐",
            Algorithm.als: "矩阵分解", Algorithm.popular: "热门推荐",
            Algorithm.cold_start: "冷启动"}.get(algorithm, algorithm.value)


def _hash_evidence(reasons: list[dict]) -> str:
    """Deterministic short hash of all evidence dicts for tamper-check display."""
    body = json.dumps([r["evidence"] for r in reasons], sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(body.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Ark (Doubao) LLM integration
# ---------------------------------------------------------------------------

_ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
_ARK_SYSTEM = (
    "你是推荐系统的解释助手。用户会给你一部被推荐电影的真实依据（用户历史评分、"
    "算法命中的相似度、类型匹配等）。你的任务：\n"
    "1. 用普通话把依据翻译成一段自然的中文解释，2-4 句话即可；\n"
    "2. 必须只依据提供的事实，不得编造评分、电影、相似度或类型；\n"
    "3. 不得修改或质疑推荐列表，你只负责解释为什么推荐它；\n"
    "4. 不要输出 JSON、不要用 Markdown、不要加称呼。"
)


def _ark_available() -> bool:
    return bool(os.environ.get("ARK_API_KEY") and os.environ.get("ARK_ENDPOINT"))


def ask_llm_ai_explanation(
    algorithm: Algorithm,
    movie_title: str,
    movie_genres: list[str],
    reasons: list[dict],
    user_watched_count: int,
) -> str | None:
    """Call Ark Doubao to narrate the evidence. Returns None on any failure."""
    if not _ark_available():
        return None
    # Build a compact, evidence-only payload the model can safely narrate.
    algo_name = _algo_name(algorithm)
    evidence_lines = []
    for r in reasons:
        ev = r.get("evidence", {})
        t = r.get("type", "")
        if algorithm == Algorithm.itemcf and "neighbour_movie_id" in ev:
            evidence_lines.append(
                f"- 你给电影#{ev['neighbour_movie_id']}打了 {ev['user_rating']:.1f} 分；"
                f"它与目标电影的 ItemCF 相似度 {ev['similarity']:.4f}。"
            )
        elif algorithm == Algorithm.content and "matched_genres" in ev:
            evidence_lines.append(
                f"- 目标电影类型 {','.join(ev['matched_genres'])} 与你的画像匹配；"
                f"余弦相似度 {ev['cosine_fit']:.4f}。"
            )
        elif algorithm == Algorithm.als and "score" in ev:
            evidence_lines.append(f"- ALS 隐因子匹配度得分 {ev['score']:.4f}。")
        else:
            evidence_lines.append(f"- {json.dumps(ev, ensure_ascii=False)}")
    user_text = (
        f"请解释为什么推荐电影《{movie_title}》（类型：{'、'.join(movie_genres) or '未知'}）。\n"
        f"推荐算法：{algo_name}。你共看过 {user_watched_count} 部电影。\n"
        f"真实依据如下：\n" + "\n".join(evidence_lines) +
        "\n\n请用 2-4 句中文自然语言解释，不要编造。"
    )
    try:
        import urllib.request
        import ssl
        payload = json.dumps({
            "model": os.environ["ARK_ENDPOINT"],
            "messages": [
                {"role": "system", "content": _ARK_SYSTEM},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.3,
            "max_tokens": 300,
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            _ARK_URL, data=payload, method="POST",
            headers={
                "Authorization": f"Bearer {os.environ['ARK_API_KEY']}",
                "Content-Type": "application/json",
            },
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"].strip()
        if not content or len(content) < 5:
            return None
        return content
    except Exception:
        return None
