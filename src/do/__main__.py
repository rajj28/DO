"""Entry point: `python -m do <command>`, with src/ put on the path so the seed runs
from a clone with no install step."""
import sys
from pathlib import Path

# Model output is arbitrary Unicode. On a Windows console (cp1252) a character like
# U+202F NARROW NO-BREAK SPACE - which gpt-oss emits around numbers - raises
# UnicodeEncodeError and kills the run mid-experiment. Reconfigure the console only:
# artifacts are written with encoding="utf-8" and stay byte-exact, so the recorded
# utterance is never altered. Only what the terminal can display degrades.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from do.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
