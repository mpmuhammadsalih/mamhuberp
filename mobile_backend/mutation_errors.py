"""Map mutation exceptions to HTTP responses (busy lock / validation)."""

from __future__ import annotations

from mobile_backend.operation_lock import OperationBusyError
from mobile_backend.utils.response import failure


def failure_from_mutation_exc(exc: BaseException, *, fallback: str = "Request failed."):
    if isinstance(exc, OperationBusyError):
        return failure(str(exc) or "A save is already in progress.", status_code=423)
    if isinstance(exc, ValueError):
        return failure(str(exc), status_code=400)
    return failure(str(exc) or fallback, status_code=400)
