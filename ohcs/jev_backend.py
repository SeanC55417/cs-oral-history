"""Client factory. Same SDK code path in both modes:

  * real:  TYPESAFE_API_KEY set  -> TypeSafeClient() calls POST https://api.typesafe.ai/v1/systemone (model jev-latest)
  * stub:  no key                -> TypeSafeClient(transport=MockTransport(stub)) answers with a transparent
                                    keyword heuristic in the exact Jev response shape.

The stub exists only so the pipeline, MEDFORD output and report can be built and tested
before an API key is available. Its numbers are NOT calibrated probabilities.
"""
from __future__ import annotations

import json
import math
import os
import re

import httpx2
from typesafe_sdk import TypeSafeClient

STUB_MODEL = "heuristic-stub-0.1"

# keyword cues per question key (lower-case regex fragments)
CUES = {
    "theme__first_encounter": r"first (day|time|introduc|saw|job)|read in|introduced to|when i saw|decks of punched|vacuum tube|what i wanted to do",
    "theme__mentorship_lineage": r"\b(john|aiken|mccarthy|newell|simon|engelbart|wilkes|wheeler|gill|advis|mentor|worked for me|working with)\b",
    "theme__institution_building": r"department|institute|position|hired|moved to|started the|committee|tracks in|school|joined",
    "theme__funding_patronage": r"darpa|arpa|nsf|grant|funded|support|money|dollars",
    "theme__technical_breakthrough": r"network|language|abstraction|operating system|imp\b|byte|console|implementation|algol|models|computer (i|we) developed|idea",
    "theme__identity_belonging": r"\bgirls?\b|women|woman|born in|village|evening session|only one|immigra",
    "theme__profession_formation": r"programmer|profession|intellectual challenge|to teach computer science|discipline|physicist",
    "theme__teaching_students": r"undergraduate|students?|kids|course|teach|classes",
    "theme__reflection_legacy": r"today|looking back|caught fire|great experiment|wheel of reincarnation|understood|arguments about|the most important",
    "theme__serendipity": r"out of nowhere|don't even remember|bootleg|by chance|accident|asked me this question|changed my life",
    "is_recollection": r"\bi\b|\bwe\b|\bme\b|\bmy\b",
}


def _sig(x: float) -> float:
    # Map a keyword score into the 0-to-1 range; this does not calibrate it.
    return 1 / (1 + math.exp(-x))


def _state_text(state) -> str:
    # Accept either plain text or the structured context sent by the extractor.
    if isinstance(state, dict):
        return str(state.get("passage") or state.get("text") or json.dumps(state))
    return str(state)


def _years(text: str) -> list[int]:
    # Recognize four-digit years from 1900 through 2029 for the stub's era choice.
    return [int(y) for y in re.findall(r"\b(19[0-9]{2}|20[0-2][0-9])\b", text)]


def stub_answer(key: str, q: dict, state) -> dict:
    # Return the answer shape expected by the SDK for this question type.
    text = _state_text(state).lower()
    if q["type"] == "noul":
        # More matching keyword cues produce a higher yes/no-style score.
        cue = CUES.get(key)
        hits = len(re.findall(cue, text)) if cue else 0
        return {"type": "noul", "noul": round(_sig(2.5 * hits - 1.0), 3)}
    if q["type"] == "choice":
        # Start each option equally, then add evidence from dates or matching words.
        opts = list(q["criteria"])
        logits = {o: 0.0 for o in opts}
        if key == "era":
            ys = _years(text) or (_years(str(state.get("years_hint", ""))) if isinstance(state, dict) else [])
            for y in ys:
                o = "pre_1950" if y < 1950 else ("2000_plus" if y >= 2000 else f"{y // 10 * 10}s")
                logits[o] = logits.get(o, 0) + 2.0
            if not ys:
                logits["timeless"] = 1.0
        else:
            for o in opts:
                words = re.findall(r"[a-z]{5,}", (o + " " + str(q["criteria"][o] or "")).lower())
                logits[o] = 0.4 * sum(w[:6] in text for w in words)
        # Normalize the option weights so they sum to approximately one after rounding.
        z = sum(math.exp(v) for v in logits.values())
        probs = {o: round(math.exp(v) / z, 3) for o, v in logits.items()}
        best = max(probs, key=probs.get)
        ranked = sorted(probs.values(), reverse=True)
        # The stub defines confidence as the gap between the top two choices.
        conf = round(ranked[0] - (ranked[1] if len(ranked) > 1 else 0), 3)
        return {"type": "choice", "choice": best, "confidence": conf, "probabilities": probs}
    if q["type"] == "score":
        # Choose a scale position using detail counts or positive/negative wording.
        n = len(q["criteria"])
        feats = len(_years(text)) + len(re.findall(r"\b[A-Z][a-z]+\b", _state_text(state)))
        if "attitude" in (q.get("instructions") or ""):
            pos = len(re.findall(r"wonderful|marvelous|great|beautiful|impressive|mind-blowing|good thing|having a ball", text))
            neg = len(re.findall(r"cannot|skeptical|only one|fraction", text))
            center = 1 + (1 if pos > neg else -1 if neg > pos else 0)
        else:
            center = min(n - 1, feats // 3)
        # Build an illustrative distribution around that position for the SDK response.
        probs = {str(i): 0.0 for i in range(n)}
        probs[str(center)] = 0.7
        for j in (center - 1, center + 1):
            if 0 <= j < n:
                probs[str(j)] += 0.3 / (2 if 0 < center < n - 1 else 1)
        return {"type": "score", "score": float(center), "confidence": 0.4,
                "legend": {str(i): c for i, c in enumerate(q["criteria"])}, "probabilities": probs}
    raise ValueError(q["type"])


def _handler(request: httpx2.Request) -> httpx2.Response:
    # Answer the SDK's request locally in the same JSON shape as an API response.
    body = json.loads(request.content)
    answers = {k: stub_answer(k, q, body["state"]) for k, q in body["questions"].items()}
    return httpx2.Response(200, json={"model": STUB_MODEL, "answers": answers,
                                      "usage": {"input_tokens": len(json.dumps(body)) // 4, "output_tokens": 0}})


def make_client() -> tuple[TypeSafeClient, str]:
    # A configured key selects the live API; otherwise requests stay in the mock transport.
    if os.environ.get("TYPESAFE_API_KEY"):
        return TypeSafeClient(), "jev-latest"
    return TypeSafeClient(api_key="stub", transport=httpx2.MockTransport(_handler)), STUB_MODEL
