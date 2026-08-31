"""Profiler wrappers to check resource usage.
To use, import the decorator as such:
from sds_gateway.api_methods.utils.profilers import profile_memory
Then annotate functions to profile with @profile_memory"""

import functools
import threading
import tracemalloc

from loguru import logger

_tracemalloc_lock = threading.Lock()


def profile_memory(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _tracemalloc_lock:
            owns_tracing = not tracemalloc.is_tracing()

            if owns_tracing:
                tracemalloc.start()

            try:
                return func(*args, **kwargs)
            finally:
                current, peak = tracemalloc.get_traced_memory()

                if owns_tracing and tracemalloc.is_tracing():
                    tracemalloc.stop()

                logger.info(
                    "[Memory Profiler] {} Current: {:.2f} MB",
                    func.__name__,
                    current / 10**6,
                )
                logger.info(
                    "[Memory Profiler] {} Peak: {:.2f} MB",
                    func.__name__,
                    peak / 10**6,
                )

    return wrapper
