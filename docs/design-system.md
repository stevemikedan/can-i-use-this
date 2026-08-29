# Design System — The Registry

Extracted on 29 Aug 2026 from the five files in `docs/design/`: Entry Screen, Progress Screen, Result Screen v3, Disambiguation Screen, Narrow Preview. Every value below appears in that markup; nothing is aspirational. Where the build must map a visual to the data model, the `schemas.py` value is named.

The `.dc.html` files are Design Composer format (`<x-dc>`, `<sc-for>`, `<sc-if>`, `{{ }}` bindings, `support.js`). **Visual reference only.** Their inline styles are real CSS and translate directly; the templating is rewritten in React. Narrow Preview is a harness that frames the other three at 380px — its `#E4E4DC` ground and `#999` iframe border are the harness, not the product.

---

## 1. Type

Two families, from Google Fonts:

- **Archivo** — weights 400, 500, 600, 700, 900, plus 400 italic. Everything that is not an evidence value.
- **IBM Plex Mono** — weights 400, 500, 600. Evidence values only.

Base: `font-family: 'Archivo', sans-serif; font-weight: 500; color: INK; background: PAPER`.

### Six sizes — the complete scale

Counted across all five files: 12 (75 uses), 16 (57), 21 (6), 28 (4), 38 (2), 64 (1). No other size exists.

| px | Token | Where it appears | Weight · tracking · leading |
|---|---|---|---|
| 12 | `META` | Eyebrow labels (section heads, band labels, `QUERY`, `PURPOSE OF USE`) · tags and pills (tier, effort, admin badge) · control buttons · mono metadata (dates, expiry, catalog, timestamps, `retrieved …`) · confidence labels · small secondary notes · disclaimer · running tally | 600 uppercase, tracking 0.08–0.14em; mono at 500; disclaimer 500 at 1.7 leading |
| 16 | `BODY` | Prose (rules, why-it-matters, notes) · links and text toggles · primary button · holder names · mono evidence values and search strings · the band query line · **small stamps** (non-required layer, layer chips, `CLEAR` on alternatives, example stamps) | 500 at 1.5–1.55 leading; links/toggles 600; small stamps 700 uppercase 0.04em |
| 21 | `TITLE` | Layer titles · open-question titles · candidate artist · Entry tagline · `Record complete` | 700; tagline 500 at 1.4; `Record complete` 700 uppercase 0.02em |
| 28 | `HEADLINE` | The one-line why on the band · **non-blocking layer stamp** · Progress query · Entry example titles · Entry input at narrow | 500 at 1.3 (headline); 700 at 1.05–1.2 elsewhere |
| 38 | `STAT` | **Blocking layer stamp** · clearance numbers (mono) · elapsed clock (mono) · Entry input · masthead / verdict at narrow | 700 (stamp, input); mono 500 at leading 1; 900 at narrow display |
| 64 | `VERDICT` | The verdict word · the masthead `Can I use this?_` · `Which one?` | 900, leading 1, tracking −0.01em, uppercase, `text-wrap: balance` |

Display size drops one step at narrow: 64 → 38 (masthead, verdict, `Which one?`), input 38 → 28. Nothing else changes size.

### Tracking, in use

`0.14em` section eyebrows · `0.12em` band masthead label, `BLOCKING —` label, evidence fact label · `0.10em` effort pill, chip name, clearance stat label · `0.08em` tier tag, `NEW INQUIRY`, copy button, ledger status · `0.06em` admin badge, expiry line · `0.04em` small stamps, primary button · `0.02em` control buttons, `Record complete` · `0.01em` layer stamps · `−0.01em` VERDICT.

### Leading, in use

`1` display and mono stats · `1.05` layer stamp · `1.15` example titles · `1.2` Progress query · `1.3` headline · `1.4` tagline · `1.5` notes and section subtitles · `1.55` body prose · `1.7` disclaimer.

### Measures

`40ch` headline · `42–44ch` band prose · `48ch` question title · `56–58ch` clearance summary, shortcut prose · `60–62ch` rules and reasoning · `64–70ch` notes · `78ch` disclaimer.

### The mono rule

