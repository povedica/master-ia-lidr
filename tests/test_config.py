"""Settings loading tests."""

import pytest

import app.config as app_config
from app.config import Settings, get_settings


def test_default_env_file_is_beside_app_package() -> None:
    """`.env` is anchored to the service root, not the process CWD."""
    root = app_config._APP_ROOT
    assert (root / "app" / "main.py").is_file()
    assert app_config._DEFAULT_ENV_FILE == root / ".env"


def test_settings_reads_openai_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test-model")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.openai_model == "gpt-test-model"


def test_get_settings_cached_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test-env")
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    assert first.app_env == "test-env"


def test_optional_anthropic_fields_have_safe_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_TIMEOUT_SECONDS", raising=False)
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.anthropic_api_key == ""
    assert settings.anthropic_model == "claude-haiku-4-5-20251001"
    assert settings.anthropic_timeout_seconds == 30.0
    assert settings.estimation_output_tokens_max == 2048


def test_estimation_output_tokens_max_can_be_overridden_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESTIMATION_OUTPUT_TOKENS_MAX", "3000")
    get_settings.cache_clear()
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    assert settings.estimation_output_tokens_max == 3000


def test_provider_chain_defaults() -> None:
    settings = Settings(
        _env_file=None,
        llm_auth_fallback=False,
        estimation_output_persist_enabled=False,
        estimation_stats_log_enabled=False,
    )
    assert settings.llm_providers == "openai,anthropic"
    assert settings.static_fallback_enabled is True
    assert settings.llm_auth_fallback is False
    assert settings.llm_domain_guardrail_enabled is True
    assert settings.estimation_output_persist_enabled is False


def test_domain_guardrail_can_be_disabled_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DOMAIN_GUARDRAIL_ENABLED", "false")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.llm_domain_guardrail_enabled is False


def test_estimation_output_persist_can_be_enabled_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESTIMATION_OUTPUT_PERSIST_ENABLED", "true")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.estimation_output_persist_enabled is True


def test_llm_call_persist_can_be_enabled_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_CALL_PERSIST_ENABLED", "true")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.llm_call_persist_enabled is True


def test_default_llm_provider_and_model_have_documented_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEFAULT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    assert settings.default_llm_provider == "unset"
    assert settings.default_llm_model == "openai/gpt-4o-mini"
    assert settings.gemini_api_key == ""


def test_default_llm_model_can_be_overridden_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEFAULT_LLM_MODEL", "anthropic/claude-haiku-4-5-20251001")
    get_settings.cache_clear()
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    assert settings.default_llm_model == "anthropic/claude-haiku-4-5-20251001"


def test_openai_litellm_model_id_prefixes_short_model_names() -> None:
    settings = Settings(_env_file=None, openai_api_key="sk-test", openai_model="gpt-4o-mini")
    assert settings.openai_litellm_model_id() == "openai/gpt-4o-mini"


def test_frontend_origins_list_default_includes_local_vite_dev_servers() -> None:
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    assert settings.frontend_origins_list() == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_frontend_origins_list_parses_comma_separated_env_style_string() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        frontend_origins="http://a.example:3000, http://b.example:3000 ,",
    )
    assert settings.frontend_origins_list() == [
        "http://a.example:3000",
        "http://b.example:3000",
    ]


def test_frontend_origins_list_empty_when_blank() -> None:
    settings = Settings(_env_file=None, openai_api_key="sk-test", frontend_origins="  ,  ")
    assert settings.frontend_origins_list() == []


def test_openai_litellm_model_id_passthrough_when_already_prefixed() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        openai_model="openai/custom-model",
    )
    assert settings.openai_litellm_model_id() == "openai/custom-model"


def test_anthropic_litellm_model_id_prefixes_short_model_names() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="ak-test", anthropic_model="claude-haiku-4-5-20251001")
    assert settings.anthropic_litellm_model_id() == "anthropic/claude-haiku-4-5-20251001"


def test_acb_defaults_disabled_for_session_endpoint() -> None:
    settings = Settings(_env_file=None, acb_enabled=False)
    assert settings.acb_enabled is False
    assert settings.acb_active_for_endpoint("session_estimate") is True
    assert settings.acb_requested(None, endpoint="session_estimate") is False


def test_acb_requested_honors_override_and_single_pass_escape() -> None:
    settings = Settings(_env_file=None, acb_enabled=True)
    assert settings.acb_requested("acb", endpoint="session_estimate") is True
    assert settings.acb_requested("single_pass", endpoint="session_estimate") is False


def test_acb_force_enabled_in_dev_when_local() -> None:
    settings = Settings(
        _env_file=None,
        acb_enabled=False,
        acb_force_enabled_in_dev=True,
        dev_mode=True,
        app_env="local",
    )
    assert settings.acb_requested(None, endpoint="session_estimate") is True


def test_embedding_pipeline_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.embedding_pipeline_model == "text-embedding-3-small"
    assert settings.embedding_pipeline_batch_size == 100


def test_embedding_pipeline_settings_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PIPELINE_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDING_PIPELINE_BATCH_SIZE", "50")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.embedding_pipeline_model == "text-embedding-3-large"
    assert settings.embedding_pipeline_batch_size == 50


def test_settings_reads_database_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = "postgresql+asyncpg://estimator:estimator@postgres:5432/estimator"
    monkeypatch.setenv("DATABASE_URL", dsn)
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.database_url == dsn


def test_database_url_defaults_to_empty_string() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url == ""


def test_retrieval_settings_defaults_are_backward_compatible() -> None:
    settings = Settings(_env_file=None)
    assert settings.retrieval_default_mode == "A"
    assert settings.retrieval_lexical_text_search_config == "spanish"
    assert settings.retrieval_recall_k == 50
    assert settings.retrieval_top_k_final == 5
    assert settings.retrieval_rrf_k == 60
    assert settings.retrieval_rerank_enabled is False
    assert settings.retrieval_rerank_model == ""


def test_retrieval_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_DEFAULT_MODE", "D")
    monkeypatch.setenv("RETRIEVAL_LEXICAL_TEXT_SEARCH_CONFIG", "english")
    monkeypatch.setenv("RETRIEVAL_RECALL_K", "40")
    monkeypatch.setenv("RETRIEVAL_TOP_K_FINAL", "10")
    monkeypatch.setenv("RETRIEVAL_RRF_K", "80")
    monkeypatch.setenv("RETRIEVAL_RERANK_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.retrieval_default_mode == "D"
    assert settings.retrieval_lexical_text_search_config == "english"
    assert settings.retrieval_recall_k == 40
    assert settings.retrieval_top_k_final == 10
    assert settings.retrieval_rrf_k == 80
    assert settings.retrieval_rerank_enabled is True
    assert settings.retrieval_rerank_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
