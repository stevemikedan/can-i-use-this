# Can I Use This? — Project Definition

**Status:** authoritative. Supersedes `agentic-cinema-project-plan.md` and `can-i-use-this-spec.md`, both of which contain stale recommendations and should be treated as archive only.

**Hackathon:** Agentic Cinema (Devpost) · Parallel track · Deadline **Sep 9, 2026, 2:00pm PDT** · Target submission **Sep 8**
**Today:** Aug 25, 2026 · **Build days available: 12** (Aug 26 – Sep 6, with Sep 7–8 reserved for video, writeup, and submission)
**Team:** solo

**Spike: PASSED (Aug 25).** Rules engine written, 35 tests green. Two-layer determination verified end-to-end against live MusicBrainz and Wikidata. Findings changed the music architecture materially — see §3 and §9.

---

## 1. What it is

Paste any music or written/film work. Say what you want to do with it. Get back a cited verdict: can you use it, who owns it, what it would cost, what to use instead if you can't — and an honest account of what couldn't be determined.

**The insight the product is built on:** one thing you searched for is usually several separately-owned works with different answers. A song is a composition *and* a recording. A book is a work *and* possibly a translation. Existing tools flatten this and give confidently wrong answers as a result.

**The verdict is three-dimensional:** `verdict = f(layer, jurisdiction, intent)`.

---

## 2. Scope — final, and deliberately smaller than the last draft

### In

| Feature | Why it stays |
|---|---|
| **Music** (composition + sound recording layers) | Primary. Best demo, most common real question in film |
| **Text / film** (work + edition + translation layers) | Secondary. Best free API coverage; carries the public-domain-checker concept |
| Rights-layer decomposition | The core abstraction; without it the product is just another lookup |
| Jurisdiction toggle (US / UK / EU) | Cheap, visually dramatic, technically real |
| Intent-aware verdicts | Highest differentiation per unit of effort |
| Archive-disagreement notes | Signature output; half a day |
| Confidence + unresolved questions | The rigor story; also how the renewal problem stops being a hole |
| Handoff / resources panel | Nearly free — identifiers are already resolved |
| Clearance difficulty assessment | Party count, unclaimed shares, one-stop detection. Small, high-value |

### Cut — and these are real cuts, not deferrals

| Cut | Days recovered | Rationale |
|---|---|---|
| **Images as an asset type** | ~2.0 | Weakest Tier 2 coverage, no authoritative rights source, and reverse-image handling is a subsystem of its own. The one to lose |
| **Researched alternatives engine** | ~0.7 | Replaced by a curated static list per asset type. A hand-picked public-domain substitute is as useful to the user and costs nothing at runtime |
| **Parallel Monitor integration** | ~0.5 | Nice always-on beat for the video, but not load-bearing. Re-add only if genuinely ahead on Sep 2 |
| **Batch / CSV mode** | ~0.5 | Describe it in the writeup as the institutional path. Don't build it |

**Revised core estimate: ~13 days against 13 available.** Slack is effectively zero after the expanded design pass (see §6). The cut list above is therefore also the *re-cut* list, in this order:

1. Jurisdiction toggle → US only (~0.5 days)
2. Disagreement notes → drop (~0.5 days)
3. Text/film asset type → drop, ship music only (~2 days)

Decide on Sep 1. If the pipeline isn't end-to-end by then, take cut 1 and 2 immediately rather than hoping.

### Explicitly not in scope
Audio fingerprinting, image matching, a licensing marketplace, accounts or auth, saved history, mobile-specific work, any fourth asset type.

---

## 3. Architecture

### Three research tiers, cheapest first

```
Tier 1  Rights URI parsing        static table, no call, no model
        RightsStatements.org (12 statements), Creative Commons

Tier 2  Direct APIs               structured, fast, free
        MusicBrainz · MLC · Wikidata · Open Library
        HathiTrust Bib · Spotify · Wikimedia Commons

Tier 3  Parallel                  everything else
        Task (deep, cited) · Search (grounding) · Extract (JS pages)
```

### Pipeline

```
classify → identify → decompose → research → rules → compare → assemble
```

`decompose` runs *before* `research`. Research fans out per layer, concurrently. Every stage emits a `PipelineEvent` for the live progress UI.

### Music path — revised after the spike

The original design assumed the risk was *does the work link exist*. It isn't — work relations are present often enough, and Wikidata was clean 6 for 6. **The real problems are recording selection and true first-publication date.**

