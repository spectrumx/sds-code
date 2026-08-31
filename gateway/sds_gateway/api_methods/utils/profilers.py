"""Profiler wrappers to check resource usage."""

import functools
import tracemalloc

from loguru import logger


def profile_memory(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tracemalloc.start()
        result = func(*args, **kwargs)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        logger.info(
            f"[Memory Profiler] {func.__name__} Current: {current / 10**6:.2f} MB"
        )
        logger.info(f"[Memory Profiler] {func.__name__} Peak: {peak / 10**6:.2f} MB")
        return result

    return wrapper