**Mono is for evidence values only:** dates, years, timestamps, expiry lines, percentages, shares, catalog and matrix numbers, identifiers (MBID, ISWC, ISRC), `retrieved …` stamps, clearance statistics, the elapsed clock, search strings, the title echoed on Disambiguation (`Take Five`).

**Archivo for everything else:** labels, section heads, button text, stamps, verdict words, names, all prose.

The markup uses mono in 20 declarations against ~100 Archivo ones; the build should land near 30/70 by area. In the data model, mono is exactly: `ResearchedFact.value` when it is a date, year, number or identifier; `Source.retrieved_at`; `Identifier.value`; `UnresolvedQuestion.search_terms`; `HandoffLink.paste_string`; `PipelineEvent.elapsed_ms`.

---

## 2. Color

Six colors plus one control color for the band, and six derived tints. Nothing else appears in the product markup.

| Hex | Token | Job |
|---|---|---|
| `#FAFAF4` | `PAPER` | The ground; text on the band |
| `#16233A` | `INK` | Text, major rules, the band; the `UNDETERMINED` stamp (dashed); selected-control text on the band |
| `#2244AA` | `LEDGER_BLUE` | All interaction on paper: links, text toggles, focus rings, primary and copy buttons, selected controls, the `IN PROGRESS` status, the live caret line |
| `#1E6B47` | `STAMP_GREEN` | `CLEAR` and `CLEAR — CONDITIONS`; `COMPLETE` status; `Record complete`; stamped ledger lines |
| `#6D28D9` | `STAMP_VIOLET` | `LICENSE REQUIRED` |
| `#B3261E` | `STAMP_RED` | **Rights semantics only:** `RESTRICTED`, the blocking left rule and its label, a failed source's note and `FAILED` mark in the ledger. Never error chrome, never hover |
| `#8FACF2` | `BLUE_ON_INK` | Controls and links reversed out of the band: `NEW INQUIRY`, `QUERY` eyebrow, the verdict's terminal glyph (`.` `_` `?`), selected control fill, unselected control border/text, confidence ticks, focus rings on the band |

### Derived — the only tints

| Value | Token | Use |
|---|---|---|
| `rgba(22,35,58,0.7)` | `INK_70` | Secondary text on paper: subtitles, notes, mono metadata, confidence labels, unselected control borders, struck-through failed sources, queued section titles |
| `rgba(22,35,58,0.2)` | `INK_20` | Feint rules (solid and dashed), tag borders, evidence left rule, the empty confidence tick |
| `rgba(250,250,244,0.72)` | `PAPER_72` | Secondary text on the band: eyebrows, freshness line, `typically 30–90 seconds`, unresolved chip text |
| `rgba(250,250,244,0.25)` | `PAPER_25` | Chip borders on the band; the empty confidence tick on the band |
| `rgba(34,68,170,0.18)` | `BLUE_18` | `::selection` only |
| `rgba(34,68,170,0.05)` | `BLUE_05` | Hover wash on list rows that are links (examples, candidates) |

Buttons on the band hover with `filter: brightness(1.12)` — no extra color.

### Stamps ↔ `Verdict`

| `schemas.Verdict` | Word | Color | Underline (layer stamp) |
|---|---|---|---|
| `clear` | Clear | `STAMP_GREEN` | 4px solid green |
| `clear_with_conditions` | Clear — conditions | `STAMP_GREEN` | 4px solid green |
| `license_required` | License required | `STAMP_VIOLET` | 4px solid violet |
| `restricted` | Restricted | `STAMP_RED` | 4px solid red |
| `undetermined` | Not determined | `INK` | 2px **dashed** ink |

Verdict word on the band: 64/900 in `PAPER` with the terminal glyph in `BLUE_ON_INK`. Verdict is always uppercase via `text-transform`, never typed in caps.

### Confidence ↔ `Confidence`

Four ticks. Filled: `high` 4 · `medium` 3 · `low` 2 · `none` 1. Filled tick `INK`, empty `INK_20`; on the band, filled `BLUE_ON_INK`, empty `PAPER_25`. Three sizes: overall 6×16 gap 3 · layer 5×13 gap 3 · evidence 4×11 gap 2. Always followed by the label in words (`medium confidence`).

