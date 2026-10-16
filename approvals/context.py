from contextlib import contextmanager
from contextvars import ContextVar

_writing = ContextVar("approval_internal_write", default=False)
_execution = ContextVar("approval_execution", default=None)


@contextmanager
def internal_write():
    token = _writing.set(True)
    try:
        yield
    finally:
        _writing.reset(token)
