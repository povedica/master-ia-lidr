"""Calibration constants for soft consistency and LLM-as-judge evals."""

from __future__ import annotations

# Soft consistency (multi-run live estimator)
SOFT_HOURS_VARIANCE_RATIO = 0.75
SOFT_COMPONENT_MIN_RUNS_RATIO = 2 / 3
SOFT_CONFIDENCE_DELTA = 0.15
SOFT_CONSISTENCY_RUNS = 3

# GEval metric thresholds (calibration placeholders — tune before CI gating)
SESSION_CONTEXT_USE_THRESHOLD = 0.7
SCOPE_COHERENCE_THRESHOLD = 0.7
JUSTIFICATION_QUALITY_THRESHOLD = 0.7
CONFIDENCE_CALIBRATION_THRESHOLD = 0.65
CROSS_TURN_CONSISTENCY_THRESHOLD = 0.7
COMPLETENESS_FOR_SCOPE_THRESHOLD = 0.65