### Contrast, verified

On `PAPER`: INK 15.0 · LEDGER_BLUE 8.1 · STAMP_VIOLET 6.8 · STAMP_RED 6.2 · STAMP_GREEN 6.2 · INK_70 ≈ 7.6. On `INK`: PAPER 15.0 · BLUE_ON_INK 7.0 · PAPER_72 ≈ 8.5. All AA. `LEDGER_BLUE` on `INK` is 1.85 — never; that is what `BLUE_ON_INK` is for.

---

## 3. Structure

### Page

- One column, `max-width: 920px`, centered. **No cards** — one continuous ruled document.
- The **band**: `INK` background, `PAPER` text, full-bleed; inner padding `28px 24px 48px` (Result, Entry, Disambiguation) or `28px 24px 40px` (Progress). Narrow: `24px 16px 36px` / `24px 16px 32px`.
- The **document**: padding `0 24px 80px`; narrow `0 16px 64px`.
- **Breakpoint: 560px**, the only one. Below it: band and document padding tighten, display sizes drop one step, list rows stack. Everything else is `flex-wrap`. The layout must survive at 380px (Narrow Preview) — including the blocking frame with its 4px red rule and the `EFFORT` pill.

### Rules — the whole vocabulary

| Rule | Use |
|---|---|
| `1px solid INK` | Under every section head; under the Progress log head |
| `2px solid INK` | Above the running tally |
| `3px solid INK` | Entry input underline (focus: `LEDGER_BLUE`) |
| `1px solid INK_20` | Between rows (layers, examples, candidates, alternatives, ledger sections); the blocking frame's border; tag borders |
| `1px dashed INK_20` | Holder rows, ledger lines, the search-terms box, the composition-shortcut box |
| `2px dashed INK_20` | The non-required divider, the scope footer, the escape hatch |
| `2px solid INK_20` | Left rule on each evidence item |
| `4px solid <stamp color>` / `2px dashed INK` | Under a layer stamp |
| `4px solid STAMP_RED` | Left rule of the blocking layer frame |
| `1px solid PAPER_25` / `1px dashed PAPER_25` | Layer chips on the Progress band: resolved / researching |

### Radius

**6px, the single value** (14 uses): control buttons, tags and pills, admin badge, primary and copy buttons, the blocking frame, the search-terms box, the composition-shortcut box, layer chips. Nothing is rounded otherwise.

### Spacing

Sections: `margin-top: 56px` (first after the band) then `64px`. Section head: `padding-bottom: 14px` over its rule, `gap: 6px` between eyebrow and subtitle. Row padding: layers `28px 4px` · examples `24px 4px` · candidates `18px 4px` · alternatives `16px 0` · holders `12px 0` · ledger lines `9px 0` · ledger sections `22px 0 6px`. The blocking frame: `margin: 28px 0; padding: 24px 28px` (narrow `18px 16px`). Within a layer row: `gap: 24px 32px`; the stamp column `flex: 0 1 240px; min-width: 180px`, the body column `flex: 1 1 380px; min-width: 240px`. Inline groups `gap: 6px 14px`; link lines `gap: 6px 10px`; controls `gap: 8px`; chips `gap: 12px`.

---

## 4. Interaction

### Controls (purpose, territory)

Segmented buttons, `12/600`, tracking 0.02em, padding `10px 14px`, radius 6, `aria-pressed`. On paper: selected `LEDGER_BLUE` fill / `PAPER` text; unselected transparent with `1px solid INK_70` border, `INK` text; hover border `LEDGER_BLUE`. On the band: selected `BLUE_ON_INK` fill / `INK` text; unselected transparent with `BLUE_ON_INK` border and text; hover `brightness(1.12)`. Transition 0.15s.

Purpose labels ↔ `schemas.Intent`: `Documentary — distributed` → `film_tv` · `Sample — commercial release` → `commercial` · `New recording — you perform it` → `rerecord`. Territory ↔ `Jurisdiction`: `US` `UK` `EU`. Changing either on Result re-renders instantly from the matrix already on the client (`all_determinations` covers every jurisdiction; `REQUIRED_LAYERS` decides which layers count). On Disambiguation, the composition shortcut sets `rerecord` and **re-runs the query** — it changes the required-layer set and therefore the verdict.

