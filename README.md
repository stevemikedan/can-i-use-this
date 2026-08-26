# Can I Use This?

A rights-determination agent for people about to publish something — a documentary editor with a music cue, a podcaster, a YouTuber, an archivist clearing a backlog. Paste a song (books and films are next), say what you want to do with it, and get a cited verdict: whether you can use it, who owns it, roughly what it would cost, and an honest account of what could not be determined.

Built for the Agentic Cinema hackathon, Parallel track.

> This is research, not legal advice. Verify before relying on it for anything consequential.

## The one idea

One thing you search for is usually several separately-owned works with different answers.

```
"West End Blues" — Louis Armstrong
  ├── composition      King Oliver · published 1928           → public domain since 2024
  └── sound recording  Hot Five session, 1928-06-28            → protected until 2029 (CLASSICS Act)
                                                    roll-up  → LICENSE REQUIRED
```

The song is free; the famous recording of it is not — so the answer for a film is *no, not without a master use license*. The reverse happens too: a 1924 recording can be public domain while the song it captures is still protected. Most tools flatten this into one answer and get it wrong. Handling it correctly is the entire product.

The verdict is also three-dimensional — `f(layer, jurisdiction, intent)`. The same song gets different answers in the US and the EU, and for a film versus a re-recording (where the original master stops mattering).

## Architecture

```
classify → identify → decompose → research → rules → compare → assemble
```

*Architecture diagram: to be added before submission.*

**Identify.** MusicBrainz recording search. A title with no artist and several artists in the results **stops for disambiguation** and returns candidates — researching an ambiguous entity produces confidently wrong output, the worst failure mode this product has.

**Select the recording.** One composition is often several MusicBrainz work entities (arrangements, "original 1924 version", translations). A single work search finds them all; every recording linked to each is enumerated and the artist's earliest **dated session** is chosen. MusicBrainz's `first-release-date` is the earliest release *on file* — frequently a CD reissue decades after the session — and is never allowed to drive a term.

**Research, cheapest tier first.**

| Tier | What | Sources |
|---|---|---|
| 1 | Static parsing, no call, no model | RightsStatements.org and Creative Commons URIs |
| 2 | Direct APIs, cached persistently, throttled, retried with backoff, every call fails soft | MusicBrainz (recordings, works, dated sessions, ISWCs, writer credits) · Wikidata (publication year, composer/lyricist cross-check, death years) · MLC (publishers, administrators, shares) · Open Library, HathiTrust (text) |
| 3 | Parallel | **Search** on the primary request path for US renewal records (works published 1931–1963) and for the original release of recordings that only have a reissue date · **Task** for structured, cited multi-field research |

**Rules.** A hand-written, unit-tested rules engine (`rules/`) computes every term: the MMA/CLASSICS schedule for US sound recordings, the 95-year US published-work term with its renewal window, life+70 for UK/EU compositions, and 70-years-from-publication for UK/EU recordings. Every determination records which rule fired and why. No model ever computes a copyright term.

**Assemble.** A verdict per layer per jurisdiction; a conservative roll-up over only the layers your intent actually requires, where *unknown* is more restrictive than *protected*; unresolved questions with exact search terms and links to the records that would settle them; and handoff links — deep links, pre-filled searches, or honest "search here, paste this" instructions — to verify, resolve, or license.

Every asserted value is a `ResearchedFact` carrying its sources and a confidence. Anything that cannot be sourced becomes an `UnresolvedQuestion` rather than a guess. The canonical data model is `schemas.py`.

## Setup and run

```bash
pip install -r requirements.txt

python -m pipeline "West End Blues" "Louis Armstrong"
python -m pipeline "Rhapsody in Blue" "Paul Whiteman" --jurisdiction UK --intent film_tv
python -m pipeline "Take Five" --json            # no artist → stops with candidates

python -m pytest                                # rules, sources, research, registry, pipeline
python -m sources.warm "Blue Moon" "The Marcels" # pre-warm the cache and print timings
```

| Environment variable | Purpose |
|---|---|
| `PARALLEL_API_KEY` | Tier 3 research through the `parallel-web` SDK. Without it Tier 3 degrades: questions are still emitted, just without search hits. |
| `CACHE_BACKEND` | `sqlite` (default, `.cache/tier2.sqlite`), `firestore`, or `memory` |
| `CACHE_PATH` / `CACHE_COLLECTION` | SQLite file / Firestore collection |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI (Gemini) and Firestore when deployed on Cloud Run |

