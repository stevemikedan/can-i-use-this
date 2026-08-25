"""
Deterministic copyright term rules. No network, no model, no I/O.

Re-exports everything so `from rules import ...` works exactly as it did
when this was a single rules.py.
"""

from .terms import (  # noqa: F401
    CURRENT_YEAR,
    Determination,
    Status,
    life_plus_70,
    us_standard_term,
)
from .mma import us_sound_recording  # noqa: F401
from .rollup import VERDICT_ORDER, roll_up, status_to_verdict  # noqa: F401
