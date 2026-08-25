"""
Roll-up across layers. Most restrictive REQUIRED layer wins; undetermined is
the most restrictive value of all.

Function bodies unchanged from the original rules.py.
"""

from typing import Optional

from .terms import Status

VERDICT_ORDER = {
    "clear": 0,
    "clear_with_conditions": 1,
    "license_required": 2,
    "restricted": 3,
    "undetermined": 4,
}


def status_to_verdict(status: Status, has_unclaimed_shares: bool = False) -> str:
    if status == "undetermined":
        return "undetermined"
    if status == "public_domain":
        return "clear"
    if has_unclaimed_shares:
        return "restricted"
    return "license_required"


def roll_up(layer_verdicts: list[tuple[str, str, bool]]) -> tuple[str, Optional[str]]:
    """
    layer_verdicts: (layer_id, verdict, is_required)

    Returns the most restrictive verdict across REQUIRED layers, plus the
    layer_id that set it. Undetermined is most restrictive: if we don't know,
    we don't say clear.
    """
    required = [(lid, v) for lid, v, req in layer_verdicts if req]
    if not required:
        return "undetermined", None
    blocking_id, worst = max(required, key=lambda x: VERDICT_ORDER[x[1]])
    return worst, blocking_id
