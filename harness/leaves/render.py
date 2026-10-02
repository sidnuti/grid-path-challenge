"""Loads a versioned prompt file (`prompts/<name>.v<version>.md`, split on an `<!-- system -->` /
`<!-- user -->` marker pair) and renders its user half with `str.format(**ctx)`. Kept separate
from `run.py` so a prompt version bump is a new file, not a code change — `leaf()` callers pass
`prompt_ver` through to the replay cache key specifically so a prompt edit invalidates the cache
for anything that used the old wording.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=None)
def _load(name: str, version: str) -> tuple[str, str]:
    path = PROMPTS_DIR / f"{name}.v{version}.md"
    text = path.read_text()
    _, _, rest = text.partition("<!-- system -->")
    system, _, user = rest.partition("<!-- user -->")
    return system.strip(), user.strip()


def render(name: str, version: str, ctx: dict) -> tuple[str, str]:
    system, user_template = _load(name, version)
    return system, user_template.format(**ctx)
