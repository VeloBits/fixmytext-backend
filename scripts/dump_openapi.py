"""Dump the FastAPI OpenAPI schema to stdout (or a file).

Usage:
    python scripts/dump_openapi.py            # → stdout
    python scripts/dump_openapi.py openapi.json
"""

import json
import sys
from pathlib import Path

# Ensure repo root is importable when invoked as `python scripts/dump_openapi.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402


def main() -> None:
    spec = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(spec)
    else:
        sys.stdout.write(spec)


if __name__ == "__main__":
    main()
