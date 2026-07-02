"""Unit tests for a few cogtide.models pydantic schemas.

Round-trip (model_dump -> reconstruct) checks, polymorphic coercion via
QuestionDossier.from_normalized, and the extra='forbid' guard. Pure model
logic; no network, no filesystem.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cogtide.models import (
    IdeaScorecard,
    QuestionDossier,
    ReviewerCalibrationRecord,
)


def test_question_dossier_round_trip():
    d = QuestionDossier(
        original_question="q",
        clarified_question="cq",
        core_question="core",
        target_phenomenon="tp",
        why_it_matters="w",
        scope="s",
        constraints=["c1", "c2"],
        consolidated_summary="cs",
    )
    d2 = QuestionDossier(**d.model_dump())
    assert d2 == d


def test_question_dossier_from_normalized_coerces_polymorphic_fields():
    d = QuestionDossier.from_normalized({
        "clarified_question": ["part a", "part b"],  # list -> joined string
        "constraints": "single",                     # scalar -> list
        "core_question": "core",
        "consolidated_summary": "summary",
    })
    assert d.clarified_question == "part a, part b"
    assert d.constraints == ["single"]
    # Unspecified required strings default to empty strings, not errors.
    assert d.original_question == ""
    assert d.scope == ""


def test_question_dossier_forbids_extra_fields():
    with pytest.raises(ValidationError):
        QuestionDossier(
            original_question="q",
            clarified_question="cq",
            core_question="core",
            target_phenomenon="tp",
            why_it_matters="w",
            scope="s",
            consolidated_summary="cs",
            bogus_field="nope",
        )


def test_idea_scorecard_round_trip():
    sc = IdeaScorecard(
        idea_id="I001",
        quality_score=7.5,
        unexpected_support=1.2,
        is_underrated=True,
        reviewer_ids=["R1", "R2"],
        n_reviews=2,
    )
    sc2 = IdeaScorecard(**sc.model_dump())
    assert sc2 == sc


def test_reviewer_calibration_record_round_trip():
    rec = ReviewerCalibrationRecord(
        reviewer_id="R1",
        run_id="run_x",
        quality_prediction_error=0.75,
        calibration_score=0.9,
        calibration_weight=0.95,
    )
    rec2 = ReviewerCalibrationRecord(**rec.model_dump())
    assert rec2 == rec