### Links and toggles

Links: `LEDGER_BLUE`, underline 1.5px, offset 3px, hover `INK`. Text toggles (`Holders & evidence`, `Breakdown`, `Show links`, `Where to check…`): a `<button>` styled as a link, `16/600`, `aria-expanded`. Focus everywhere: `outline: 2px solid LEDGER_BLUE; outline-offset: 2px` (band: `BLUE_ON_INK`).

### Buttons

Primary (`Begin research`): `LEDGER_BLUE` fill, `PAPER` text, `16/600` tracking 0.04em, padding `14px 26px`, hover `INK`. Copy (`COPY SEARCH` → `COPIED ✓` for 1.6s): `12/600` tracking 0.08em, padding `11px 18px`, same colors.

### Row links

Example rows and candidate rows are whole-row `<a>`s: `INK` text, no underline, hover `BLUE_05` wash, trailing `Open the record →` / `Research this →` in `LEDGER_BLUE 16/600`.

### Motion

- Verdict re-stamp on a control change: opacity 0.15 → 1, **140ms** ease-out, on the verdict word only.
- Progress caret: `▊` blinking 1s step-end after the live line.
- Ledger lines append in place; nothing slides in. No layout shift when a layer resolves — chips and sections are ruled in from the start as `QUEUED` / `Researching…`.
- `prefers-reduced-motion: reduce` disables all of it.

---

## 5. Component inventory — from the markup

Each component names the design file it comes from and the data it binds to.

**Shared**

| Component | Anatomy | Binds to |
|---|---|---|
| `Band` | Full-bleed `INK`; top line = masthead label (12/600, 0.12em) left, context (`PAPER_72`) right; then screen-specific content | — |
| `Eyebrow` | 12/600 uppercase, tracking 0.12–0.14em; `INK` on paper, `PAPER_72` or `BLUE_ON_INK` on the band | — |
| `SectionHead` | `Eyebrow` + 16 subtitle in `INK_70`, `padding-bottom: 14px`, `1px solid INK` rule; may carry a `TextToggle` at the right | — |
| `Stamp` | Verdict word, uppercase, 700, in stamp color; sizes 38 (blocking, with 4px underline), 28 (layer, underline), 16 (small: chips, non-required, alternatives, examples) | `Verdict` |
| `ConfidenceTicks` | 4 ticks + label; three sizes; band variant | `Confidence` |
| `Controls` | Segmented purpose / territory buttons; paper and band variants | `Intent`, `Jurisdiction` |
| `TextToggle` | Link-styled button with `aria-expanded` | — |
| `PrimaryButton`, `CopyButton` | See §4 | — |
| `Tag` | 12/600, tracking 0.08–0.10em, `1px solid INK_20`, radius 6, padding `1px 7px` (tier) or `3px 9px` (effort) | `LinkTier` → `DEEP LINK` / `PRE-FILLED SEARCH` / `GUIDED MANUAL`; `estimated_effort` → `EFFORT: MINUTES / HOURS / SPECIALIST` |
| `Disclaimer` | 12/500 at 1.7, `INK_70`, 78ch, `margin-top: 56px` | `RightsResponse.disclaimer` |

**Result**

