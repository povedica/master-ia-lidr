"""Guardrail-specific errors surfaced to HTTP or pipeline callers."""


class GuardrailViolationError(Exception):
    """Enforced guardrail blocked the request (maps to HTTP 422 with safe detail)."""

    def __init__(
        self,
        *,
        guardrail_id: str,
        reason_code: str,
        user_message: str,
        audit_id: str,
    ) -> None:
        super().__init__(user_message)
        self.guardrail_id = guardrail_id
        self.reason_code = reason_code
        self.user_message = user_message
        self.audit_id = audit_id
