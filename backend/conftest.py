"""pytest config: hermetic test env + import path.

Forces API keys empty so a developer's real `.env` never triggers live API calls
(which would cost money / be flaky) or flip the `*_configured` assertions. The suite
deliberately exercises the free no-key paths. Also puts the backend dir on sys.path.
"""

import os
import sys
from pathlib import Path

# Override any real keys loaded from .env so tests stay offline + free.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["DEEPGRAM_API_KEY"] = ""
os.environ["EXA_API_KEY"] = ""  # never hit the paid Exa API in tests
os.environ["FAL_KEY"] = ""  # never hit the paid fal/Pika video API in tests

sys.path.insert(0, str(Path(__file__).resolve().parent))