```
RESOLVE  title + artist (artist REQUIRED — title-only stops for disambiguation)
   ↓
SELECT   work-rels sweep on top candidates → collect distinct work MBIDs
         → browse /recording?work=X → filter to artist → earliest DATED session
         (this step is most of the engineering; see latency note below)
   ↓
├── COMPOSITION
│     Wikidata P577 → composition year
│     MusicBrainz artist-rels → writers, CROSS-CHECKED against Wikidata
│     MLC API → publishers, administrator, shares            [Tier 2]
│     Renewal (1931-1963) → TIER 3 RESEARCH, not auto-undetermined
│     Rules → 95-year US term; life+70 for EU/UK
│
└── SOUND RECORDING
      Dated performance relation → year                      [trustworthy]
      first-release-date → LOW ONLY, may be a reissue        [never confident]
      Rules → MMA/CLASSICS schedule
```

**Three hard-won rules, each from a real failure:**

1. **`first-release-date` may never drive a confident determination.** It returned a 1975 reissue for a 1928 session — 42 years wrong on the one fact CLASSICS depends on. Only a dated performance relation, label matrix data, or Tier 3 research counts. See `RecordingDateBasis` in `schemas.py`.

2. **Writer lists must be corroborated against Wikidata.** MusicBrainz gave King Oliver without Clarence Williams for West End Blues. US terms are unaffected (95-year rule), but life+70 runs from the *last surviving* author, so an incomplete list silently produces wrong EU/UK answers.

3. **Renewal is a Tier 3 research task, not a dead end.** Four of six real cases landed in the 1931–1963 window. Automatic "undetermined" there makes the product useless for most of the 20th-century songbook.

### Text/film path

```
Open Library / LoC → identifiers, editions, publication facts
  ├── TEXT WORK        Wikidata author death year → rules
  ├── EDITION          HathiTrust Bib API → rights determination
  └── TRANSLATION      separate author, separate term
```

### Stack

Agent Builder / ADK · Gemini via Vertex AI · Parallel SDK (`parallel-web`) · FastAPI on Cloud Run with SSE · Firestore cache · React + Tailwind · no auth.

---

## 4. Resolved ambiguities

These were undefined and a coding agent would have guessed. They are now decided.

### 4.1 Determination status → Verdict mapping

| Determination status | Conditions | Verdict |
|---|---|---|
| `public_domain` | no other restrictions | `CLEAR` |
| `public_domain` | other known legal restrictions | `CLEAR_WITH_CONDITIONS` |
| `no_copyright_other_restrictions` | always | `CLEAR_WITH_CONDITIONS` |
| `protected` | permissive license covers this intent | `CLEAR_WITH_CONDITIONS` |
| `protected` | no license, licensing path exists | `LICENSE_REQUIRED` |
| `protected` | unclaimed shares, or holder refuses this use class | `RESTRICTED` |
| `undetermined` | always | `UNDETERMINED` |

### 4.2 Which layers are "required" for the roll-up

`overall_verdict` = most restrictive verdict across **required** layers only. Required is a function of asset type and intent:

| Asset type | Intent | Required layers |
|---|---|---|
| Music | any audiovisual or commercial use | composition **and** sound recording |
| Music | using a re-recording instead | composition only |
| Music | personal / non-distributed | composition and sound recording (still, but cost band shifts) |
| Text | quoting or adapting the original | text work |
| Text | using a specific translation | text work **and** translation |
| Text | using a specific annotated edition | text work **and** edition |

Non-required layers still appear in the response and still get determinations — they're just excluded from the roll-up.

### 4.3 Restriction ordering

`CLEAR` < `CLEAR_WITH_CONDITIONS` < `LICENSE_REQUIRED` < `RESTRICTED` < `UNDETERMINED`

`UNDETERMINED` is treated as **most** restrictive for roll-up purposes. If we don't know, we don't say clear.

### 4.4 Cache key

Canonical key is the sorted, colon-joined list of `is_primary` identifiers across all layers, prefixed by asset type. Never the raw query string — "bohemian rhapsody" and "Bohemian Rhapsody (Queen)" must hit the same cache entry. Jurisdiction and intent are **not** part of the key, because the full matrix is computed and cached together.

### 4.5 Disambiguation failure

If `resolution_confidence` is LOW and more than one candidate exists, return `alternate_candidates` and **stop** — do not research. Researching an ambiguous entity produces confidently wrong output, which is the worst failure mode this product has. The UI presents the candidates; the user picks; resubmission carries `disambiguation_choice`.

### 4.6 Latency budget — previously unaddressed

**Revised after the spike — this is now the top technical risk.**

Recording selection measured at **7–19 MusicBrainz calls** (work-rels sweep, then paginated browse-by-work; Summertime has 1,806 linked recordings). At the 1 req/sec rate limit that is 20–30 seconds inside Tier 2 alone, before any Parallel research starts. MusicBrainz also returned 503s and TCP resets at 1 req/sec during the spike.

