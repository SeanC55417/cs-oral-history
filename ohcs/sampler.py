"""Sampling frame: Drafty's CS-professor dataset (Brown HCI, Shaun Wallace et al.).

The CSV ships in the public repo brownhci/drafty at user_interest_profile/finalProfs.csv
(FullName, University, JoinYear, SubField, Bachelors, Doctorate; ~5,056 rows).

Oral-tradition idea: the "elders" (earliest cohorts) are sampled first, because their
first-hand memory is the scarcest, and we stratify by decade x subfield so the history
isn't only told by the famous few.
"""
from __future__ import annotations

import csv
import os
import random
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

# Find project files relative to this module, regardless of the terminal's folder.
ROOT = Path(__file__).resolve().parent.parent
# An environment variable lets callers use a faculty CSV stored somewhere else.
DRAFTY_CSV = Path(os.environ.get(
    "DRAFTY_CSV", ROOT / "libraries" / "drafty" / "user_interest_profile" / "finalProfs.csv"
)).expanduser()


@dataclass
class Faculty:
    # Keep one faculty row together; the decade is calculated from join_year below.
    name: str
    university: str
    join_year: int | None
    subfield: str
    bachelors: str
    doctorate: str

    @property
    def cohort(self) -> str:
        if self.join_year is None:
            return "unknown"
        return f"{self.join_year // 10 * 10}s"  # For example, 1972 becomes "1970s".

    def to_dict(self):
        # Include the calculated decade when exporting the row to JSON.
        d = asdict(self)
        d["cohort"] = self.cohort
        return d


def load_frame(path: Path = DRAFTY_CSV) -> list[Faculty]:
    # Read columns by name and turn each CSV row into a Faculty record.
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            jy = r.get("JoinYear", "").strip()
            # Missing or nonnumeric years stay unknown instead of being guessed.
            rows.append(Faculty(
                name=r["FullName"].strip(), university=r["University"].strip(),
                join_year=int(jy) if jy.isdigit() else None,
                subfield=r.get("SubField", "").strip() or "Unspecified",
                bachelors=r.get("Bachelors", "").strip(), doctorate=r.get("Doctorate", "").strip()))
    return rows


def suspicious_join_years(frame: list[Faculty], min_year: int = 1960) -> list[Faculty]:
    """Rows whose JoinYear predates the first CS departments (~1962) -- likely data errors
    (e.g. a faculty member listed as joining in 1955 who got a PhD decades later).
    These are good candidates for a Jev Noul 'join_year_plausible' check + human review."""
    return [f for f in frame if f.join_year is not None and f.join_year < min_year]


def stratified_sample(frame: list[Faculty], per_cell: int = 2, cohorts: tuple[str, ...] | None = None,
                      seed: int = 7) -> list[Faculty]:
    """Sample up to `per_cell` people for every (cohort, subfield) cell, oldest cohorts first."""
    rng = random.Random(seed)  # A fixed seed makes repeated samples reproducible.
    cells: dict[tuple[str, str], list[Faculty]] = defaultdict(list)
    for f in frame:
        if cohorts and f.cohort not in cohorts:
            continue
        cells[(f.cohort, f.subfield)].append(f)  # Group by both decade and specialty.
    out = []
    for key in sorted(cells):
        people = cells[key]
        # Choose within each group so one large group cannot fill the whole sample.
        rng.shuffle(people)
        out.extend(people[:per_cell])
    return out


def match(frame: list[Faculty], name: str) -> Faculty | None:
    # Ignore capitalization and periods, but otherwise require the same name.
    n = name.lower().replace(".", "")
    for f in frame:
        if f.name.lower().replace(".", "") == n:
            return f
    return None


if __name__ == "__main__":
    # Running this module directly prints a small sampling preview.
    fr = load_frame()
    print(len(fr), "faculty;", sum(f.join_year is not None for f in fr), "with JoinYear")
    print("suspicious (<1960):", [(f.name, f.join_year) for f in suspicious_join_years(fr)])
    s = stratified_sample(fr, per_cell=1, cohorts=("1960s", "1970s"))
    print(len(s), "sampled elders, e.g.", [f.name for f in s[:8]])
