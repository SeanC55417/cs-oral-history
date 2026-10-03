"""Retrieval layer: one small collector per source family. Each returns `RawDoc`s that are
cached to data/cache/<id>.json so extraction is reproducible and re-runnable offline.

Run these from a machine with open internet access; the sandbox used for the first sample
could not reach web.archive.org, reddit.com or youtube.com.

Politeness: all collectors sleep between requests and send a descriptive User-Agent.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import httpx

# Keep downloaded text separate from the curated sample; save() writes here.
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
UA = {"User-Agent": "cs-oral-history-research/0.1 (academic project; contact: see repo)"}


@dataclass
class RawDoc:
    # Give every source type the same basic fields before passage extraction.
    uri: str
    source_type: str            # oral_history_transcript | faculty_homepage | forum_thread | video | paper | memoir_essay
    retrieved: str              # ISO date
    title: str = ""
    text: str = ""
    archived_uri: str | None = None   # Wayback snapshot, if any
    capture_date: str | None = None   # YYYY-MM-DD of the snapshot / post / upload
    meta: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        # Turn the source URL into a stable short filename; snapshots get their own IDs.
        return hashlib.sha1((self.archived_uri or self.uri).encode()).hexdigest()[:12]

    def save(self) -> Path:
        # Call this explicitly to keep a local JSON copy for later processing.
        CACHE.mkdir(parents=True, exist_ok=True)
        p = CACHE / f"{self.id}.json"
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1))
        return p


def _today() -> str:
    # Use the same date format in every collected document's retrieval metadata.
    return time.strftime("%Y-%m-%d")


def _get(url: str, **kw) -> httpx.Response:
    # Share request settings and stop on HTTP errors before processing the response.
    r = httpx.get(url, headers=UA, timeout=60, follow_redirects=True, **kw)
    r.raise_for_status()
    time.sleep(1.0)  # Space out successful requests to avoid rapid repeated downloads.
    return r


def html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup  # pip install beautifulsoup4
    soup = BeautifulSoup(html, "html.parser")
    # Remove browser code and styling so they do not become research text.
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    # Wayback injects a toolbar; drop it
    for t in soup.select("#wm-ipp-base, #wm-ipp, #donato"):
        t.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n")).strip()


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader  # pip install pypdf
    reader = PdfReader(io.BytesIO(data))  # Read downloaded bytes without a temporary PDF.
    return "\n\f\n".join((p.extract_text() or "") for p in reader.pages)  # \f keeps page breaks for citations


# ---------------------------------------------------------------- Wayback Machine
def wayback_snapshots(url: str, start: str = "1995", end: str = "2010", limit: int = 20) -> list[dict]:
    """CDX API: one capture per year of a faculty homepage (collapse on year)."""
    r = _get("https://web.archive.org/cdx/search/cdx", params={
        "url": url, "from": start, "to": end, "output": "json", "filter": "statuscode:200",
        "collapse": "timestamp:4", "limit": limit})
    rows = r.json()
    if not rows:
        return []
    # The first API row names the columns; later rows hold snapshot values.
    head, *body = rows
    return [dict(zip(head, b)) for b in body]


def wayback_fetch(url: str, timestamp: str) -> RawDoc:
    # the `id_` flag returns the original bytes without the Wayback toolbar
    snap = f"https://web.archive.org/web/{timestamp}id_/{url}"
    r = _get(snap)
    return RawDoc(uri=url, archived_uri=snap, source_type="faculty_homepage", retrieved=_today(),
                  capture_date=f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}",
                  title=re.search(r"<title>(.*?)</title>", r.text, re.I | re.S).group(1).strip()
                  if "<title" in r.text.lower() else "", text=html_to_text(r.text))


def faculty_homepage_history(url: str) -> list[RawDoc]:
    """Homepage-as-oral-tradition: the same person's self-description re-told across years."""
    return [wayback_fetch(url, s["timestamp"]) for s in wayback_snapshots(url)]


