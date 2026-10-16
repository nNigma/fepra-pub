"""Ошибки доменных сервисов. Роуты превращают их в HTTP: status -> код, detail -> {detail}.

Сервисы про HTTP не знают: status здесь просто рекомендуемый код ответа.
"""
from __future__ import annotations


class ServiceError(Exception):
    status = 400
    code = "error"

    def __init__(self, detail: str = "", *, code: str | None = None, status: int | None = None):
        super().__init__(detail or self.code)
        self.detail = detail or self.code
        if code:
            self.code = code
        if status:
            self.status = status


class BadRequest(ServiceError):
    status = 400
    code = "bad_request"


class Forbidden(ServiceError):
    status = 403
    code = "forbidden"


class NotFound(ServiceError):
    status = 404
    code = "not_found"


class Invalid(ServiceError):
    """Данные распознаны, но не проходят проверку (422)."""
    status = 422
    code = "invalid"


class QuotaExceeded(ServiceError):
    status = 429
    code = "llm_quota"
