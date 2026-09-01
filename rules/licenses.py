"""
Tier 1: the static license table.

A license relation on the MusicBrainz record (recording or work) is matched
against this table — no call, no model — and a recognized license settles the
layer outright: research for that layer stops, and the determination carries
the license's terms. Attribution and share-alike requirements surface as
CLEAR_WITH_CONDITIONS rather than CLEAR, because the user has to do
something. NC licenses do not cover commercial use, so the covering question
is intent-dependent and answered at assemble time (the determination itself
stays intent-independent, like every other determination).

Deterministic and unit-tested, like the rest of rules/: if a model parsed a
license URI, that would be a bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class License:
    code: str            # "cc_by_sa"
    label: str           # "CC BY-SA 4.0" (version filled from the URI)
    public_domain: bool  # CC0 / PD mark: no rights reserved at all
    attribution: bool
    sharealike: bool
    noncommercial: bool
    noderivatives: bool


_CC_CODES = {
    "by": ("cc_by", "CC BY", False, True, False, False, False),
    "by-sa": ("cc_by_sa", "CC BY-SA", False, True, True, False, False),
    "by-nd": ("cc_by_nd", "CC BY-ND", False, True, False, False, True),
    "by-nc": ("cc_by_nc", "CC BY-NC", False, True, False, True, False),
    "by-nc-sa": ("cc_by_nc_sa", "CC BY-NC-SA", False, True, True, True, False),
    "by-nc-nd": ("cc_by_nc_nd", "CC BY-NC-ND", False, True, False, True, True),
}

_LICENSE_RE = re.compile(
    r"creativecommons\.org/(?:licenses/(?P<code>[a-z-]+)/(?P<ver>[\d.]+)"
    r"|publicdomain/(?P<pd>zero|mark)/[\d.]+)")


def parse_license(uri: str) -> Optional[License]:
    """A recognized license from a URI, or None. Version-agnostic on code."""
    m = _LICENSE_RE.search(uri.lower())
    if not m:
        return None
    if m.group("pd"):
        return License("cc0" if m.group("pd") == "zero" else "cc_pd_mark",
                       "CC0 1.0" if m.group("pd") == "zero" else "CC Public Domain Mark",
                       True, False, False, False, False)
    row = _CC_CODES.get(m.group("code"))
    if row is None:
        return None
    code, label, pd, by, sa, nc, nd = row
    return License(code, f"{label} {m.group('ver')}", pd, by, sa, nc, nd)


# Intents whose use is non-commercial for NC purposes. Everything else is
# treated as commercial — the conservative reading.
NONCOMMERCIAL_INTENTS = {"personal", "education"}


def covers_intent(lic: License, intent_value: str) -> bool:
    """Does this license grant the use, before conditions?"""
    if lic.public_domain:
        return True
    if lic.noncommercial and intent_value not in NONCOMMERCIAL_INTENTS:
        return False
    return True


def conditions(lic: License) -> str:
    """The conditions sentence shown with a covered use."""
    parts = []
    if lic.attribution:
        parts.append("credit the creator as the license specifies")
    if lic.noderivatives:
        parts.append("use the track unmodified")
    if lic.sharealike:
        parts.append("share any adaptation under the same license")
    if lic.noncommercial:
        parts.append("non-commercial use only")
    return "; ".join(parts) if parts else "no conditions"


def license_explanation(lic: License, intent_value: str) -> str:
    if lic.public_domain:
        return (f"Dedicated to the public domain ({lic.label}) by its rights holder, "
                f"per the license relation on the MusicBrainz record.")
    if not covers_intent(lic, intent_value):
        return (f"Released under {lic.label}, which does not cover commercial use. "
                f"This use needs a license from the rights holder directly.")
    return f"Released under {lic.label}. Conditions: {conditions(lic)}."
