# Can I Use This?

A rights-determination agent. Paste a song or a book, say what you want to do with it, get a cited verdict: can you use it, who owns it, roughly what it costs, what to use instead, and what couldn't be determined.

Built for the Agentic Cinema hackathon (Parallel track). **Deadline: Sep 9, 2026.** Solo developer. Schedule has no slack — see `docs/PROJECT.md` §2 for the cut ladder.

---

## The one thing to get right

**One query maps to several separately-owned works with different answers.**

```
"West End Blues"
  ├── composition      (writers/publishers; ISWC; MLC)      → public domain
  └── sound recording  (label; ISRC; MusicBrainz)           → protected until 2029
                                                    roll-up → LICENSE REQUIRED
```

A composition can be public domain while every recording of it is protected. A book's original can be public domain while a translation isn't. This is the most common source of wrong answers in this domain, and handling it correctly is the entire product.

**Verdict is three-dimensional:** `verdict = f(layer, jurisdiction, intent)`.

---

## Hard rules — violating any of these breaks the project's central claim

1. **The rules engine is hand-written Python, never LLM-generated at runtime.** `rules/` is deterministic, unit-tested, auditable. Every `Determination` records which `rule_id` fired and why. If a model computes a copyright term, that's a bug.

2. **Three research tiers, always prefer the cheapest that can answer:**
   - Tier 1 — static table parsing RightsStatements.org / Creative Commons URIs. No call, no model.
   - Tier 2 — direct APIs: MusicBrainz, MLC, Wikidata, Open Library, HathiTrust, Spotify.
   - Tier 3 — Parallel (Task / Search / Extract) for everything else.
   Record the tier in `Source.method`.

3. **Decompose into layers BEFORE researching.** Research fans out per layer, concurrently.

4. **No unsourced facts.** Every value is a `ResearchedFact` with sources and confidence, or it becomes an `UnresolvedQuestion`. No third option. If the model wants to assert something it can't cite, that's a bug.

5. **Conservative roll-up.** Use `REQUIRED_LAYERS` and `VERDICT_ORDER` from `schemas.py` — not inference. `UNDETERMINED` is the *most* restrictive value. If we don't know, we don't say clear.

6. **Stop on ambiguous resolution.** If `resolution_confidence` is LOW with multiple candidates, set `stop_for_disambiguation`, return candidates, do not research. Researching an ambiguous entity produces confidently wrong output — the worst failure mode this product has.

7. **Tier 2 failures degrade, never fail.** 5-second timeout, fall through to Tier 3.

---

## Scope — exactly two asset types

**In:** music (composition + sound recording), text/film (work + edition + translation).

**Recognized but NOT researched:** images, fonts, characters, footage, trademarks. These return a `boundary_note` explaining honestly what we can't do yet. Do not implement them. Do not suggest implementing them.

**Not in scope at all:** audio fingerprinting, image matching, licensing marketplace, accounts/auth, saved history, researched alternatives (curated static lists only), Parallel Monitor, batch/CSV mode.

If you think of a feature that would improve this, write it down and don't build it. Anything added requires something cut.

---

## Known-hard problem

US works published 1931–1963 required renewal in year 28. Those records are partly scanned card images with no machine access. **If renewal can't be determined, do not guess** — emit an `UnresolvedQuestion` with exact search terms and the right catalog range. That's designed behavior and a demo asset, not a gap.

(The renewal window rolls forward every 1 January as the 95-year cliff advances.)

---

## Latency

Cold query target: **under 90 seconds.** Use Parallel `base-fast` or `core-fast`. **Never `pro` or `ultra` in the request path** — they run minutes to hours.

Render progressively: layers resolved from Tier 2 appear while Tier 3 is still running. The staged progress UI is not decoration — it's what makes 60 seconds tolerable, and it's a major part of the demo video.

MusicBrainz: ~1 req/sec, requires a descriptive User-Agent, cache everything.

---

## Stack

Google ADK / Agent Builder · Gemini via Vertex AI · Parallel SDK (`parallel-web`) · FastAPI on Cloud Run with SSE · Firestore cache · React + Tailwind · no auth.

Build the pipeline as plain Python that ADK wraps, so provisioning delays never block work.

---

## Design

Full tokens in `docs/design-system.md`. The essentials:

- **Six font sizes only:** 12 / 16 / 21 / 28 / 38 / 64. No decimals, no intermediates.
- **Six colors:** `#FAFAF4` PAPER · `#16233A` INK · `#2244AA` LEDGER_BLUE · `#1E6B47` STAMP_GREEN · `#6D28D9` STAMP_VIOLET · `#B3261E` STAMP_RED. Plus `#8FACF2` for controls on the INK band, and INK at 0.7 / 0.2 opacity. Nothing else.
- **STAMP_RED is rights semantics only** — RESTRICTED and the blocking rule. Never error, never hover.
- **Mono (IBM Plex Mono) is for evidence values only** — dates, percentages, identifiers, citations, search strings. Everything else is Archivo. Target ~30/70.
- **No cards.** One continuous ruled document. Radius 6px where used.

Visual reference: `docs/design/*.dc.html`. These are Design Composer format (`<x-dc>`, `{{ }}` bindings) — **read as reference only, they are not React.** The inline styles are real CSS and translate directly.

---

## Repo map

```
rules/          deterministic terms. mma.py, terms.py, rollup.py + tests
sources/        Tier 2 API clients
research/       Tier 3 Parallel client
registry/       sources.yaml — handoff link templates
agent/          ADK orchestration — build LAST
api/            FastAPI + SSE
web/            React frontend
spike/          throwaway verification, kept for reference
docs/           PROJECT.md, design-system.md, design-reference.md
schemas.py      CANONICAL. Read its docstring. Do not redesign.
```

---

## Commands

```bash
python -m pytest rules/            # rules engine tests
python -m uvicorn api.main:app --reload
```

---

## Build order

Do not scaffold everything and fill it in.

1. One music query, command line, correct two-layer cited verdict. Nothing else until this works.
2. Text/film path, same skeleton.
3. ADK orchestration wrapping the working pipeline.
4. Frontend with staged progress.
5. Deploy to Cloud Run.

---

## Status

- `rules/` — MMA/CLASSICS schedule, US standard terms, life+70, roll-up. **Written and passing 33 boundary tests.** Do not modify without re-running them.
- `spike/` — verifies MusicBrainz work↔recording linkage and Wikidata death years.
- Design — Entry, Progress, Result complete. Disambiguation and error/boundary states not yet designed; specify from `docs/design-reference.md`.
- MLC API access pending. Composition layer degrades to Tier 3 if it doesn't arrive.