Runtime AI is limited to Google Cloud AI services and Parallel; everything else is ordinary open infrastructure (httpx, Pydantic, SQLite, FastAPI).

## Repository

```
rules/       deterministic copyright terms + boundary tests
sources/     Tier 2 clients, persistent cache, fail-soft HTTP
research/    Tier 3 — Parallel Search and Task
registry/    handoff link templates (sources.yaml)
pipeline/    the plain-Python pipeline and CLI
agent/       google-adk orchestration wrapping the pipeline
api/         FastAPI + SSE for the staged progress UI
web/         React frontend
spike/       the verification spike, kept for reference
docs/        project definition, compliance notes, design system
schemas.py   canonical Pydantic models
```

## Status

- Music path runs end to end from the command line. Both reference queries produce the expected cited two-layer verdict — *West End Blues / Louis Armstrong* (composition public domain, recording protected, license required) in about 8 seconds cold and *Rhapsody in Blue / Paul Whiteman* (both layers public domain, clear) in about 19 seconds cold; under a second when cached.
- 94 tests across the rules engine, the cache layer, the Parallel wrappers, the link registry, and the pipeline (ambiguity stop, reissue-only path, renewal window, degraded Tier 3).
- Not yet built: the Gemini step that reads Tier 3 evidence into cited facts, MLC integration (publishers, shares, clearance difficulty), the text/film path, the ADK agent, the API, the frontend, and the Cloud Run deployment.

## Known limitations

- **The renewal window.** US works published 1931–1963 lost protection after 28 years unless renewed, and most of the 20th-century songbook falls in that window. The renewal records are scanned catalog pages with no machine-readable database. The tool searches for candidate entries and hands them over as an unresolved question with exact search terms; it does not guess. Expect many mid-century compositions to come back *undetermined* rather than *clear* or *protected*.
- **No database publishes sync licensing contacts or prices.** Sync is negotiated one-off. The tool identifies the parties, the administrator, and the shape of the negotiation, and gives cost bands as ranges — never a point estimate.
- **Determinations are US-centric.** The US rules are the most complete. UK and EU determinations cover the composition (life+70) and the recording (70 years from publication); other jurisdictions are not modelled.
- **Coverage follows the sources.** A recording MusicBrainz has not dated, or a work Wikidata has not described, ends in an unresolved question rather than an answer. Writer lists that cannot be corroborated cap the UK/EU confidence at LOW.
- **Music first.** Text and film (work, edition, translation) share the same skeleton but are not built yet. Images, fonts, characters, footage and trademarks are recognised and refused with an explanation, not researched.

## Why the provenance rules exist

Three times during the build a source returned a plausible fact that had never actually been established, and each would have become a confident wrong verdict with no visible tell:

- **A reissue date is not a publication date.** MusicBrainz's `first-release-date` for the 1928 Armstrong *West End Blues* was 1975 — a 42-year error on the one fact the recording term depends on.
- **An incomplete author list understates a life+70 term.** MusicBrainz credited King Oliver alone; co-writer Clarence Williams died in 1965, which moves the EU expiry from 2009 to 2036.
- **A name search can return the wrong person.** Searching Wikidata for "Clarence Williams" returned the actor (d. 2021), not the pianist (d. 1965).

Each became a rule: a recording's date must come from a trustworthy basis, a writer list must be corroborated before life+70 is applied, and people are resolved through identifier links between databases rather than by name. When a rule can't be met the layer is *undetermined* and the response names the fact that would settle it.

## What we learned from the data

- **MusicBrainz** returned a 1975 reissue date for a 1928 session — a 42-year error on the one fact the CLASSICS calculation depends on. Only the dated performance relation is trustworthy. Popular standards have 600–1,800 linked recording entities, and the service returns 503s on roughly a quarter of first attempts at one request per second; "Tier 2 degrades, never fails" turned out to be necessary rather than cautious.
- **Wikidata** was clean for every case tested and catches co-writers MusicBrainz omits — which matters because life+70 runs from the *last surviving* author.
- **Recording selection, not the work link, is the hard problem.** Replacing a ten-call per-recording sweep with a single work search cut cold latency from 71 s to 7.5 s on West End Blues and from 45 s to 19 s on Rhapsody in Blue.

## License

MIT — see `LICENSE`.
