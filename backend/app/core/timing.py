"""
Lightweight request-phase timing. There was previously zero visibility into
where chat-response latency actually goes (see backend/PERFORMANCE_AUDIT.md),
so this exists as a small, dependency-free way to log a duration_ms line per
named phase instead of guessing.
"""
import time
from contextlib import contextmanager
from loguru import logger


@contextmanager
def phase(name: str, **context):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        ctx = " ".join(f"{k}={v}" for k, v in context.items())
        logger.info(f"[timing] {name} duration_ms={duration_ms:.1f} {ctx}".rstrip())
