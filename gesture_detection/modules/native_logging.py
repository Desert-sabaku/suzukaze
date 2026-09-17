"""Small helpers for third-party libraries that write directly to file descriptor 2."""

import os
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def suppress_native_stderr(enabled: bool = True) -> Iterator[None]:
    """Temporarily silence native stderr while preserving Python exceptions.

    MediaPipe/Abseil writes initialization diagnostics below Python's logging
    layer, so neither ``logging`` nor ``redirect_stderr`` can control them.
    Restricting the redirection to initialization/first inference avoids hiding
    diagnostics during the rest of the worker's lifetime.
    """
    if not enabled:
        yield
        return

    saved_stderr = os.dup(2)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        os.dup2(saved_stderr, 2)
        os.close(saved_stderr)
