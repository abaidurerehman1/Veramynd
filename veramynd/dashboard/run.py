#!/usr/bin/env python3
"""Run the Veramynd enterprise alignment dashboard."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERAMYND = ROOT.parent
if str(VERAMYND) not in sys.path:
    sys.path.insert(0, str(VERAMYND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    os.chdir(ROOT)
    import uvicorn

    print(f"Veramynd dashboard -> http://{args.host}:{args.port}")
    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
