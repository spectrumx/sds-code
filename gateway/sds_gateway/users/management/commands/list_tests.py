import unittest

from django.core.management.base import BaseCommand
from loguru import logger as log


class Command(BaseCommand):
    help = "List all test cases"

    def handle(self, *args, **options) -> None:
        loader = unittest.TestLoader()
        suite: unittest.TestSuite = loader.discover(".")
        test_count = 0

        def log_test_suite(suite: unittest.TestSuite, indent: int = 0) -> None:
            nonlocal test_count
            prefix = "  " * indent + "- "
            for test in suite:
                # check if this is a nested suite
                if isinstance(test, unittest.TestSuite):
                    if not test or not test._tests:  # noqa: SLF001
                        continue
                    log.info(f"{prefix}")
                    log_test_suite(test, indent=indent + 1)
                elif isinstance(test, unittest.TestCase):
                    test_count += 1
                    if isinstance(test, str):
                        log.info(f"{prefix}{test}")
                    else:
                        log.info(f"{prefix}{test._testMethodName}")  # noqa: SLF001
                else:
                    # log unknown types for debugging, but this should not happen
                    log.warning(f"{prefix}Unknown test object: {test}")

        log_test_suite(suite)
        log.info(f"Discovered {test_count} test cases.")