| Component | Anatomy | Binds to |
|---|---|---|
| `VerdictBand` | Masthead `CAN I USE THIS? — RESEARCH RECORD` · freshness (mono, `PAPER_72`) · `NEW INQUIRY` · `QUERY` eyebrow + query line · verdict word 64/900 + terminal `.` · headline 28/500 · `PURPOSE OF USE` controls · `TERRITORY` controls · `CONFIDENCE` ticks + label | `overall_verdict`, `overall_headline`, `overall_confidence`, `generated_at`, `served_from_cache`, `query` |
| `LayerRow` | Two columns: stamp + mono expiry line (`EXPIRES 1 JAN 2029` / `EXPIRED 1 JAN 2024` / `—`) left; title 21/700 + mono subtitle, rule prose, `ConfidenceTicks` + `TextToggle` right. **Blocking variant:** `BLOCKING — THIS LAYER SETS THE ANSWER` label in `STAMP_RED`, frame `1px solid INK_20` with `4px solid STAMP_RED` left rule, radius 6, stamp at 38. First non-blocking row has no top rule | `LayerVerdict`, `Determination.expiry_year`, `Determination.status`, `is_required`, the layer's `identifiers` for the subtitle |
| `LayerDetail` | Opens under the row: `1px solid INK_20` top rule; `RIGHTS HOLDERS` (optional italic note) and `EVIDENCE` | `holders`, `term_facts` |
| `HolderRow` | `1px dashed INK_20` top; name 16/600 · role 12 `INK_70` · `ADMINISTERS LICENSING` badge (`INK` fill, `PAPER`, radius 6) · mono line: share, territory, enforcement · optional contact link + `↗ licensing contact` | `RightsHolder` (`is_administrator`, `share_percent`, `territory`, `enforcement_posture`, `contact_path`) |
| `EvidenceItem` | `2px solid INK_20` left rule, `padding-left: 16px`; fact eyebrow + small ticks; mono value 16; reasoning prose `INK_70`; `SourceLine`s | `ResearchedFact` |
| `SourceLine` | `Tag` (tier) · name (link if URL) · mono `retrieved <date>` · optional italic excerpt on its own line | `Source` (`method` → tier label, `url`, `retrieved_at`, `excerpt`) |
| `ClearanceRow` | `CLEARANCE` eyebrow left; summary + `Breakdown` toggle right; opens to three `StatBlock`s (38 mono + 12 label) and detail prose | `ClearanceProfile` (`party_count`, `unclaimed_share_percent`, `difficulty`) |
| `NonRequiredRow` | Under `2px dashed INK_20`; label `NOT REQUIRED FOR THIS PURPOSE — SHOWN FOR REFERENCE, EXCLUDED FROM THE ANSWER`; small stamp 16; title in `INK_70` | `LayerVerdict` with `is_required=False`, `intent_note` |
| `QuestionRow` | Title 21/700 + `EFFORT` tag; why-it-matters; `TextToggle` → what it would change (`if_yes` / `if_no`), `SearchTermsBox` (`1px dashed INK_20`, radius 6, mono terms 16 + `CopyButton`), `LinkLine`s | `UnresolvedQuestion` |
| `LinkLine` | `Tag` · link · optional note on its own line in `INK_70` | `HandoffLink` (`tier`, `url`, `source_name`, `description`, `navigation_hint`, `paste_string`) |
| `AlternativeRow` | `1px solid INK_20` top; small green stamp `CLEAR` · title 16/600 · creator 12 · why prose with optional link | `Alternative` |
| `RecordsPanel` | `GO TO THE RECORDS` head with `Show links` toggle; groups `VERIFY` / `ACT` (and `RESOLVE`), each a column of `LinkLine`s | `handoff_links` grouped by `purpose` |

**Progress**

| Component | Anatomy | Binds to |
|---|---|---|
| `ProgressBand` | Masthead `— RESEARCH IN PROGRESS` · context `US · DOCUMENTARY` · `QUERY` + query 28/700 · stage line 16 · `ELAPSED` + clock 38 mono + `typically 30–90 seconds` · `LayerChip` strip | `PipelineEvent.message`, `elapsed_ms` |
| `LayerChip` | Radius 6, padding `10px 16px`, min-width 150; name 12/600 + small stamp 16; `1px dashed PAPER_25` + `Researching…` in `PAPER_72` until resolved, then `1px solid PAPER_25` + the stamp word in `PAPER` | `PipelineEvent.partial` (`layers`, then per-layer verdicts when they land) |
| `LedgerSection` | `1px solid INK_20` top; title (Roman numeral + name) in `INK` or `INK_70` if queued; status `QUEUED` (`INK_70`) / `IN PROGRESS` (`LEDGER_BLUE`) / `COMPLETE` (`STAMP_GREEN`) | `PipelineStage` |
| `LedgerLine` | `1px dashed INK_20` top; mono timestamp (`0:14`) · source 16/600 · note 16 `INK_70` · mono mark right (`2 RECORDS` / `STAMPED` green / `FAILED` red). Failed source struck through in `INK_70`, its note in `STAMP_RED`; **corrected, never erased** | `PipelineEvent` (`status`, `message`, `detail`, `degraded`, `error_message`, `sources_consulted`) |
| `Caret` | The live line: text in `LEDGER_BLUE 16/600` + blinking `▊` | the stage currently `started` |
| `RunningTally` | `2px solid INK` top; `sources consulted` / `records retrieved` / `failures on record`, values mono | `sources_consulted`, count of `degraded` |
| `RecordComplete` | `Record complete` 21/700 green + `Open the research record →` | final `assemble` event |

