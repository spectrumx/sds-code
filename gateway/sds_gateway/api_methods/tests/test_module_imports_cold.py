"""Cold-import safety tests for all production modules.

Regression guard against ``TypeError`` on subscriptable-type usage (e.g.
``File[Any]``) that only manifests when ``django_stubs_ext.monkeypatch()`` has
not been called.  ``config.settings.base`` does NOT call the monkeypatch; this
test suite exercises the true cold-import path for every module under
``sds_gateway/``.

The ``TypeError`` class of bugs is specific to Python 3.13+ where common
Django types like ``File`` and ``ContentFile`` are not subscriptable.  The
monkeypatch adds ``__class_getitem__`` to ``FileProxyMixin``, which masks
the issue.  In production, the monkeypatch was absent from
``config.settings.production``, so the error surfaced at import time.
"""

from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Project root directory (where ``manage.py`` lives).

SETTINGS_MODULE = "config.settings.base"
# Django settings module that does NOT call ``django_stubs_ext.monkeypatch()``.

EXPECTED_PARTS = 3
# Number of colon-delimited fields in a ``RESULT:`` line: module, status, msg.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _module_path(py_file: Path, base_dir: Path) -> str:
    """Convert a ``.py`` file path to a dotted module path relative to ``base_dir``.

    Example:
        ``sds_gateway/api_methods/utils/foo.py`` →
        ``sds_gateway.api_methods.utils.foo``
    """
    rel = py_file.relative_to(base_dir)
    parts = list(rel.parts)
    # Strip ``.py`` suffix
    parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def _collect_py_files(base_dir: Path) -> list[Path]:
    """Collect all production ``.py`` files under ``sds_gateway/``.

    Skips:
    - ``__init__.py`` files
    - Files inside ``migrations/`` directories
    - Files inside ``tests/`` directories
    - Files whose name starts with ``test_``
    """
    sds_gateway = base_dir / "sds_gateway"
    collected: list[Path] = []
    for py_file in sorted(sds_gateway.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        if "migrations" in py_file.parts:
            continue
        if "tests" in py_file.parts:
            continue
        if py_file.name.startswith("test_"):
            continue
        collected.append(py_file)
    return collected


def _run_batch(module_paths: list[str]) -> list[tuple[str, str, str]]:
    """Import *module_paths* in a single cold subprocess.

    One ``django.setup()`` per batch.  Returns ``[(module, status, msg), ...]``.
    Status is ``SUCCESS``, ``TYPEERROR``, or ``ERROR``.
    """
    code = (
        "import sys, os\n"
        f"sys.path.insert(0, {str(BASE_DIR)!r})\n"
        f'os.environ["DJANGO_SETTINGS_MODULE"] = {SETTINGS_MODULE!r}\n'
        "import django\n"
        "try:\n"
        "    django.setup()\n"
        "except Exception as e:\n"
        '    print(f"SETUP_ERROR: {e}")\n'
        "    exit(1)\n"
        "import importlib\n"
        "for _mp in " + repr(module_paths) + ":\n"
        "    try:\n"
        "        importlib.import_module(_mp)\n"
        '        print(f"RESULT:{_mp}:SUCCESS:")\n'
        "    except TypeError as e:\n"
        '        print(f"RESULT:{_mp}:TYPEERROR:{e}")\n'
        "    except Exception as e:\n"
        '        print(f"RESULT:{_mp}:ERROR:{type(e).__name__}:{e}")\n'
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,  # we're checking it below
    )

    # If subprocess crashed entirely and produced no RESULT lines, bail fast.
    if result.returncode != 0 and "RESULT:" not in result.stdout:
        msg = (
            f"Batch subprocess crashed (exit={result.returncode}): "
            f"{result.stderr[:500]}"
        )
        raise RuntimeError(msg)

    parsed: list[tuple[str, str, str]] = []
    for line in result.stdout.strip().splitlines():
        if line.startswith("RESULT:"):
            parts = line.split(":", 3)
            module = parts[1]
            status = parts[2]
            msg = parts[3] if len(parts) > EXPECTED_PARTS else ""
            parsed.append((module, status, msg))
    return parsed


# ---------------------------------------------------------------------------
# Collect all production modules at collection time
# ---------------------------------------------------------------------------

_PY_FILES = _collect_py_files(BASE_DIR)
_MODULE_PATHS = [_module_path(f, BASE_DIR) for f in _PY_FILES]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_cold_import_no_type_error() -> None:
    """Cold-import all production modules — fail on ``TypeError``, warn on others."""
    n_workers = max(1, min(os.cpu_count() or 1, 8))
    batches: list[list[str]] = [[] for _ in range(n_workers)]
    for i, mod in enumerate(_MODULE_PATHS):
        batches[i % n_workers].append(mod)

    all_results: list[tuple[str, str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(_run_batch, b) for b in batches if b]
        for future in concurrent.futures.as_completed(futures):
            all_results.extend(future.result())

    type_errors = [(m, msg) for m, s, msg in all_results if s == "TYPEERROR"]
    other_errors = [(m, msg) for m, s, msg in all_results if s == "ERROR"]

    if type_errors:
        pytest.fail(
            f"{len(type_errors)} module(s) raised TypeError on cold import:\n"
            + "\n".join(f"  {m}: {msg}" for m, msg in type_errors)
        )

    for module, msg in other_errors:
        if "ImproperlyConfigured" not in msg and "EnvError" not in msg:
            warnings.warn(f"Unexpected import error in {module}: {msg}", stacklevel=2)
