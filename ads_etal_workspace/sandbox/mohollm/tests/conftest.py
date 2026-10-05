import os
import sys
import warnings
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
UP = HERE / "upstream"
sys.path.insert(0, str(UP))            # mohollm, main, benchmark_initialization
sys.path.insert(0, str(HERE))          # adapters
sys.path.insert(0, str(HERE.parent))   # common
os.environ.setdefault("SANDBOX_LLM_MODE", "replay")   # offline tests can never spend money
warnings.filterwarnings("ignore")


@pytest.fixture(autouse=True)
def _cwd_upstream(monkeypatch):
    """Upstream resolves prompt templates / configs relative to its own root ('./prompt_templates/...')."""
    monkeypatch.chdir(UP)
