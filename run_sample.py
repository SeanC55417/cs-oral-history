"""End-to-end sample run:
   Drafty frame -> harvested sources -> Jev (or stub) typed extraction -> MEDFORD files -> results.json

   python run_sample.py            # stub backend unless TYPESAFE_API_KEY is set
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ohcs import analysis, sampler
from ohcs.extract import extract_passage
from ohcs.jev_backend import make_client
from ohcs.medford_writer import write_mfd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
harvest = json.loads((ROOT / "data/harvest_sample.json").read_text())
cb = json.loads((ROOT / "data/codebook.json").read_text())
CODES = list(cb["codes"])
retrieved = time.strftime("%Y-%m-%d")

# 1. sampling frame
frame = sampler.load_frame()
cohorts = Counter(f.cohort for f in frame)
sub_by_cohort = Counter((f.cohort, f.subfield) for f in frame)
suspicious = sampler.suspicious_join_years(frame)

# 2. extraction
client, model = make_client()
records, mfd_paths = [], []
for src in harvest["sources"]:
    d = sampler.match(frame, src["drafty_name"]) if src.get("drafty_name") else None
    src["_drafty"] = d.to_dict() if d else None
    recs = [extract_passage(client, model, src, i, ex) for i, ex in enumerate(src["excerpts"])]
    records.extend(recs)
    mfd_paths.append(write_mfd(src, recs, src["_drafty"], retrieved, model, OUT / "medford"))

# 3. validate every MEDFORD file with the official parser
validation = {}
for p in mfd_paths:
    r = subprocess.run([sys.executable, "-m", "ohcs.validate", str(p)], capture_output=True, text=True, cwd=ROOT)
    validation[p.name] = {0: "passed", 2: "passed (desirable-field warnings)"}.get(r.returncode, "FAILED: " + r.stdout[-400:])

# 4. analysis
narr = {s["id"]: s["narrator"] for s in harvest["sources"]}
gold = {(sid, i): set(labs) for sid, L in cb["gold"].items() if not sid.startswith("_") for i, labs in enumerate(L)}
pred = {(r.source_id, r.idx): set(r.accepted_themes) for r in records}
agree = analysis.agreement(pred, gold, CODES)
probs = [r.themes[c] for r in records for c in CODES]
labels = [int(c in gold[(r.source_id, r.idx)]) for r in records for c in CODES]
ece, reliability = analysis.expected_calibration_error(probs, labels)
by_narr = {}
for s in harvest["sources"]:
    by_narr.setdefault(s["narrator"], []).extend(e["text"] for e in s["excerpts"])

gold_rel = cb.get("gold_relations", {})
lineage = [{"narrator": narr[r.source_id], **rel, "source": r.source_id, "passage": r.idx + 1,
            "reference": gold_rel.get(r.source_id, {}).get(rel["person"])}
           for r in records for rel in r.relations]

results = {
    "generated": retrieved, "model": model,
    "frame": {"n": len(frame), "with_join_year": sum(f.join_year is not None for f in frame),
              "cohorts": dict(sorted(cohorts.items())),
              "subfields_1960s_1970s": Counter(f.subfield for f in frame if f.cohort in ("1960s", "1970s")).most_common(12),
              "suspicious_join_years": [f.to_dict() for f in suspicious]},
    "sources": [{k: v for k, v in s.items() if k != "excerpts"} | {"n_excerpts": len(s["excerpts"])}
                for s in harvest["sources"]],
    "gaps": harvest["gaps"],
    "passages": [asdict(r) | {"narrator": narr[r.source_id],
                              "gold": sorted(gold.get((r.source_id, r.idx), []))} for r in records],
    "theme_matrix_gold": analysis.theme_matrix(gold, narr, CODES),
    "theme_matrix_pred": analysis.theme_matrix(pred, narr, CODES),
    "agreement_vs_reference": agree,
    "calibration": {"ece": ece, "reliability": reliability,
                    "note": "stub scores are not probabilities; rerun with TYPESAFE_API_KEY to measure Jev calibration"},
    "routing": Counter(r.route for r in records),
    "formulas": analysis.formulas(by_narr),
    "lineage": lineage,
    "medford_validation": validation,
    "codebook": cb["codes"],
}
(OUT / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str))
print(f"model={model} passages={len(records)} mfd={len(mfd_paths)}")
print("validation:", validation)
print("agreement:", {k: v for k, v in agree.items() if k != 'per_code'}, "ECE", ece)
print("routing:", results["routing"])
