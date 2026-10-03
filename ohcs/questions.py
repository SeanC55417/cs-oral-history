"""Typed question sets for Jev (TypeSafe System One).

Design rules taken from TypeSafe's docs:
  * one atomic, few-second judgement per question; decompose anything that needs reasoning
  * all questions in a call are evaluated in parallel and in isolation against the same state,
    so multi-label theme coding = one Noul per code in a single call (no context rot)
  * Jev cannot write text: spans (quotes, names, dates) come from deterministic candidate
    generation, and Jev *chooses / scores / verifies* those candidates.
"""
from __future__ import annotations

import json
from pathlib import Path

from typesafe_sdk import Choice, Noul, Score

# Read theme definitions from the shared codebook so prompts use the same labels.
CODEBOOK = json.loads((Path(__file__).resolve().parent.parent / "data" / "codebook.json").read_text())["codes"]

# Dictionary keys are saved labels; the descriptions explain each choice to Jev.
ERAS = {
    "pre_1950": "Events before 1950", "1950s": "Events in the 1950s", "1960s": "Events in the 1960s",
    "1970s": "Events in the 1970s", "1980s": "Events in the 1980s", "1990s": "Events in the 1990s",
    "2000_plus": "Events in 2000 or later", "timeless": "Not about a specific time (general reflection)",
}

NARRATIVE_FUNCTION = {
    "origin_story": "How the speaker got started or first arrived somewhere",
    "turning_point": "A decision or event that changed the direction of a career or the field",
    "building": "Creating something lasting: a department, lab, system, or language",
    "anecdote": "A specific story about another person or a memorable moment",
    "context": "Background facts: dates, jobs, funding arrangements",
    "reflection": "Looking back and judging, or stating a lesson",
}


def passage_questions() -> dict:
    """Asked of every passage. State = {narrator, source_type, interview_date, passage}."""
    # A separate yes/no-style question lets one passage receive several themes.
    q = {f"theme__{k}": Noul(instructions=v) for k, v in CODEBOOK.items()}
    # Choice selects one label; Score uses the ordered descriptions as a scale.
    q.update({
        "is_recollection": Noul(instructions="The speaker is recalling their own past experience, in the first person."),
        "era": Choice(instructions="When did the events described in the passage take place?", criteria=ERAS),
        "narrative_function": Choice(instructions="What role does this passage play in the speaker's story?",
                                     criteria=NARRATIVE_FUNCTION),
        "specificity": Score(instructions="How historically specific is the passage?", criteria=[
            "Vague: no names, dates, places, or systems",
            "Some concrete detail",
            "Specific: names people, dates, places or systems"]),
        "affect": Score(instructions="The speaker's attitude toward what they describe", criteria=[
            "Critical or regretful", "Neutral, matter-of-fact", "Admiring, delighted, or nostalgic"]),
    })
    return q


# Relationships are described from the narrator's point of view.
RELATION = {
    "advisor_or_mentor": "The person taught, advised, or mentored the narrator",
    "student_or_mentee": "The narrator taught, advised, or supervised the person",
    "peer_colleague": "A colleague or collaborator at a similar level",
    "funder_or_patron": "The person controlled money, jobs, or institutional support for the narrator",
    "influence": "The narrator was inspired by the person's work without working for them",
    "other": "None of the above, or the person is only mentioned in passing",
}


def relation_question() -> dict:
    """State = {narrator, passage, person}. Person names come from candidate extraction."""
    # Classify a name already found in the text; this question does not find names.
    return {"relation": Choice(instructions="How is `person` related to the narrator in this passage?", criteria=RELATION)}


SOURCE_KIND = {
    "oral_history_transcript": "An interview transcript with question/answer turns",
    "faculty_homepage": "A personal or faculty web page",
    "memoir_essay": "A first-person essay or memoir written by the subject",
    "forum_thread": "A discussion thread (Reddit, Hacker News, mailing list)",
    "video": "A video transcript or video page",
    "paper": "A research or history paper written in the third person",
    "obituary_or_profile": "An obituary, news profile or encyclopedia entry about the person",
}


def triage_questions() -> dict:
    """Asked of every crawled page before extraction. State = {url, title, text[:6000]}."""
    # These page-screening questions are available for a future collection run.
    return {
        "source_kind": Choice(instructions="What kind of document is this?", criteria=SOURCE_KIND),
        "first_person": Noul(instructions="Most of the text is written or spoken in the first person by the subject."),
        "about_cs_history": Noul(instructions="The document contains recollections about the history of computing or computer science."),
        "usefulness": Score(instructions="How useful is this document as a primary source for an oral history of computer science?",
                            criteria=["Not useful", "Marginal (mentions only)", "Useful (some recollection)",
                                      "Rich primary source (extended first-person memory)"]),
    }


def faculty_row_questions() -> dict:
    """State = one Drafty row. Flags data problems in the sampling frame."""
    # A low score would flag a row for checking, not change its recorded year.
    return {"join_year_plausible": Noul(
        instructions="The JoinYear is plausible for when this person joined this university as faculty.")}
