"""Fetch real film posters for the local catalogue from Letterboxd.

The frozen MovieLens snapshot has no poster files. This helper resolves each
film through its Letterboxd page, checks the English title and release year in
the page metadata, then downloads the official 2:3 poster into
``frontend/public/posters/<movie_id>.jpg``.

Only requested ids and a bounded popularity prefix are fetched; anything missing
keeps the generated archive cover.

Run from the project root on the host:

    python scripts/fetch_posters.py --ids 3253,2502,1517 --workers 5
    python scripts/fetch_posters.py --limit 600
"""
from __future__ import annotations

import argparse
import csv
import difflib
import html as html_entities
import json
import random
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/packages/rec-course-v3-train5-1.0.0"
STATS = ROOT / "models/business/popular-v1/item-stats.json"
OUTPUT = ROOT / "frontend/public/posters"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
PRINT_LOCK = threading.Lock()
COUNTERS = {"fetched": 0, "missing": 0, "skipped": 0, "done": 0}


def base_title(title: str) -> str:
    value = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
    for article in (", The", ", A", ", An"):
        if value.endswith(article):
            value = article[2:] + " " + value[: -len(article)].strip()
    return value


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def similar(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def slugify(title: str) -> str:
    value = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    value = value.lower().replace("&", " and ").replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def title_variants(title: str) -> list[str]:
    variants: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip(" -:")
        if value and value not in variants:
            variants.append(value)

    add(title)
    add(re.sub(r"\([^)]*\)", "", title))
    for base in list(variants):
        for separator in (":", " - "):
            add(base.split(separator)[-1])
    stripped = re.sub(r"^[^:]*?'s\s+", "", title)
    if len(stripped.split()) >= 2:
        add(stripped)
    return variants


def slug_candidates(title: str, year: str) -> list[str]:
    slugs: list[str] = []
    for variant in title_variants(title):
        slug = slugify(variant)
        for value in ([f"{slug}-{year}", slug] if year else [slug]):
            if value and value not in slugs:
                slugs.append(value)
    return slugs


def fetch(url: str, timeout: int = 25, attempts: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            last = error
            if error.code == 404 or attempt == attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
        except Exception as error:  # noqa: BLE001 - network flakiness
            last = error
            if attempt == attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise last  # pragma: no cover


def poster_from_page(html: str) -> str | None:
    posters = re.findall(r'https://a\.ltrbxd\.com/resized/[^"\'\s]+\.jpg[^"\'\s]*', html)
    preferred = [value for value in posters if "-0-600-0-900-crop" in value]
    return (preferred or [value for value in posters if "film-poster" in value] or [None])[0]


def matches(html: str, title: str, year: str) -> bool:
    meta = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    if not meta:
        return False
    og_title = html_entities.unescape(meta.group(1))
    og_year = re.search(r"\((\d{4})\)\s*$", og_title)
    if year and og_year and abs(int(year) - int(og_year.group(1))) > 1:
        return False
    candidate = re.sub(r"\s*\(\d{4}\)\s*$", "", og_title).strip()
    left, right = normalize(title), normalize(candidate)
    return similar(title, candidate) >= 0.86 or (
        len(right) >= 4 and (left.startswith(right) or right.startswith(left)
                             or left.endswith(right) or right.endswith(left)))


def resolve(movie: dict) -> str | None:
    title = base_title(movie["movielens_title"])
    year = movie.get("release_year") or ""
    for slug in slug_candidates(title, year):
        try:
            html = fetch(f"https://letterboxd.com/film/{slug}/")
        except Exception:  # noqa: BLE001 - 404 and network errors both mean "try next slug"
            continue
        if matches(html, title, year):
            image = poster_from_page(html)
            if image:
                return image
    return None


def download(url: str, target: Path) -> bool:
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30).read()
    except Exception:
        return False
    if len(data) < 4096 or not data.startswith(b"\xff\xd8"):
        return False
    target.write_bytes(data)
    return True


def grab(movie_id: str, movie: dict, target: Path, jitter: float) -> tuple[str, str]:
    time.sleep(random.uniform(0, jitter))
    if target.exists():
        return movie_id, "skipped"
    image = resolve(movie)
    if image and download(image, target):
        return movie_id, "fetched"
    return movie_id, "missing"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="popularity prefix to fetch")
    parser.add_argument("--ids", default="", help="comma separated movie ids to fetch first")
    parser.add_argument("--delay", type=float, default=0.6, help="max random delay per task (seconds)")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()

    with (PACKAGE / "movies.csv").open(encoding="utf-8", newline="") as stream:
        movies = {row["movie_id"]: row for row in csv.DictReader(stream)}
    stats = json.loads(STATS.read_text(encoding="utf-8"))["items"]

    ranked: list[str] = [value.strip() for value in args.ids.split(",") if value.strip()]
    if args.limit:
        ranked += sorted(stats, key=lambda key: (-stats[key]["count"], int(key)))[: args.limit]
    ordered = list(dict.fromkeys(value for value in ranked if value in movies))
    OUTPUT.mkdir(parents=True, exist_ok=True)

    total = len(ordered)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(grab, movie_id, movies[movie_id], OUTPUT / f"{movie_id}.jpg", args.delay)
                   for movie_id in ordered]
        for future in as_completed(futures):
            movie_id, status = future.result()
            COUNTERS[status] += 1
            COUNTERS["done"] += 1
            with PRINT_LOCK:
                if COUNTERS["done"] % 10 == 0:
                    print(json.dumps({"progress": f"{COUNTERS['done']}/{total}", "fetched": COUNTERS["fetched"],
                                      "missing": COUNTERS["missing"], "skipped": COUNTERS["skipped"]}), flush=True)
    print(json.dumps({"status": "done", "fetched": COUNTERS["fetched"], "missing": COUNTERS["missing"],
                      "skipped": COUNTERS["skipped"], "files": len(list(OUTPUT.glob("*.jpg")))}))


if __name__ == "__main__":
    main()
