"""DeepEval GEval metrics for session estimation quality."""

from __future__ import annotations

from deepeval.metrics import GEval
from deepeval.test_case.llm_test_case import SingleTurnParams

from tests.evals import thresholds as t
from tests.evals.judge.config import JudgeConfig

_EVAL_PARAMS = [
    SingleTurnParams.INPUT,
    SingleTurnParams.ACTUAL_OUTPUT,
    SingleTurnParams.CONTEXT,
]

_SESSION_CONTEXT_USE_CRITERIA = """
You are evaluating a software estimation assistant that runs in multi-turn sessions.

The model received prior user turns and accumulated project metadata before producing
the final structured estimate.

Score HIGH when the final estimate clearly reflects prior turns: added scope (e.g. Redis),
technology choices, team size, integrations, and explicit rejections from earlier turns.

Score LOW when the estimate ignores prior turns, contradicts accumulated metadata,
or reads as a generic one-shot estimate unrelated to session history.

Penalize reintroduction of technologies or scope items listed under rejected_options
or explicit_constraints in the metadata.
""".strip()

_SCOPE_COHERENCE_CRITERIA = """
Evaluate whether line items, phases, hours, and duration align with the merged session
scope, project type, and category (small vs large). Score HIGH when effort and components
match the described integrations and constraints. Score LOW for generic or mismatched scope.
""".strip()

_JUSTIFICATION_QUALITY_CRITERIA = """
Evaluate summary, assumptions, and risks for clarity, actionability, and tie-in to scope.
Score HIGH when risks name concrete integration/compliance concerns from the session.
Score LOW for vague boilerplate unrelated to the transcript and metadata.
""".strip()

_CONFIDENCE_CALIBRATION_CRITERIA = """
Evaluate whether stated confidence matches ambiguity, contradictions, and risk level in the
session. Score HIGH when confidence is lower for ambiguous or integration-heavy scope.
Score LOW when confidence is extreme despite clear uncertainty signals.
""".strip()

_CROSS_TURN_CONSISTENCY_CRITERIA = """
Evaluate whether the final estimate contradicts accumulated metadata or prior turns,
especially rejected technologies or explicit constraints. Score HIGH when consistent;
score LOW when rejected options reappear in line items, summary, or assumptions.
""".strip()

_COMPLETENESS_FOR_SCOPE_CRITERIA = """
Evaluate coverage relative to project category and described scope. Small MVPs should not
be wildly over-scoped; large integration projects should not omit major mentioned systems.
Score HIGH for reasonable coverage; LOW for obvious gaps or inflation.
""".strip()


def build_session_eval_metrics(config: JudgeConfig) -> list[GEval]:
    """Return all GEval metrics configured for the judge model."""

    model = config.litellm_model
    return [
        GEval(
            name="SessionContextUse",
            criteria=_SESSION_CONTEXT_USE_CRITERIA,
            evaluation_params=_EVAL_PARAMS,
            threshold=t.SESSION_CONTEXT_USE_THRESHOLD,
            model=model,
        ),
        GEval(
            name="ScopeCoherence",
            criteria=_SCOPE_COHERENCE_CRITERIA,
            evaluation_params=_EVAL_PARAMS,
            threshold=t.SCOPE_COHERENCE_THRESHOLD,
            model=model,
        ),
        GEval(
            name="JustificationQuality",
            criteria=_JUSTIFICATION_QUALITY_CRITERIA,
            evaluation_params=_EVAL_PARAMS,
            threshold=t.JUSTIFICATION_QUALITY_THRESHOLD,
            model=model,
        ),
        GEval(
            name="ConfidenceCalibration",
            criteria=_CONFIDENCE_CALIBRATION_CRITERIA,
            evaluation_params=_EVAL_PARAMS,
            threshold=t.CONFIDENCE_CALIBRATION_THRESHOLD,
            model=model,
        ),
        GEval(
            name="CrossTurnConsistency",
            criteria=_CROSS_TURN_CONSISTENCY_CRITERIA,
            evaluation_params=_EVAL_PARAMS,
            threshold=t.CROSS_TURN_CONSISTENCY_THRESHOLD,
            model=model,
        ),
        GEval(
            name="CompletenessForScope",
            criteria=_COMPLETENESS_FOR_SCOPE_CRITERIA,
            evaluation_params=_EVAL_PARAMS,
            threshold=t.COMPLETENESS_FOR_SCOPE_THRESHOLD,
            model=model,
        ),
    ]
