import os
import sys
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))                    # adapters
sys.path.insert(0, str(HERE / "upstream"))       # src, preprint
sys.path.insert(0, str(HERE.parent))             # common
os.environ.setdefault("SANDBOX_LLM_MODE", "replay")   # offline tests can never spend money
warnings.filterwarnings("ignore")