**Entry**

| Component | Anatomy | Binds to |
|---|---|---|
| `Masthead` | `RESEARCH RECORD — NEW INQUIRY` · scope line right · `Can I use this?_` 64/900 · tagline 21/500 | — |
| `Input` | Transparent, `3px solid INK` bottom rule (focus `LEDGER_BLUE`), 38/700 (narrow 28), placeholder `INK_70` | `title` (+ ` — artist`) |
| `Controls`, `PrimaryButton` | As §4; the 30–90 s note beneath in `INK_70` | `Intent`, `Jurisdiction` |
| `ExampleRow` | Whole-row link: title 28/700 + mono meta · small stamp right · note + `Open the record →` | The pre-warmed demo queries; must return warm |
| `ScopeFooter` | `2px dashed INK_20`; `SCOPE OF THE REGISTER` + prose | — |

**Disambiguation**

| Component | Anatomy | Binds to |
|---|---|---|
| `PausedBand` | `— INQUIRY PAUSED` · `Which one?` 64/900 · 28 explanation · `WHAT WE UNDERSTOOD` / `WHAT'S AMBIGUOUS` columns (title echoed in mono) | `stop_for_disambiguation`, `overall_headline`, `query.raw_input` |
| `CandidateRow` | Whole-row link: mono year `flex: 0 0 36px` · artist 21/700 + note · mono issue right · `Research this →` | `Candidate` (`label`, `disambiguator`, `identifiers`) |
| `ShowMore` | `TextToggle`: `Show the other N — mostly later covers and reissues` | `alternate_candidates` beyond the first five |
| `ShortcutBox` | `1px dashed INK_20`, radius 6, padding `20px 22px`; `NOT USING A SPECIFIC RECORDING?` + prose + `Research the composition only →` | sets `Intent.RERECORD` and re-runs |
| `EscapeHatch` | `2px dashed INK_20` top; `None of these is it?` + `Refine the inquiry — add an artist, year, or label →` | back to Entry with the query kept |

**Not in the design files** — build minimal, from `docs/design-reference.md` §3: Boundary (unsupported asset type), Not found, Error. Use the band with a 64/900 word, a 28 explanation, and a single `TextToggle`/link back; no new tokens.

---

## 6. Content rules the markup encodes

- Section eyebrows are nouns in caps: `RIGHTS LAYERS`, `OPEN QUESTIONS — 1`, `ALTERNATIVES`, `GO TO THE RECORDS`, `CLEARANCE`, `ACCESSION LOG`, `CANDIDATES — SHOWING 5 OF 18`.
- Every section head carries one subtitle sentence that says what the section is for.
- Stamps are words, never icons. `Not determined`, not "Unknown".
- Progress copy comes from the pipeline's `PipelineEvent.message` strings, not invented; the Roman-numeral sections group them by stage.
- Failures stay on the record, struck through.
- The disclaimer is present on Result and quiet; never a modal.

---

## 7. What changed since the 25 Aug extraction

Verified against the current markup: INK opacities collapsed to two (0.7, 0.2); the two off-palette tints on Progress are gone; radii are 6px only; the Result, Entry and Disambiguation layouts wrap correctly (flex-wrap on every inline group, no fixed heights); the narrow state is handled at 560px and previewed at 380px. Disambiguation and Narrow Preview are new and covered above. The 38px stamp for the blocking layer, the `EFFORT` pill, the search-terms box with copy, the `VERIFY` / `ACT` grouping and the `NEW INQUIRY` link did not exist in the earlier extraction.