| Call | Processor | Target |
|---|---|---|
| Classification, disambiguation | Gemini Flash | < 2s |
| **Recording selection (MusicBrainz)** | — | **20–30s cold, < 2s cached** |
| Other Tier 2 calls | — | < 3s, concurrent |
| Layer research | Parallel `base-fast` or `core-fast` | < 45s |
| Rules, compare, assemble | local | < 1s |

**Cold total is now 60–75 seconds against a 90-second budget, with no headroom for retries.** Required mitigations, not optional:

- **Persistent cache of work→recordings maps and all MB responses, keyed by MBID.** The single highest-leverage fix.
- **Cap browse-by-work pagination** — stop early once artist-matched dated candidates are found. Never page 1,806 recordings.
- **Minimize the work-rels sweep** to the fewest candidates that reliably find the original.
- Aggressive retry with backoff on 503s, degrading to Tier 3 rather than failing.

**Design consequences:**

- The staged progress UI is not decoration — it's what makes 60 seconds tolerable. Show each stage completing, with source counts.
- Render progressively. Layers that resolve from Tier 2 should appear while Tier 3 is still running.
- **Pre-warm the cache for demo assets before recording.** This is legitimate — the results are real. But show at least one genuinely cold run in the video so the pipeline is visibly doing work.
- Never use Parallel `pro` or `ultra` in the request path. They run for minutes to hours.

### 4.7 Rate limits and retries

MusicBrainz is ~1 req/sec and requires a descriptive User-Agent. Cache every MusicBrainz response indefinitely. Exponential backoff on 503. All Tier 2 calls get a 5-second timeout and fail soft — a missing Tier 2 result degrades to Tier 3, it does not fail the query.

---

## 5. Demo assets — pick these, now

Each exists to demonstrate one specific behavior. Verify each by hand before building around it.

| # | Asset | Demonstrates |
|---|---|---|
| 1 | A pre-1926 recording of a composition still under copyright | **The core reveal.** Recording is public domain, composition isn't, verdict is no. Teaches the layer model in five seconds |
| 2 | A pre-1926 recording of a pre-1900 composition | Both layers clear. The happy path |
| 3 | A contemporary recording of a public-domain classical work | Inverse of #1 — composition clear, master protected |
| 4 | A work with split publisher shares across several parties | Clearance difficulty: multiple negotiations, veto risk |
| 5 | A work with unclaimed shares in MLC | Cannot be fully cleared at any price. The orphan dead-end |
| 6 | A US book published 1929–1963 | Renewal unresolvable → `UnresolvedQuestion` with exact search terms. Honest boundary |
| 7 | A translated work | Text-side layer split: original PD, translation protected |
| 8 | A work where US and EU answers differ | Jurisdiction toggle changing the verdict |

**Do not skip the hand-verification step.** A demo asset that produces a wrong answer on stage is worse than not having it.

---

## 6. Schedule

### DONE — Aug 24–25

- Procurement, GCP project, repo with MIT license in first commit
- Design pass: Entry, Progress, Result complete; design system extracted to `docs/design-system.md`
- **Spike passed.** Rules engine (`rules/`) written, 35 tests green under pytest. Recording selection, date-basis discipline, and writer cross-checking all verified against live APIs.

### Aug 26 – Aug 30 — pipeline (5 days)

