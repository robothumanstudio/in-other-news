#!/usr/bin/env python3
"""Fetch the feeds in feeds.yaml and render The Reading Room as a static page.

Usage:  python build.py            -> writes public/index.html
        python build.py other.yaml -> use a different config
"""
from __future__ import annotations

import html
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "public"
USER_AGENT = "ReadingRoom/1.0 (+static RSS front page)"
TIMEOUT = 20

TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
SKIP_IMG = re.compile(r"(\.gif|pixel|tracking|feedburner|gravatar|1x1)", re.I)
NEWS = ("news-au", "news-world")
TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|si$|CMP$)", re.I)


# ── helpers ──────────────────────────────────────────────
def clean_text(raw: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    # Drop boilerplate like "The post X appeared first on Y." and "Continue reading…"
    text = re.sub(r"\s*The post .{0,200} appeared first on .*$", "", text)
    return re.sub(r"\s*(Continue reading|Read more)\W*$", "", text, flags=re.I)


def find_image(entry) -> str | None:
    for m in entry.get("media_thumbnail", []) + entry.get("media_content", []):
        url = m.get("url", "")
        if url and m.get("medium", "image") == "image" and not SKIP_IMG.search(url):
            return url
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image/"):
            return enc.get("href")
    blobs = [c.get("value", "") for c in entry.get("content", [])]
    blobs.append(entry.get("summary", ""))
    for blob in blobs:
        for url in IMG_RE.findall(blob):
            if not SKIP_IMG.search(url):
                return html.unescape(url)
    return None


def entry_date(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def link_key(url: str) -> str:
    """Normalise a link for duplicate checks, dropping only tracking parameters."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING.match(k)]
    return urlunsplit(("", parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def section_for(entry, feed: dict) -> str:
    """Use the feed's category_map to route tagged stories to another department."""
    cmap = {k.lower(): v for k, v in (feed.get("category_map") or {}).items()}
    for tag in entry.get("tags", []):
        term = (tag.get("term") or "").lower()
        if term in cmap:
            return cmap[term]
    return feed["section"]


# ── fetching ─────────────────────────────────────────────
def fetch_feed(feed: dict, cfg: dict, now: datetime) -> list[dict]:
    s, section = cfg["settings"], feed["section"]
    if section in NEWS:
        cutoff = now - timedelta(hours=s.get("news_max_age_hours", 24))
    elif section == "video":
        cutoff = now - timedelta(days=s.get("video_max_age_days", 45))
    else:
        cutoff = now - timedelta(days=s.get("longform_max_age_days", 45))

    req = urllib.request.Request(feed["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            parsed = feedparser.parse(resp.read())
    except Exception as exc:  # one broken feed shouldn't break the page
        print(f"  ! {feed['name']}: {exc}", file=sys.stderr)
        return []

    items = []
    for e in parsed.entries:
        link, title = e.get("link"), clean_text(e.get("title", ""))
        if not link or not title:
            continue
        is_video = "youtube.com/" in link or "youtu.be/" in link
        if is_video and s.get("skip_youtube_shorts", True) and "/shorts/" in link:
            continue
        date = entry_date(e)
        if date and date < cutoff:
            continue
        summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "")
        if not summary and e.get("media_description"):
            summary = e["media_description"]
        items.append({
            "title": title,
            "link": link,
            "source": feed["name"],
            "section": section_for(e, feed),
            "can_lead": feed.get("lead", True) and not is_video,
            "is_video": is_video,
            "date": date or now,
            "summary": clean_text(summary),
            "image": None if section in NEWS else find_image(e),
        })
    items.sort(key=lambda i: i["date"], reverse=True)
    items = items[: feed.get("per_feed", 6)]
    return items


# ── assembling the page ──────────────────────────────────
def balanced(items: list[dict], n: int, per_source: int) -> list[dict]:
    """Newest first, but no source takes more than `per_source` slots
    unless there's nothing else to fill them with."""
    chosen, counts = [], {}
    for it in items:
        if counts.get(it["source"], 0) < per_source:
            chosen.append(it)
            counts[it["source"]] = counts.get(it["source"], 0) + 1
    extra = [i for i in items if i not in chosen]
    chosen = (chosen + extra)[:n] if len(chosen) < n else chosen[:n]
    return sorted(chosen, key=lambda i: i["date"], reverse=True)


def main(config_path: Path) -> None:
    cfg = yaml.safe_load(config_path.read_text())
    site, s, feeds = cfg["site"], cfg["settings"], cfg["feeds"]
    tz = ZoneInfo(site.get("timezone", "UTC"))
    now = datetime.now(timezone.utc)

    print(f"Fetching {len(feeds)} feeds…")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda f: fetch_feed(f, cfg, now), feeds))
    for f, r in zip(feeds, results):
        print(f"  {'✓' if r else '·'} {f['name']}: {len(r)} items")

    seen, items = set(), []
    for item in sorted((i for r in results for i in r), key=lambda i: i["date"], reverse=True):
        key = link_key(item["link"])
        if key not in seen:
            seen.add(key)
            items.append(item)

    def pick(section: str) -> list[dict]:
        return [i for i in items if i["section"] == section]

    # Long Read: the newest department story with an image from a lead-eligible source.
    dept_ids = [d["id"] for d in cfg["departments"]]
    longform = [i for i in items if i["section"] in dept_ids]
    lead = next((i for i in longform if i["image"] and i["can_lead"]), None) \
        or next((i for i in longform if i["can_lead"]), None)

    per_dept = s.get("stories_per_department", 3)
    departments = []
    for d in cfg["departments"]:
        stories = balanced([i for i in pick(d["id"]) if i is not lead],
                           d.get("count", per_dept), s.get("max_per_source", 2))
        if stories:
            departments.append({**d, "stories": stories})

    video = pick("video")[: s.get("video_count", 4)]
    news_n = s.get("news_count", 8)
    news = [
        {"label": "Australia", "items": pick("news-au")[:news_n]},
        {"label": "World", "items": pick("news-world")[:news_n]},
    ]
    news = [col for col in news if col["items"]]

    # Rendering
    def local(d: datetime) -> datetime:
        return d.astimezone(tz)

    def day(d: datetime) -> str:
        l = local(d)
        return f"{l.day} {l:%b}"

    def clock(d: datetime) -> str:
        l = local(d)
        return f"{l.hour % 12 or 12}:{l:%M}{'am' if l.hour < 12 else 'pm'}"

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]))
    env.filters["day"] = day
    env.filters["clock"] = clock

    ln = local(now)
    page = env.get_template("index.html").render(
        site=site, feeds=list({f['name']: f for f in feeds}.values()), lead=lead, departments=departments,
        video=video, news=news,
        today=f"{ln:%A} {ln.day} {ln:%B %Y}", updated=clock(now),
    )
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    total = (1 if lead else 0) + sum(len(d["stories"]) for d in departments) \
        + len(video) + sum(len(c["items"]) for c in news)
    print(f"Wrote {OUT_DIR / 'index.html'} with {total} items.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "feeds.yaml")
