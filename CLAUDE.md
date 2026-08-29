# Can I Use This?

A rights-determination agent for documentary and independent film production. Paste a music cue, say what you want to do with it, get a cited verdict: can you use it, who owns it, roughly what it costs, what to use instead, and what couldn't be determined.

Built for the Agentic Cinema hackathon (Parallel track). The project plan and scope decisions live in `docs/PROJECT.md`; the current schedule, cuts and gates in `docs/ENDGAME.md`; the competition's technical constraints in `docs/COMPLIANCE.md`.

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

## Architectural rules — each exists because breaking it produces confidently wrong answers

1. **The rules engine is hand-written Python, never LLM-generated at runtime.** `rules/` is deterministic, unit-tested, auditable. Every `Determination` records which `rule_id` fired and why. If a model computes a copyright term, that's a bug.

2. **Three research tiers, always prefer the cheapest that can answer:**
   - Tier 1 — static table parsing RightsStatements.org / Creative Commons URIs. No call, no model.
   - Tier 2 — direct APIs: MusicBrainz, MLC, Wikidata, Open Library, HathiTrust, Spotify.
   - Tier 3 — Parallel (Search / Task / Extract) for everything else.
   Every `Source` records the tier in `Source.method`.

3. **Decompose into layers BEFORE researching.** Research fans out per layer, concurrently.

4. **Parallel Search runs on the primary request path.** Search handles renewal research and first-publication-date research; Task handles structured multi-field layer research. Both are used; Search is the one the track mandates — see `docs/COMPLIANCE.md` §1.

5. **No unsourced facts.** Every value is a `ResearchedFact` with sources and confidence, or it becomes an `UnresolvedQuestion`. No third option. If the model wants to assert something it can't cite, that's a bug.

6. **Conservative roll-up.** Use `REQUIRED_LAYERS` and `VERDICT_ORDER` from `schemas.py` — not inference. `UNDETERMINED` is the *most* restrictive value. If we don't know, we don't say clear.

7. **Stop on ambiguous resolution.** If `resolution_confidence` is LOW with multiple candidates, set `stop_for_disambiguation`, return candidates, do not research. Researching an ambiguous entity produces confidently wrong output — the worst failure mode this product has.

8. **Tier 2 failures degrade, never fail.** 5-second timeout, fall through to Tier 3.

9. **A recording's date must be trustworthy before a term is computed from it.** MusicBrainz `first-release-date` is the earliest release on file and is frequently a reissue; only a dated performance relation, label matrix data, or researched evidence (`RecordingDateBasis`, `TRUSTWORTHY_DATE_BASES` in `schemas.py`) may drive a confident sound-recording determination. Anything else yields an `UnresolvedQuestion`.

10. **Writer lists are cross-checked against Wikidata.** Life+70 runs from the death of the *last surviving* author, so an incomplete writer list can only ever shorten a UK/EU term. An uncorroborated list therefore **blocks** that determination — it becomes an `UnresolvedQuestion` carrying the alternative outcomes — rather than merely lowering its confidence. Same failure class as rule 9.

---

## Scope — one asset type

**In:** music (composition + sound recording). Text/film (work + edition + translation) shares the skeleton and was **cut on Aug 29** for the submission — see `docs/ENDGAME.md`.

**Recognized but not researched:** images, fonts, characters, footage, trademarks. These return a `boundary_note` explaining honestly what the tool can't do yet.

**Out of scope:** audio fingerprinting, image matching, licensing marketplace, accounts/auth, saved history, researched alternatives (curated static lists only), Parallel Monitor, batch/CSV mode, chat interface, skills registry. The reasoning behind each cut is in `docs/PROJECT.md` §2 and `docs/ENDGAME.md`.

---

## Known-hard problem

US works published 1931–1963 required renewal in year 28. Renewals filed before 1978 are partly scanned card images with no machine access; renewals filed from 1978 on (works published 1951–1963) are in the Copyright Office online catalog, which search excerpts cannot reach (`research.music.renewal_record_system`). **If renewal can't be determined, do not guess** — Parallel Search gathers candidate records, the reader reads them only if a passage states the renewal, and otherwise the result is an `UnresolvedQuestion` with exact search terms pointing at the record system that holds the answer. That is designed behavior, not a gap. On the first live run one of four windows resolved; that is the honest number.

The reader's confidence is capped by the class of source it cites — primary record → high, rightsholder/publisher notice → medium, anything else → low — in a validator, not the prompt. A "not renewed" finding needs a primary record.

(The renewal window rolls forward every 1 January as the 95-year cliff advances.)

---

## Latency

Cold query target: **under 90 seconds.** Use Parallel `base-fast` or `core-fast`. **Never `pro` or `ultra` in the request path** — they run minutes to hours.

Render progressively: layers resolved from Tier 2 appear while Tier 3 is still running. The staged progress UI is what makes a 60-second query tolerable.

MusicBrainz: ~1 req/sec, requires a descriptive User-Agent, and returns 503s on a sizeable share of first attempts. Every response is cached persistently; recording selection uses one work search rather than a per-recording sweep.

