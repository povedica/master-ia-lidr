"""Chunking compare tests (feature-063)."""

from __future__ import annotations

from app.embedding_pipeline.chunking_compare import compute_strategy_stats
from app.embedding_pipeline.schemas import Budget, BudgetComponent, ClientMetadata


def _sample_budget() -> Budget:
    return Budget(
        budget_id="BUD-1",
        client_metadata=ClientMetadata(name="Acme", sector="retail", country="ES"),
        project_summary="E-commerce checkout",
        main_technology="Python",
        year=2025,
        total_estimated_hours=120,
        components=[
            BudgetComponent(
                component_id="c1",
                name="Checkout",
                description="Payment flow",
                tech_stack=["stripe"],
                estimated_hours=40,
                complexity="medium",
                dependencies=[],
            )
        ],
    )


def test_compare_stats_for_three_strategies() -> None:
    budgets = [_sample_budget()]
    structural = compute_strategy_stats("structural", budgets)
    recursive = compute_strategy_stats("recursive", budgets)
    sentence = compute_strategy_stats("sentence_window", budgets)
    assert structural.chunk_count >= 1
    assert recursive.chunk_count >= structural.chunk_count
    assert sentence.chunk_count >= 1