Cache layer first (it's now the latency fix, not an optimization), then MLC integration if access arrived, renewal research via Tier 3, disagreement logic, assembly. Command line output only.

**Gate, end of Aug 30:** query in → complete cited multi-layer response out, unattended, under 90 seconds cold.

### Aug 31 – Sep 3 — product (4 days)

Frontend from the approved design. Cloud Run deploy. Handoff panel. Firestore cache. README with architecture diagram.

**Gate, end of Sep 3:** hosted URL works cold, for a stranger, on a machine that isn't yours.

### Sep 4–6 — hardening and freeze (3 days)

**Sep 5 morning: feature freeze.** Verify all demo assets by hand. Pre-warm cache. Fix only what's broken.

### Sep 7–8 — package and submit

Video (budget a full day, 5–10 takes). Devpost writeup. DQ checklist. **Submit Sep 8.**

---

### Archive — Aug 24 procurement list (complete)

Ordered by blocking risk.

1. **Request MLC Public Search API access** (`publicapi@themlc.com` or themlc.com/dataprograms). Unknown wait, no equal-quality fallback.
2. **Request Gemini Enterprise Agent Platform / Agent Builder access.**
3. **Ask the organizers, on the Devpost forum, whether ADK + Vertex AI satisfies the "Agent Builder" requirement.** See §8.1 — this is a live eligibility ambiguity and the answer changes your critical path.
4. Register on Devpost, select the Parallel track.
5. GCP project: enable Vertex AI, Agent Builder, Cloud Run, Firestore. **Set a billing budget alert.**
6. Install Parallel Search MCP into your coding agent (free, no key).
7. Parallel API key; run the Task quickstart; confirm `output.basis` citations.
8. Spotify developer credentials.
9. Public GitHub repo, **MIT license in the initial commit**, `schemas.py` in the second.

### Archive — superseded schedule

The pre-spike plan (spike Aug 25–26, design Aug 26–27, pipeline Aug 27–31, product Sep 1–4) is
superseded by the DONE / Aug 26–30 schedule above. Retained only as a record of what was planned;
**do not take dates from here.**

---

## 7. Disqualification checklist

- [ ] Repository public
- [ ] Open-source license file at root, visible in GitHub's About sidebar
- [ ] Google Cloud services imported and called in code — not just named in README
- [ ] Parallel imported and called in code — not just named in README
- [ ] Repo contains all source, assets, and run instructions
- [ ] Hosted URL live and reachable during judging
- [ ] Demo video ≤ 3 min, public on YouTube or Vimeo, English or subtitled
- [ ] Video shows the project functioning as built — not a cinematic trailer
- [ ] Parallel track selected on the form
- [ ] Devpost submission form complete
- [ ] Official rules re-read for partner-track-specific requirements

---

## 8. Open risks

### 8.1 Eligibility ambiguity — resolve today

The rules require an agent "powered by Gemini and Google Cloud Agent Builder." It is **not clear** whether the open-source ADK running against Vertex AI satisfies this, or whether provisioned Gemini Enterprise Agent Platform access is mandatory.

This matters enormously: ADK is `pip install` and available immediately; Gemini Enterprise provisioning may take days. **Ask on the Devpost forum today.** If ADK counts, your critical path shortens by whatever the provisioning wait would have been.

Either way, build the pipeline as plain Python that ADK wraps. Then provisioning delay never blocks real work.

### 8.2 Other risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Latency: MB recording selection 20-30s** | **High** | Persistent cache keyed by MBID; cap pagination; minimize work-rels sweep. See §4.6. Now the top technical risk |
| **Renewal wall: most 20th-c. works land in 1931-1963** | **High** | Tier 3 research (Stanford Copyright Renewal DB, USCO records, CCE scans) before falling back to UnresolvedQuestion |
| MusicBrainz 503s / TCP resets at 1 req/s | **High** | Backoff + degrade to Tier 3. "Tier 2 degrades, never fails" is necessary, not optional |
| Agent Builder access delayed | Medium | §8.1. Plain-Python pipeline that ADK wraps |
| MLC access delayed or refused | Medium | Composition layer degrades to Tier 3. Core demo survives — it needs only MB dated relations plus arithmetic |
| Confidence never reaches HIGH | Medium | Every spike case came back MEDIUM. Recalibrate: dated performance relation + corroborated writers + ISWC should reach HIGH, or the dimension carries no information |
| Wrong recording entity selected | Medium | Artist required; alternates surfaced; earliest dated session preferred |
| Scope creep returns | High | §2 cut list is binding |
| Schema drift mid-build | Medium | `schemas.py` changes are decisions, not edits |


---

## 9. Decision log

Recording reversals so the reasoning isn't lost and doesn't get re-litigated.

| Date | Decision | Why |
|---|---|---|
| Aug 24 | Parallel track over Grafana / ClickHouse / IBM / Replit | No infrastructure setup tax; thinnest field; best fit for a research-shaped problem |
| Aug 24 | "Can I Use This?" over script clearance | Broader audience, faster demo, absorbs the clearance concept anyway |
| Aug 24 | Music demoted after discovering Songview has no API | Believed music had no Tier 2 |
| Aug 24 | **Music restored as primary** | MLC Public Search API covers composition ownership; MMA/CLASSICS makes the recording layer pure arithmetic. Better than a Songview API would have been |
| Aug 24 | Images cut | Weakest Tier 2, no authoritative source, reverse-image is its own subsystem |
| Aug 24 | Alternatives engine reduced to curated static | Same user value, no runtime research cost |
| Aug 24 | Monitor and batch cut | Not load-bearing; schedule was underwater |
| Aug 25 | **Spike passed; music architecture revised** | Work links exist and Wikidata is clean. Real risks are recording selection and true first-publication date |
| Aug 25 | `first-release-date` may never drive a confident determination | Returned a 1975 reissue for a 1928 session — 42 years wrong |
| Aug 25 | Writer lists cross-checked against Wikidata | MB omitted a co-writer; life+70 needs the last surviving author |
| Aug 25 | Renewal promoted to Tier 3 research | 4 of 6 real cases hit the 1931-1963 window; auto-undetermined would gut the product |
| Aug 25 | Caching promoted from optimization to requirement | Recording selection costs 20-30s at the MB rate limit |