# ---------------------------------------------------------------- Reddit
def reddit_search(query: str, subreddits=("AskHistorians", "compsci", "IAmA", "programming"),
                  limit: int = 25) -> list[RawDoc]:
    """Public JSON endpoints (no auth, low rate). For volume use PRAW with an API key."""
    docs = []
    for sub in subreddits:
        r = _get(f"https://www.reddit.com/r/{sub}/search.json",
                 params={"q": query, "restrict_sr": 1, "limit": limit, "sort": "relevance"})
        # Each child wraps one search result; search results contain the post text.
        for c in r.json()["data"]["children"]:
            d = c["data"]
            docs.append(RawDoc(uri="https://www.reddit.com" + d["permalink"], source_type="forum_thread",
                               retrieved=_today(), title=d["title"], text=d.get("selftext", ""),
                               capture_date=time.strftime("%Y-%m-%d", time.gmtime(d["created_utc"])),
                               meta={"subreddit": sub, "author": d["author"], "score": d["score"]}))
    return docs


def reddit_thread(permalink: str, max_comments: int = 200) -> RawDoc:
    # A thread response has separate sections for the post and its comments.
    r = _get(permalink.rstrip("/") + ".json", params={"limit": max_comments})
    post, comments = r.json()
    p = post["data"]["children"][0]["data"]
    lines = []

    def walk(node, depth=0):
        # Flatten nested replies while preserving authors and reply depth in the text.
        for c in node.get("data", {}).get("children", []):
            d = c.get("data", {})
            if "body" in d:
                lines.append(f"[{d['author']}|score={d['score']}|depth={depth}] {d['body']}")
                if isinstance(d.get("replies"), dict):
                    walk(d["replies"], depth + 1)
    walk(comments)
    return RawDoc(uri=permalink, source_type="forum_thread", retrieved=_today(), title=p["title"],
                  text=p.get("selftext", "") + "\n\n" + "\n".join(lines),
                  capture_date=time.strftime("%Y-%m-%d", time.gmtime(p["created_utc"])),
                  meta={"author": p["author"], "subreddit": p["subreddit"]})


# ---------------------------------------------------------------- Video
def youtube_transcript(video_id: str, title: str = "") -> RawDoc:
    from youtube_transcript_api import YouTubeTranscriptApi  # pip install youtube-transcript-api
    segs = YouTubeTranscriptApi().fetch(video_id)
    # Keep minute:second timestamps so passages can be traced back to the video.
    text = "\n".join(f"[{int(s.start)//60:02d}:{int(s.start)%60:02d}] {s.text}" for s in segs)
    return RawDoc(uri=f"https://www.youtube.com/watch?v={video_id}", source_type="video",
                  retrieved=_today(), title=title, text=text)


# ---------------------------------------------------------------- Oral-history transcripts
# Starting points for finding source URLs; this table does not crawl the archives.
KNOWN_ARCHIVES = {
    "chm": "https://computerhistory.org/oral-histories/",               # Computer History Museum (PDF transcripts)
    "cbi": "https://conservancy.umn.edu/handle/11299/59493",            # Charles Babbage Institute
    "ethw": "https://ethw.org/Oral-History:List_of_all_Oral_Histories", # IEEE History Center
    "acm_turing": "https://amturing.acm.org/",                           # Turing laureate interviews
    "sova": "https://sova.si.edu/record/nmah.ac.0196",                  # Smithsonian Computer Oral History Collection (1967-73)
}


def transcript(uri: str, source_type: str = "oral_history_transcript") -> RawDoc:
    r = _get(uri)
    ctype = r.headers.get("content-type", "")
    # Choose an extractor using the response type or the URL's file extension.
    text = pdf_to_text(r.content) if ("pdf" in ctype or uri.lower().endswith(".pdf")) else html_to_text(r.text)
    return RawDoc(uri=uri, source_type=source_type, retrieved=_today(), text=text)


# ---------------------------------------------------------------- Papers (OpenAlex; no key needed)
def openalex_memoirs(author_name: str, per_page: int = 25) -> list[dict]:
    """Find retrospective / historical papers by an author (e.g. 'history', 'recollections', 'early days')."""
    a = _get("https://api.openalex.org/authors", params={"search": author_name}).json()["results"]
    if not a:
        return []
    # Use the first author match; ambiguous names may need a manual check.
    aid = a[0]["id"].rsplit("/", 1)[-1]
    q = "history|recollections|retrospective|early days|reminiscences|personal account"
    r = _get("https://api.openalex.org/works", params={
        "filter": f"author.id:{aid}", "search": q, "per-page": per_page}).json()
    # Return discovery metadata and links; full paper text is not downloaded here.
    return [{"title": w["title"], "year": w["publication_year"], "doi": w.get("doi"),
             "oa_url": (w.get("open_access") or {}).get("oa_url")} for w in r["results"]]
