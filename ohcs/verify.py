"""Quote verification: every excerpt must be found in the cached full text before it is marked verbatim.

Handles '...' elisions by matching each fragment separately, normalises whitespace, quotes and
hyphenation from PDF extraction, and returns the page number (pages are split on \\f by collectors.pdf_to_text).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher


def _norm(s: str) -> str:
    # Remove formatting differences that should not prevent a quotation match.
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"-\s*\n\s*", "", s)           # de-hyphenate line breaks
    return re.sub(r"\s+", " ", s).strip().lower()


def locate(fragment: str, full_text: str, min_ratio: float = 0.92) -> tuple[float, int | None]:
    """Best fuzzy match of `fragment` in `full_text`; returns (ratio, 1-based page or None)."""
    frag = _norm(fragment)
    best, best_page = 0.0, None
    for pno, page in enumerate(full_text.split("\f"), start=1):
        # Search pages separately so a match can retain its source page number.
        pg = _norm(page)
        if frag in pg:
            # An exact match after normalization needs no fuzzy comparison.
            return 1.0, pno
        n = len(frag)
        # Try overlapping text windows and keep the closest wording found.
        for i in range(0, max(1, len(pg) - n + 1), max(1, n // 4)):
            r = SequenceMatcher(None, frag, pg[i:i + n]).ratio()
            if r > best:
                best, best_page = r, pno
    # A weak match keeps its score but receives no verified page number.
    return (best, best_page) if best >= min_ratio else (best, None)


def verify_excerpt(excerpt: str, full_text: str) -> dict:
    # Split at omitted text and check the remaining substantial fragments separately.
    frags = [f.strip(" .") for f in re.split(r"\.\.\.|…", excerpt) if len(f.strip()) > 8]
    res = [locate(f, full_text) for f in frags]
    ok = all(p is not None for _, p in res)  # Every checked fragment must be found.
    # "verbatim" means normalized exact matches; "close" allows fuzzy matches.
    return {"status": "verbatim" if ok and all(r == 1.0 for r, _ in res) else "close" if ok else "not_found",
            "pages": sorted({p for _, p in res if p}), "min_ratio": round(min(r for r, _ in res), 3)}


if __name__ == "__main__":
    # Demonstrate matching an excerpt with omitted words against a two-page text.
    doc = "Some preamble.\f So I moved to MIT in the fall of 1972. And at the same time, Mike Schroeder was hired."
    print(verify_excerpt("I moved to MIT in the fall of 1972...Mike Schroeder was hired", doc))
