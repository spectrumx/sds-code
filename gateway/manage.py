#!/usr/bin/env python
import os
import sys
from pathlib import Path

from loguru import logger as log

try:
    from rich import traceback

    traceback.install()
except ImportError:
    log.warning("Install rich to get nice stacktraces.")

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as err:
        # The above import may fail for some other reason.
        # Check if the issue is a missing Django:
        try:
            from importlib.util import find_spec
        except ImportError:
            pass  # proceed raising the first import error
        else:
            if find_spec("django") is None:
                failed_django_import_msg = (
                    "Couldn't import Django. Did you forget to "
                    "activate a virtual environment?"
                )
                raise ImportError(failed_django_import_msg) from err
            # proceed raising the first import error

        raise

    # This allows easy placement of apps within the interior
    # sds_gateway directory.
    current_path = Path(__file__).parent.resolve()
    sys.path.append(str(current_path / "sds_gateway"))

    execute_from_command_line(sys.argv)
