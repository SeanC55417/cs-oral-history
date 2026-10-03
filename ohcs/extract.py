"""Passage-level extraction: deterministic candidates -> Jev typed decisions -> routed records."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from typesafe_sdk import Choice

from .questions import passage_questions, relation_question

# Accept high theme scores, review middle scores, and omit scores at or below 0.30.
NOUL_ACCEPT, NOUL_REJECT = 0.80, 0.30
CHOICE_ACCEPT = 0.60  # Minimum confidence used for era and relationship routing.

ENTITY_TYPES = {
    "person": "A specific human being",
    "organization": "A company, university, agency, or lab",
    "place": "A city, country, or region",
    "artifact": "A computer, system, language, book, paper, or film",
    "other": "Anything else (a word capitalised only because it starts a sentence, etc.)",
}

# Small lists of known names used only by the offline entity classifier.
_ORG = r"^(Brown|Swarthmore|UCLA|MIT|Mitre|DARPA|ARPA|NSF|IBM|Stanford|Carnegie Mellon|Harvard|City College|Robotics Institute|Mathematical Centre|Time Magazine|Computer History Museum|Internet)$"
_PLACE = r"^(India|Chennai|New York|Cambridge|Pittsburgh)$"
_ART = r"^(HES|FRES|FRESS|FORTRAN|Venus|CLU|Argus|PDP-1|IMP|ALGOL|EWD249|Communication Nets|Harvard Mark I|Notes on Structured Programming|The Wheel of Reincarnation|Wheel of Reincarnation|Harvard Mark|Harvard Mark I|Liskov|Evening Session program|Summer School|Electrical Engineering|Evening Session)$"
_STOP = {"I", "The", "So", "In", "He", "It", "And", "Why", "That", "There", "What", "Since", "When", "Brown", "Everything",
         "Was", "Most", "Making", "No", "By", "A", "But", "You", "Larry", "Engineering", "September", "August", "John", "Why", "Consider"}


@dataclass
class PassageRecord:
    # Bundle one excerpt with its labels, scores, and links to the original source.
    source_id: str
    idx: int  # Zero-based position in the source's excerpt list.
    text: str
    page: str
    years: str
    themes: dict[str, float] = field(default_factory=dict)     # Theme code -> model score.
    accepted_themes: list[str] = field(default_factory=list)
    review_themes: list[str] = field(default_factory=list)
    is_recollection: float = 0.0
    era: str = ""
    era_conf: float = 0.0
    function: str = ""
    function_conf: float = 0.0
    specificity: float = 0.0
    affect: float = 0.0
    relations: list[dict] = field(default_factory=list)
    route: str = "accept"
    model: str = ""


def name_candidates(text: str, narrator: str) -> list[str]:
    """Capitalised spans (1-3 tokens). High recall on purpose; Jev decides which are people."""
    spans = re.findall(r"\b([A-Z][a-zA-Z\-]+(?:\s+(?:[A-Z][a-zA-Z\-]+|of|on))*(?:\s+[A-Z][a-zA-Z\-]+)?)", text)
    # Capitalization gives possible names; entity classification filters them later.
    out = []
    for s in spans:
        toks = s.split()
        while toks and (toks[0] in _STOP or toks[0] in {"of", "on"}):   # "Since Newell" -> "Newell"
            toks = toks[1:]
        while toks and toks[-1] in {"of", "on"}:
            toks = toks[:-1]
        s = " ".join(toks)
        # Remove obvious noise, acronyms, and text already contained in the narrator's name.
        if not s or s in narrator or len(s) < 3 or s.isupper() or re.search(r"[0-9]|-$|^[A-Z]-", s):
            continue
        if s not in out:
            out.append(s)
    # Expand two fixed first-name aliases used in the sample transcripts.
    for first, full in {"Larry": "Lawrence Roberts", "John": "John McCarthy"}.items():
        if re.search(rf"\b{first}\b", text) and full not in out:
            out.append(full)
    # drop surnames subsumed by a full name in the same passage ("McCarthy" vs "John McCarthy")
    return [c for c in out if not any(o != c and o.endswith(" " + c) for o in out)]


def _entity_type_stub(c: str) -> str:
    # The offline fallback uses small lookup lists instead of a model call.
    if re.match(_ORG, c):
        return "organization"
    if re.match(_PLACE, c):
        return "place"
    if re.match(_ART, c):
        return "artifact"
    return "person" if len(c.split()) >= 1 and c[0].isupper() else "other"


def extract_passage(client, model: str, source: dict, idx: int, ex: dict) -> PassageRecord:
    # Give every passage question the same excerpt and source context.
    state = {"narrator": source["narrator"], "source_type": source["source_type"],
             "interview_date": source.get("date"), "years_hint": ex.get("years"), "passage": ex["text"]}
    resp = client.system_one(state=state, questions=passage_questions())
    a = resp.answers
    # Preserve the original text and citation details alongside the decisions.
    rec = PassageRecord(source_id=source["id"], idx=idx, text=ex["text"], page=ex.get("p", ""),
                        years=ex.get("years", ""), model=resp.model)
    for k, v in a.items():
        if k.startswith("theme__"):
            code = k[len("theme__"):]  # Remove the question prefix to recover the codebook key.
            rec.themes[code] = v.noul
            if v.noul >= NOUL_ACCEPT:
                rec.accepted_themes.append(code)
            elif v.noul > NOUL_REJECT:
                rec.review_themes.append(code)
    # Copy the remaining typed answers into fields used by MEDFORD and the report.
    rec.is_recollection = a["is_recollection"].noul
    rec.era, rec.era_conf = a["era"].choice, a["era"].confidence
    rec.function, rec.function_conf = a["narrative_function"].choice, a["narrative_function"].confidence
    rec.specificity, rec.affect = a["specificity"].score, a["affect"].score

    # --- entities & lineage: one batched call types every candidate, one per person classifies relation
    cands = name_candidates(ex["text"], source["narrator"])
    if cands:
        if model.startswith("heuristic"):
            types = {c: _entity_type_stub(c) for c in cands}
        else:
            et = client.system_one(state=state, questions={
                f"type__{i}": Choice(instructions=f"What kind of entity is '{c}' in this passage?", criteria=ENTITY_TYPES)
                for i, c in enumerate(cands)}).answers
            types = {c: et[f"type__{i}"].choice for i, c in enumerate(cands)}
        # Only people receive a relationship question; organizations and objects do not.
        for c in [c for c in cands if types[c] == "person"]:
            r = client.system_one(state={**state, "person": c}, questions=relation_question()).answers["relation"]
            rec.relations.append({"person": c, "relation": r.choice, "confidence": r.confidence,
                                  "route": "accept" if r.confidence >= CHOICE_ACCEPT else "review"})

    # Flag the whole passage when themes or the era need review; relations route separately.
    if rec.review_themes or rec.era_conf < CHOICE_ACCEPT or not rec.accepted_themes:
        rec.route = "review"
    return rec
