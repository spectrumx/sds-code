from loguru import logger as log

try:
    from rich import traceback

    traceback.install()
except ImportError:
    log.warning("Install rich to get nice stacktraces.")
