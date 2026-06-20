"""pytest config: ensure the backend dir is on sys.path so `app`/`agents` import."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