---

## Stack

`google-adk` · Gemini via Vertex AI · `parallel-web` · FastAPI on Cloud Run with SSE · Firestore cache · React + Tailwind · no auth.

The pipeline is plain Python that ADK wraps, so it runs and is testable without an agent runtime.

**Runtime AI is limited to Google Cloud AI services and Parallel.** No other model provider appears in `requirements.txt` or the runtime; non-AI third-party services are unrestricted. See `docs/COMPLIANCE.md` §3.

---

## Design

Full tokens in `docs/design-system.md`. The essentials:

- **Six font sizes only:** 12 / 16 / 21 / 28 / 38 / 64. No decimals, no intermediates.
- **Six colors:** `#FAFAF4` PAPER · `#16233A` INK · `#2244AA` LEDGER_BLUE · `#1E6B47` STAMP_GREEN · `#6D28D9` STAMP_VIOLET · `#B3261E` STAMP_RED. Plus `#8FACF2` for controls on the INK band, and INK at 0.7 / 0.2 opacity. Nothing else.
- **STAMP_RED is rights semantics only** — RESTRICTED and the blocking rule. Never error, never hover.
- **Mono (IBM Plex Mono) is for evidence values only** — dates, percentages, identifiers, citations, search strings. Everything else is Archivo. Target ~30/70.
- **No cards.** One continuous ruled document. Radius 6px where used.

Visual reference: `docs/design/*.dc.html`. These are Design Composer format (`<x-dc>`, `{{ }}` bindings) — **reference only, not React.** The inline styles are real CSS and translate directly.

---

## Repo map

```
rules/          deterministic terms: mma.py, terms.py, rollup.py + tests
sources/        Tier 2 API clients, persistent cache, fail-soft HTTP
research/       Tier 3 — Parallel Search and Task
registry/       sources.yaml — handoff link templates
pipeline/       the plain-Python pipeline (music.py, determine.py, assemble.py) and CLI
agent/          ADK orchestration wrapping the pipeline
api/            FastAPI + SSE
web/            React frontend
spike/          the verification spike, kept for reference
docs/           PROJECT.md, COMPLIANCE.md, design-system.md, design-reference.md
schemas.py      canonical data model — read its docstring before changing anything
```

---

## Commands

```bash
python -m pytest                                   # rules, sources, research, registry, pipeline, agent
python -m pipeline "West End Blues" "Louis Armstrong"
python -m pipeline "Take Five" --json              # no artist → stops with candidates
python -m pipeline "Blue Moon" "Ella Fitzgerald" --read     # with the Gemini reader (GCP + ADC)
python -m pipeline "West End Blues" "Louis Armstrong" --graph   # through the ADK graph
python -m agent.live_cases                         # reader over live Parallel Search; --case, --all-raw
python -m agent.freeze_fixtures                    # re-freeze acceptance fixtures — deliberately, never to pass a test
python -m sources.warm "Blue Moon" "The Marcels"   # pre-warm the cache, print timings
python -m uvicorn api.main:app --reload            # once api/ exists
```

---

## Build order

1. One music query, command line, correct two-layer cited verdict.
2. Text/film path, same skeleton.
3. ADK orchestration wrapping the working pipeline.
4. Frontend with staged progress.
5. Deploy to Cloud Run.

---

## Status

- `rules/` — MMA/CLASSICS schedule, US standard terms, EU/UK recording term, life+70, roll-up. 43 boundary cases in `rules/test_rules.py`.
- `sources/` — Tier 2 cache layer: SQLite/Firestore cache, throttled + retried HTTP that fails soft, MusicBrainz and Wikidata clients.
- `research/` — Parallel Search and Task wrappers, cached, degrading cleanly when no key is present.
- `registry/` — handoff link templates.
- `pipeline/` — music path end to end, as stage functions over a `MusicRun` (`STAGES` in `pipeline/music.py`). Both demo queries produce the expected cited two-layer verdict from the CLI: West End Blues / Louis Armstrong in 7.5 s cold, Rhapsody in Blue / Paul Whiteman in 19.1 s cold, under a second warm.
- `agent/` — the reading step (`gemini_reader.py`, gemini-2.5-flash on Vertex; `gemini-flash-latest` is AI Studio only and 404s on Vertex), its schema (`reader_schema.py`), the ADK graph (`workflow.py`) and the frozen acceptance fixtures it reproduces. The `anthropic` package must not be installed: ADK's model registry imports it, 0.40.0 crashes past ADK's guard, and it violates COMPLIANCE §3.
- `spike/` — verified MusicBrainz work↔recording linkage and Wikidata death years; its findings became rules 9 and 10 above.
- Design — Entry, Progress, Result complete. Disambiguation and error/boundary states not yet designed; specify from `docs/design-reference.md`.
- Not yet built: `api/`, `web/`, the Cloud Run deployment, MLC integration. Schedule and gates: `docs/ENDGAME.md`.
