"""Import every module under `tsm` and fail if any raises.

Nix does not resolve Python imports while building, so a package with an
incomplete dependency list installs cleanly and only fails when a user opens
the screen that needs the missing module. Walking every module at build time
turns that into a build failure.
"""

import importlib
import pkgutil
import sys

import tsm

failures = []
for module in pkgutil.walk_packages(tsm.__path__, "tsm."):
    try:
        importlib.import_module(module.name)
    except Exception as exc:
        failures.append((module.name, type(exc).__name__, str(exc)))

if failures:
    print(f"import check failed for {len(failures)} module(s):")
    for name, exc_type, message in failures:
        print(f"  {name}: {exc_type}: {message}")
    sys.exit(1)

print("import check passed for every module under tsm")
