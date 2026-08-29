# Endgame — Aug 29 to Sep 8

The schedule, the cuts, and the gates for the last ten days. This supersedes
`PROJECT.md` §6, whose schedule predates the reading step. Deadline **Sep 9,
2:00pm PDT**; judging **Sep 23 – Oct 7**, and the hosted URL must stay live
through all of it (`COMPLIANCE.md` §6).

## Where things stand — Aug 29

Built and tested (`python -m pytest`, all green):

- The deterministic rules engine, the Tier 2 cache layer, the Parallel Search
  wrappers, the link registry, the music pipeline end to end.
- **The reading step** (`agent/gemini_reader.py`): Gemini via Vertex reads
  Parallel Search evidence into a cited fact or leaves the question open.
  Confidence follows the class of source cited — primary record / rightsholder
  notice / secondary — and the validator caps it; a "not renewed" finding
  needs a primary record.
- **The ADK graph** (`agent/workflow.py`): the pipeline's stages as
  deterministic agents, the two research stages in a `ParallelAgent`, the
  reader's `LlmAgent` the only model on the path. Reproduces the five frozen
  acceptance fixtures byte-for-byte.
- Design: Entry, Progress, Result. Disambiguation and error states not yet
  designed; specify from `design-reference.md`.

- **The API** (`api/`, later on Aug 29): FastAPI over the graph, SSE progress,
  `/healthz` with a real cache round-trip; Dockerfile; `deploy/deploy.sh` with
  the deploy checklist baked in (re-runnable). Local smoke passed; the Cloud
  Run run is the user's `gcloud` step.

Not built: the frontend, MLC.

### The reader against real evidence — Aug 29

First run of the reader over live Parallel Search, gemini-2.5-flash:

| Case | Window | Outcome |
|---|---|---|
| Take Five (1959) | 1986–87 | unresolved — declined to use "a later renewal date for a different version" |
| Mack the Knife (1954) | 1981–82 | unresolved — ignored Easysong's "Copyright renewed ·" boilerplate |
| Summertime (1935) | 1962–63 | unresolved in the first run; later a low-confidence find from a secondary FAQ page |
| Blue Moon (1934) | 1961–62 | **found, medium** — a publisher's permissions notice, "copyright © 1934, renewed 1961" |
| Summertime — Billy Stewart | reissue | **found 1965, low** — three Discogs citations; first live run of the recording-year path |

**One in four is the honest number**, and the three that stayed open did so
for a structural reason: their renewal windows fall after 1977, so the record
is in the Copyright Office's online catalog, which search excerpts cannot
reach — not in the scanned CCE volumes they can. The tool now says exactly
that in the `UnresolvedQuestion` and points the handoff at the online
catalog. The abstentions are the win; a tool that claims to answer everything
is the failure mode.

## Schedule

| Dates | Work |
|---|---|
| Aug 30 | **First Cloud Run deploy, API only** |
| Aug 31 – Sep 3 | Frontend — Entry, Progress, Result, minimal Disambiguation |
| Sep 4 | Redeploy with UI |
| Sep 5–6 | Harden, hand-verify demo assets, pre-warm cache. **Freeze Sep 6** |
| Sep 7 | Video |
| Sep 8 | Writeup, DQ checklist, submit |

If the graph or the API finishes early, deploy early — both finished Aug 29,
so the deploy runs Aug 29 (`deploy/deploy.sh`). Do not pull frontend work
forward: it is a different kind of task and starts clean on Aug 31.

### Why deploy before the frontend

Deploy is where the surprises are — service-account identity instead of ADC,
Firestore IAM, secrets, build config, cold starts. Found against a backend it
costs an afternoon; found on Sep 4 with a video still to make it is a
disaster.

Deploy day must cover:

- `PARALLEL_API_KEY` via Secret Manager
- the Firestore role grant for the Cloud Run service account
- `CACHE_BACKEND=firestore`, and confirmation that the Firestore cache backend
  actually works — it was the one component never exercised until Aug 29,
  when a local write/read round-trip through ADC succeeded against the real
  database (`tier2_cache`, count aggregation working). On Cloud Run
  `/healthz` repeats that probe as the service account.
- Vertex AI access from the service account (the reader has only ever run on ADC)
- `--min-instances=1` before judging; the service stays live Sep 23 – Oct 7
- the billing alert stays on

### The biggest risk

Design is a full quarter of the judging score and no frontend exists. Every
gate below protects the four frontend days.

## Cuts — decisions, not deferrals

- **Text/film as an asset type.** Music only. The skeleton was designed for
  it; it is not being built.
- Chat interface.
- Parallel Monitor.
- Batch / CSV mode.
- Accounts, auth, saved history.
- Skills registry.
- Images, fonts, characters, footage and trademarks stay
  *recognised-but-not-researched* with the boundary note.

## Gated work

**Gated on the frontend being done by end of Sep 2:**

- **Cue sheet mode** (~1 day). A film has 20–40 cues; per-cue verdicts turn
  this from a lookup utility into a production tool.
- **Parallel Search visible in the progress ledger** (~½ day).

**Gated on the frontend being done *and deployed* — candidates for Sep 5, and only then:**

- **Copyright Office online catalog integration** for post-1978 renewal
  windows (works published 1951–1963). This is where three of the four live
  cases stalled. About a day; uncertain payoff (the catalog is a search UI,
  not an API).
- **Parallel Extract on the actual CCE volume text** for pre-1978 windows,
  instead of relying on search excerpts. About a day; uncertain payoff.

Neither is started. Both are "what's next" in the writeup.

**Free, when convenient:** narrow the positioning from "creators" to
documentary and independent film production — the README opening and the
Devpost description.

## For the writeup

- One in four resolving is the honest number. Three of four stayed open for a
  structural reason (post-1978 windows are not reachable by search excerpt),
  and the tool says so and points at the right system. That is a better story
  than a tool that claims to answer everything.
- The reader's judgment is the demonstrable part: it declined a renewal date
  for a different version of the song, ignored a licensing site's "Copyright
  renewed" boilerplate, and rated a publisher's notice medium rather than
  high. Every one of those is a cited, reproducible run (`python -m
  agent.live_cases`).
- Provenance is structural, not prompted: a found fact without a citation
  fails schema validation; confidence is capped by source class in a
  validator; "not renewed" needs a primary record.
- What's next: the two gated integrations above, then MLC for publishers and
  shares, then cue sheets.

## Decided Aug 29 — low-confidence evidence is asymmetric

A low-confidence finding may drive a determination toward *protected*, never
toward *public domain*. If the only evidence for "not renewed" (or for a
recording year that would put the recording out of term) is low confidence,
the layer stays undetermined, the question stays open, and the evidence
appears on it as a lead rather than an answer.

Reason: a wrong "protected" costs someone a license they didn't need; a wrong
"public domain" ends in a takedown or a lawsuit. Summertime resolving to PD
on an audiosparx FAQ is exactly the case that should stay open, even though
the fact is probably correct and the confidence is correctly capped.

Where it lives: `LOW_CONFIDENCE_PD_RULE` in `pipeline/determine.py` (with the
reasoning as a comment), the leads in `pipeline/music.py`
(`renewal_question`, `recording_question`, `year_question`), and the reader's
own version of the rule — a "not renewed" finding needs a primary record.
