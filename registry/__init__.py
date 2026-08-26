"""
Source registry — handoff link templates (registry/sources.yaml).

    from registry import handoff_links
    links = handoff_links(identifiers, asset_type, extra={"title": ..., "artist": ...})

Each entry substitutes {value} from an already-resolved identifier of
`requires_scheme`, or a named extra ("title", "artist", "year") for
pre-filled searches and guided-manual instructions. Nothing here is
researched — it is template substitution over facts we already have.
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import quote_plus

import yaml

from schemas import AssetType, HandoffLink, Identifier, LinkTier, SourceRegistryEntry

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.yaml")
_entries: Optional[list[SourceRegistryEntry]] = None


def entries() -> list[SourceRegistryEntry]:
    global _entries
    if _entries is None:
        with open(_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        _entries = [SourceRegistryEntry(**e) for e in raw]
    return _entries


def handoff_links(identifiers: list[Identifier], asset_type: AssetType,
                  extra: Optional[dict] = None) -> list[HandoffLink]:
    extra = extra or {}
    out: list[HandoffLink] = []
    seen: set[str] = set()
    for e in entries():
        if asset_type not in e.applicable_types:
            continue
        values: list[str] = []
        if e.requires_scheme in extra:
            if extra[e.requires_scheme]:
                values = [str(extra[e.requires_scheme])]
        else:
            values = [i.value for i in identifiers
                      if i.scheme == e.requires_scheme and (i.is_primary or True)]
        for v in values[:1]:
            url = e.url_template.format(value=quote_plus(v) if e.tier != LinkTier.DEEP_LINK else v)
            if url in seen:
                continue
            seen.add(url)
            out.append(HandoffLink(
                source_name=e.name, url=url, tier=e.tier, purpose=e.purpose,
                description=e.description.format(value=v),
                paste_string=v if e.tier == LinkTier.GUIDED_MANUAL else None,
                navigation_hint=(e.navigation_hint or "").format(**{**extra, "value": v}) or None,
            ))
    return out
