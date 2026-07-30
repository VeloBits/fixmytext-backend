"""Dump the merged OpenAPI schema for all services to stdout (or a file).

The backend is four FastAPI services (see services/*), each with its own
``main.py``. This script dumps each service's schema in an isolated
subprocess (their module trees share names like ``app`` and ``main``, so
they cannot be imported side by side) and merges them into the single spec
the frontend generates its TypeScript types from.

Usage (from the backend repo root):
    python scripts/dump_openapi.py                 # merged spec → stdout
    python scripts/dump_openapi.py openapi.json    # merged spec → file

Merge rules (deterministic - same input always yields the same file):
- Services merge in the fixed order below; path/schema insertion order is
  preserved so regenerated output diffs stay minimal.
- /health and /health/ready differ per service; one canonical copy (from
  the last service) is kept, positioned after all API paths.
- Duplicate schema names are tolerated only when structurally identical
  (descriptions/examples ignored - ai-svc re-declares text-svc's models
  without docstrings). A real shape conflict aborts with instructions.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed merge order: text first (matches the historical layout of the
# generated frontend types), health endpoints taken from the last entry.
SERVICES = ["text-svc", "account-svc", "payments-svc", "ai-svc"]

# Harmless placeholders so ``from main import app`` succeeds without a real
# environment; nothing is connected to during a schema dump.
DUMP_ENV = {
    "SECRET_KEY": "openapi-dump",
    "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
}

_DUMP_SNIPPET = "import json, sys; from main import app; sys.stdout.write(json.dumps(app.openapi()))"


def dump_service(name: str) -> dict:
    """Dump one service's OpenAPI spec in an isolated interpreter."""
    env = {**os.environ, **DUMP_ENV, "PYTHONPATH": str(REPO_ROOT / "services" / name)}
    result = subprocess.run(
        [sys.executable, "-c", _DUMP_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        sys.stderr.write(f"error: dumping {name} failed:\n{result.stderr}\n")
        sys.exit(1)
    return json.loads(result.stdout)


def _structurally_equal(a: dict, b: dict) -> bool:
    """Compare schemas ignoring prose-only keys (description, examples)."""

    def strip(node):
        if isinstance(node, dict):
            return {
                k: strip(v) for k, v in node.items() if k not in ("description", "examples")
            }
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(a) == strip(b)


def merge(specs: dict[str, dict]) -> dict:
    first = specs[SERVICES[0]]
    merged: dict = {
        "openapi": first["openapi"],
        "info": first["info"],
        "paths": {},
        "components": {},
    }
    health: dict = {}

    for name in SERVICES:
        spec = specs[name]
        for path, item in spec.get("paths", {}).items():
            if path.startswith("/health"):
                health[path] = item  # last service wins, appended after API paths
                continue
            if path in merged["paths"] and merged["paths"][path] != item:
                sys.stderr.write(
                    f"error: path {path} defined differently by {name} and an "
                    "earlier service - routes must be unique across services.\n"
                )
                sys.exit(1)
            merged["paths"].setdefault(path, item)
        for section, defs in spec.get("components", {}).items():
            bucket = merged["components"].setdefault(section, {})
            for schema_name, schema in defs.items():
                if schema_name in bucket and not _structurally_equal(bucket[schema_name], schema):
                    sys.stderr.write(
                        f"error: components.{section}.{schema_name} from {name} conflicts "
                        "with an earlier service's definition. Rename one of them "
                        "(unique schema class names across services) and re-run.\n"
                    )
                    sys.exit(1)
                bucket.setdefault(schema_name, schema)
        for key, value in spec.items():
            if key not in ("openapi", "info", "paths", "components"):
                merged.setdefault(key, value)

    merged["paths"].update(health)
    return merged


def main() -> None:
    specs = {name: dump_service(name) for name in SERVICES}
    merged = merge(specs)
    text = json.dumps(merged, indent=2) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text)
        sys.stderr.write(
            f"wrote {sys.argv[1]}: {len(merged['paths'])} paths, "
            f"{len(merged['components'].get('schemas', {}))} schemas\n"
        )
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
