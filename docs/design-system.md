# Design System — The Registry

Extracted from the three approved screens: Entry, Progress, Result v3. This is the authoritative token set for the build. Where the screens drifted, the corrected value is noted.

---

## Type

Two families. `Archivo` (400/500/600/700/900) and `IBM Plex Mono` (400/500/600, plus 400 italic). Both from Google Fonts.

Exactly six sizes. No decimals, no intermediate values.

| px | Token | Role |
|---|---|---|
| 12 | `META` | Mono labels: tiers, dates, section headers, stamp metadata |
| 16 | `BODY` | Plain-English explanations; mono evidence values and search strings |
| 21 | `TITLE` | Layer names, question titles |
| 28 | `HEADLINE` | The one-line why; layer verdict words |
| 38 | `STAT` | Clearance numbers; the progress source counter |
| 64 | `VERDICT` | The answer. Deliberately past the scale's next step |

Weights in use: 500, 600, 700, 900. Standardize on **500 (mono values), 600 (labels/emphasis), 700 (titles), 900 (verdict only)**.

### The mono rule

**Mono is for evidence values only.** Dates, years, percentages, identifiers, ISWC/ISRC/MBIDs, source citations, search strings, catalog numbers.

**Archivo for everything else.** Labels, section headers, button text, the query line, all explanatory prose, verdict words.

Target roughly 30/70 mono to sans. The screens currently overshoot — enforce this in the build rather than inheriting the ratio from the markup.

---

## Color

Six colors. Nothing else except INK derived opacities.

| Hex | Token | Job |
|---|---|---|
| `#FAFAF4` | `PAPER` | The ground. One continuous document — no card grid |
| `#16233A` | `INK` | All text and rules. Also the UNDETERMINED stamp, dashed |
| `#2244AA` | `LEDGER_BLUE` | Accent: links, controls, focus, copy buttons, selected state. All interaction |
| `#1E6B47` | `STAMP_GREEN` | CLEAR and CLEAR—CONDITIONS |
| `#6D28D9` | `STAMP_VIOLET` | LICENSE REQUIRED |
| `#B3261E` | `STAMP_RED` | Rights semantics only: RESTRICTED and the blocking rule. **Never error, never hover** |

### On the dark band

| Hex | Token | Job |
|---|---|---|
| `#8FACF2` | `BLUE_ON_INK` | Controls and links reversed out of the INK band. 7.0:1 on INK |

### Derived — INK opacities only

| Value | Use |
|---|---|
| `rgba(22,35,58,0.7)` | Secondary text |
| `rgba(22,35,58,0.2)` | Feint ruling, dashed dividers |

**Drift to correct:** the screens use eight INK opacities (0.7, 0.55, 0.45, 0.4, 0.35, 0.3, 0.2, 0.15). Collapse to **two**: 0.7 and 0.2.

**Drift to remove:** `#7FD6AC` and `#C9B3F5` appear once each on Progress — tints of stamp green and violet. Not in the system. Use the base colors or an INK opacity.

### Contrast, verified

On `PAPER`: INK 15.01 · LEDGER_BLUE 8.10 · STAMP_VIOLET 6.78 · STAMP_RED 6.24 · STAMP_GREEN 6.17
On `INK`: PAPER 15.01 · BLUE_ON_INK 7.00

All pass AA. `LEDGER_BLUE` on `INK` is 1.85 — never use it there; that's what `BLUE_ON_INK` is for.

---

## Structure

- **No cards.** One continuous ruled document on PAPER. Regions separated by rules and space, not boxes.
- **Radius: 6px, single value.** Screens contain stray `0`, `1px`, `2px` — normalize to 6px or none.
- **Rules:** 1px solid INK for major dividers; 1px dashed `rgba(22,35,58,0.2)` for minor.
- **Blocking layer:** left rule in STAMP_RED plus an explicit `BLOCKING — THIS LAYER SETS THE ANSWER` label. The rule alone shouldn't carry it; keep the label and the spacing.
- **Non-required layer:** below a dashed divider, labeled `NOT REQUIRED FOR THIS PURPOSE — SHOWN FOR REFERENCE, EXCLUDED FROM THE ANSWER`. Present, visibly outside the answer.

---

## Components

| Component | Notes |
|---|---|
| `VerdictBanner` | INK band. VERDICT 64/900 in PAPER, HEADLINE 28, controls, confidence. **Cap at four elements** |
| `ControlGroup` | Purpose and territory selectors. Selected = LEDGER_BLUE fill (or BLUE_ON_INK on the band) |
| `LayerRow` | Verdict word left (TITLE, stamp color), name + mono metadata, explanation, confidence, evidence link |
| `HolderRow` | Name, role, admin badge, share, territory, enforcement |
| `EvidenceItem` | Source name, link, retrieval date, authoritative flag |
| `ConfidenceIndicator` | Tick marks + label. One visual language everywhere |
| `HandoffLink` | With visible tier: deep link / pre-filled search / guided manual |
| `LedgerLine` | Progress: timestamp, source, result count. Struck through on failure |
| `CandidateCard` | Disambiguation — not yet designed |
| `StatCounter` | STAT 38, mono. Progress source tally |

---

## Motion

- Verdict re-stamp on toggle: **under 150ms.** The matrix is client-side; toggling must feel instant.
- Ledger lines append, never animate in from off-screen.
- `prefers-reduced-motion: reduce` disables all of it. Already wired in the screens — keep it.

---

## Known defects to fix in the build

1. **Wrapping collisions.** Present on Entry (Begin research button over adjacent text; example titles over descriptions) and previously on Result. Text that wraps must push neighbors down. Suspect fixed heights or `align-items: baseline` with `margin-left: auto`.
2. **No media queries** on Entry or Result; one on Progress. Needs a real narrow breakpoint, verified at 380px — especially whether the blocking annotation survives with no margin.
3. **Eight INK opacities** → collapse to two.
4. **Two off-palette colors** on Progress → remove.
5. **Mixed radii** → 6px only.
6. **Mono overuse** → enforce the 30/70 split.

---

## Note on the source files

The `.dc.html` files are Design Composer format — `<x-dc>`, `<sc-if>`, `<dc-import>`, `{{ }}` bindings, `support.js` runtime. **Not React, not plain HTML.** Use them as visual reference only; the inline styles are real CSS and translate directly, but the templating must be rewritten in React.

The three current screens are `docs/design/entry.dc.html`, `progress.dc.html` and `result-v3.dc.html`. Earlier Result revisions were rejected and are not in the repository.
