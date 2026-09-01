"""
Rights-holder research through Parallel TASK: structured multi-field output
with per-field citations (output.basis). Fills the ClearanceProfile that MLC
access would fill authoritatively — publisher, administrator, shares,
territory, one-stop — as a research substitute until that access arrives.

THE CONSTRAINTS (they matter more than the wiring):

1. Task output is RESEARCH, not registry data. Confidence is capped at
   MEDIUM (TASK_CONFIDENCE_CEILING), every Source is method=parallel_task
   with authoritative=False, and MLC_NOTE goes on the record verbatim. When
   MLC access arrives, MLC supersedes all of this.

2. Unclaimed shares are never inferred. If found shares don't sum to 100%,
   that is absence of evidence — the same trap as "renewal not filed". We
   report what was found and say completeness can't be verified without the
   MLC. unclaimed_share_percent stays None, always, from this module.

3. This never runs on the verdict path. The caller (pipeline/clearance.py
   via GET /api/clearance) runs it only for layers already determined
   protected or license-required, after the verdict has been returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from schemas import (
    ClearanceProfile, Confidence, ResearchMethod, ResearchedFact, RightsHolder, Source,
)

from .parallel_client import TaskOutcome, run_task

# Constraint 1, enforced here and not in a prompt.
TASK_CONFIDENCE_CEILING = Confidence.MEDIUM

MLC_NOTE = ("The MLC is the authoritative source for composition ownership. This is web "
            "research standing in until API access arrives; the MLC record supersedes it.")

HOLDERS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "parties": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string",
                             "enum": ["publisher", "administrator", "label", "estate", "unknown"]},
                    "is_administrator": {"type": "boolean"},
                    "share_percent": {"type": ["number", "null"],
                                      "description": "Only if a source states the share. Never estimate."},
                    "territory": {"type": ["string", "null"]},
                    "founded_year": {"type": ["integer", "null"],
                                     "description": "The company's founding year, only if a source states it."},
                    "evidence": {"type": "string",
                                 "description": "Short quote or statement from a source supporting this party."},
                },
                "required": ["name", "role", "is_administrator", "share_percent",
                             "territory", "founded_year", "evidence"],
            },
        },
        "one_stop": {"type": ["boolean", "null"],
                     "description": "True only if a source states one entity controls both the "
                                    "publishing and the master. Null when not established."},
        "notes": {"type": "string"},
    },
    "required": ["parties", "one_stop", "notes"],
}


@dataclass
class HoldersFinding:
    """Validated rights-holder research for one layer."""
    holders: list[RightsHolder] = field(default_factory=list)
    clearance: Optional[ClearanceProfile] = None
    found_share_total: Optional[float] = None
    completeness_note: str = ""
    mlc_note: str = MLC_NOTE
    ledger: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _task_input(layer_id: str, title: str, names: list[str], year: Optional[int]) -> str:
    who = ", ".join(names) if names else "unknown"
    if layer_id == "composition":
        return (f'Identify the current music publishers and administrators of the musical composition '
                f'"{title}" (written by {who}{f", published {year}" if year else ""}). For each party: '
                f'name, whether it is the administrator (who actually licenses), its ownership share '
                f'percentage if a source states one, and the territory it controls. State whether one '
                f'entity controls both the publishing and the original master recording. Only report '
                f'what sources actually state; never estimate shares.')
    return (f'Identify who currently owns the master rights to the sound recording of "{title}" by '
            f'{who}{f" ({year})" if year else ""}: the original label and the current rights holder '
            f'after any catalog sales. State whether one entity controls both this master and the '
            f'underlying composition. Only report what sources actually state.')


def _basis_sources(outcome: TaskOutcome, party_name: str) -> list[Source]:
    """Sources for one party from output.basis. A field's citations become
    Sources; parties nothing in the basis mentions get none (and land at LOW)."""
    out: list[Source] = []
    for fb in outcome.basis or []:
        text = str(fb)
        if party_name.lower() not in text.lower():
            continue
        for c in fb.get("citations", []) if isinstance(fb, dict) else []:
            url = c.get("url")
            excerpt = ((c.get("excerpts") or [None])[0] or c.get("title") or "")[:200] or None
            out.append(Source(
                name=(c.get("title") or (url.split("/")[2] if url and "//" in url else "web source")),
                url=url if url and url.startswith(("http://", "https://")) else None,
                method=ResearchMethod.PARALLEL_TASK,
                retrieved_at=outcome.retrieved_at,
                excerpt=excerpt,
                authoritative=False,   # constraint 1: research, not registry data
            ))
    return out[:3]


def holders_from_task(outcome: TaskOutcome, layer_id: str) -> HoldersFinding:
    """TaskOutcome -> validated HoldersFinding. All three constraints live here."""
    if not outcome.ok:
        return HoldersFinding(error=outcome.error)
    content = outcome.content or {}
    parties = content.get("parties") or []
    holders: list[RightsHolder] = []
    share_total = 0.0
    any_share = False
    for p in parties:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        sources = _basis_sources(outcome, name)
        conf = TASK_CONFIDENCE_CEILING if sources else Confidence.LOW
        share = p.get("share_percent")
        if isinstance(share, (int, float)) and 0 <= share <= 100:
            share_total += float(share)
            any_share = True
        else:
            share = None
        holders.append(RightsHolder(
            name=ResearchedFact(value=name, confidence=conf, sources=sources,
                                reasoning=(p.get("evidence") or "").strip()[:300] or None),
            role=p.get("role") or "unknown",
            is_administrator=bool(p.get("is_administrator")),
            share_percent=share,
            territory=p.get("territory"),
        ))

    # Constraint 2: found shares are reported; a shortfall concludes NOTHING.
    found_total = round(share_total, 2) if any_share else None
    if found_total is not None and found_total < 100:
        completeness = (f"Shares found sum to {found_total:g}%. The remainder is not necessarily "
                        f"unclaimed; completeness cannot be verified without the MLC.")
    elif holders:
        completeness = "Completeness cannot be verified without the MLC."
    else:
        completeness = "No parties could be established from web research."

    one_stop = content.get("one_stop")
    one_stop_fact = None
    if isinstance(one_stop, bool):
        srcs = _basis_sources(outcome, "one")  # any basis entry for the one_stop field
        if srcs:
            one_stop_fact = ResearchedFact(value=one_stop, confidence=TASK_CONFIDENCE_CEILING,
                                           sources=srcs)
        # uncited one_stop is dropped: an unsourced fact is not a fact

    clearance = ClearanceProfile(
        party_count=len(holders) or None,     # parties FOUND; completeness_note qualifies it
        unclaimed_share_percent=None,         # constraint 2: never from a shortfall
        is_one_stop=one_stop_fact,
        difficulty_reasoning=completeness + " " + MLC_NOTE if holders else None,
    )
    cached = " (cached)" if outcome.from_cache else f" ({outcome.processor}, {outcome.elapsed_s:.1f}s)"
    ledger = [
        f"Parallel Task — rights holders ({'composition' if layer_id == 'composition' else 'sound recording'})",
        f"{len(holders)} part{'y' if len(holders) == 1 else 'ies'} found, "
        f"{len(outcome.basis or [])} cited field{'s' if len(outcome.basis or []) != 1 else ''}{cached}",
    ]
    return HoldersFinding(holders=holders, clearance=clearance, found_share_total=found_total,
                          completeness_note=completeness, ledger=ledger)


def research_holders(layer_id: str, title: str, names: list[str],
                     year: Optional[int]) -> HoldersFinding:
    """The Task call plus validation. Cached by the Task wrapper (7 days)."""
    outcome = run_task(_task_input(layer_id, title, names, year), HOLDERS_SCHEMA)
    return holders_from_task(outcome, layer_id)
