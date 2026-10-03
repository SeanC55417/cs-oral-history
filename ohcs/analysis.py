"""Aggregate views for the preliminary report: theme matrix, agreement with reference codes,
calibration (for when real Jev probabilities are available), recurring formulas, lineage."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict


def agreement(pred: dict[tuple, set], gold: dict[tuple, set], codes: list[str]) -> dict:
    # Compare predicted themes with reference labels for each (source, passage).
    per = {}
    tp_all = fp_all = fn_all = 0
    for c in codes:
        # Count correct labels, extra labels, and missed labels for this theme.
        tp = sum(1 for k in gold if c in gold[k] and c in pred.get(k, set()))
        fp = sum(1 for k in gold if c not in gold[k] and c in pred.get(k, set()))
        fn = sum(1 for k in gold if c in gold[k] and c not in pred.get(k, set()))
        # Precision measures correctness; recall measures how much was found.
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": round(p, 2), "recall": round(r, 2),
                  "f1": round(2 * p * r / (p + r), 2) if p + r else 0.0, "support": tp + fn}
        tp_all, fp_all, fn_all = tp_all + tp, fp_all + fp, fn_all + fn
    # Micro scores combine all counts before calculating the overall result.
    P = tp_all / (tp_all + fp_all) if tp_all + fp_all else 0
    R = tp_all / (tp_all + fn_all) if tp_all + fn_all else 0
    return {"micro_precision": round(P, 2), "micro_recall": round(R, 2),
            "micro_f1": round(2 * P * R / (P + R), 2) if P + R else 0, "per_code": per}


def expected_calibration_error(probs: list[float], labels: list[int], bins: int = 10) -> tuple[float, list[dict]]:
    """ECE + reliability table. The point of RLCD: P=0.9 answers should be right ~90% of the time."""
    table, ece, n = [], 0.0, len(probs)
    for b in range(bins):
        # Group similar predicted probabilities, including 1.0 in the final bin.
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if not idx:
            continue
        conf = sum(probs[i] for i in idx) / len(idx)
        acc = sum(labels[i] for i in idx) / len(idx)
        # Weight each probability-versus-observation gap by its share of examples.
        ece += len(idx) / n * abs(conf - acc)
        table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(idx), "mean_p": round(conf, 2), "observed": round(acc, 2)})
    return round(ece, 3), table


def formulas(passages_by_narrator: dict[str, list[str]], n_range=(2, 4), min_narrators: int = 2) -> list[dict]:
    """Homeric-formula analogue: short phrases re-used by different narrators ('changed my life',
    'first day'). Needs full transcripts to be meaningful; on excerpts it is a smoke test."""
    stop = set("the a an of to and in i was it that at by for on is my me we this so as with be".split())
    seen = defaultdict(set)  # Count distinct narrators, not repeated uses by one person.
    for narr, texts in passages_by_narrator.items():
        for t in texts:
            w = re.findall(r"[a-z']+", t.lower())
            # Slide across the words to collect phrases of each requested length.
            for n in range(n_range[0], n_range[1] + 1):
                for i in range(len(w) - n + 1):
                    g = w[i:i + n]
                    # Skip filler-only phrases and phrases with filler at both ends.
                    if all(x in stop for x in g) or g[0] in stop and g[-1] in stop:
                        continue
                    seen[" ".join(g)].add(narr)
    out = [{"phrase": g, "narrators": sorted(ns)} for g, ns in seen.items() if len(ns) >= min_narrators]
    # Prefer phrases shared by more narrators, then longer phrases.
    return sorted(out, key=lambda d: (-len(d["narrators"]), -len(d["phrase"])))[:25]


def theme_matrix(labels: dict[tuple, set], source_narrator: dict[str, str], codes: list[str]) -> dict:
    # Combine a narrator's sources into one row of theme counts, including zeros.
    m = {n: Counter() for n in dict.fromkeys(source_narrator.values())}
    for (sid, _), cs in labels.items():
        for c in cs:
            m[source_narrator[sid]][c] += 1
    return {n: {c: m[n][c] for c in codes} for n in m}
