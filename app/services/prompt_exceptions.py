"""Errors raised when resolving or rendering versioned Jinja2 prompts."""


class PromptVersionError(RuntimeError):
    """Unknown prompt use case/version or invalid manifest."""


class PromptTemplateNotFound(RuntimeError):
    """A required template file is missing on disk."""


class PromptRenderError(RuntimeError):
    """Strict Jinja2 rendering failed (e.g. missing context under StrictUndefined)."""
