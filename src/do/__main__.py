"""Entry point: `python -m do <command>`, with src/ put on the path so the seed runs
from a clone with no install step."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from do.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
