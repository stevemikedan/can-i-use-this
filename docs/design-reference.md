# Can I Use This? — Design Reference

Reference material for the interface design. Describes what the product does, what data it displays, and what screens and states exist.

---

## 1. The product

Paste a song or a book title. Say what you want to do with it. Get back a researched, cited verdict: whether you can use it, who owns it, roughly what it would cost, what to use instead if you can't, and an honest account of what couldn't be determined.

Users are people about to publish something who are suddenly unsure — a documentary editor with a music cue, a podcaster, a YouTuber, an archivist clearing a backlog. They are not lawyers. They want an answer quickly, and evidence available if they choose to look for it.

### The idea the product turns on

One thing you search for is usually several separately-owned works, each with its own answer.

A song is a **composition** (the song itself, owned by writers and publishers) and a **recording** (a specific performance, owned by a label). These can differ: a 1924 recording may be in the public domain while the song it records is still under copyright — so the overall answer is no.

A book can be a **work**, a specific **edition**, and a **translation**, each with separate terms. An original may be public domain while a modern translation is protected.

Most users don't know this. Learning it is a large part of the product's value. It must never read as a technicality or an error.

### The answer is three-dimensional

The verdict varies along three axes, all of which are user-visible:

- **Layer** — composition vs recording, work vs translation
- **Jurisdiction** — US, UK, EU. Same work, different answers
- **Intent** — a personal project and a distributed film get different answers for the same asset

A hurried user needs one verdict immediately. A careful user needs the whole matrix. Both on one screen.

---

## 2. Data the interface displays

Plain-language inventory of what comes back from the backend.

### Overall verdict
One of five values, each needing a distinct visual treatment:

| Verdict | Meaning |
|---|---|
| **Clear** | Free to use for this purpose |
| **Clear with conditions** | Usable, but something is required — attribution, a specific license's terms |
| **License required** | Protected, but there's a path to permission |
| **Restricted** | Licensing is unlikely, refused, or impossible (e.g. unclaimed ownership) |
| **Undetermined** | Research couldn't resolve it |

Plus a one-line headline explaining why, and an overall confidence level.

### Rights layers
The core of the screen. Each layer carries:

- A kind and label — "Composition (1939)", "Sound recording (1924)"
- Its own verdict, independent of the others
- Whether it is **required** for the current intent. Non-required layers still display, but don't count toward the overall verdict. (Example: if the user intends to commission a re-recording, the original master stops being required.)
- A plain-English explanation of which rule produced the determination
- An expiry year, when computable
- Confidence

### Rights holders
Per layer, often several:

- Name and role — publisher, administrator, label, author, translator, estate
- **Whether they're the administrator.** Publisher and administrator are frequently different entities, and the administrator is the one who actually licenses. Sending someone to the wrong one is a wrong answer.
- Ownership share as a percentage
- Territory, where it varies
- Contact path for licensing, when known
- Enforcement posture — aggressive, standard, permissive, unknown

### Clearance difficulty
Distinct from whether something is protected. How hard it would be to actually clear:

- **Party count** — how many separate people must say yes
- **Unclaimed share percentage** — if any ownership is unclaimed, the work *cannot* be fully cleared at any price. A dead end worth surfacing prominently.
- **One-stop** — whether a single entity controls both publishing and master. Dramatically cheaper and faster; the most useful single signal for a small production.
- An overall difficulty rating and its reasoning

### Evidence
Every asserted fact carries:

- The value
- Confidence — high, medium, low, none
- One or more sources, each with a name, link, retrieval date, whether it's authoritative, and sometimes a short excerpt
- Reasoning, when sources conflicted
- Conflicting values, when they existed. Disagreement between sources is shown, not hidden.

### Disagreement notes
Appear when our determination differs from what an archive or institution claims. Both are shown side by side — the institution's claim is never silently overridden. Includes the likely cause: institutional caution, a reproduction claim over a public-domain original, a jurisdiction mismatch, a stale record, or the possibility that we're wrong.

### Unresolved questions
Things research couldn't settle. Each carries the question, why it matters, what a yes or no would change, which layers it affects, exact search terms to use, links to where it can be resolved, and an effort estimate (minutes / hours / needs a specialist).

These are presented as next steps, not failures.

### Alternatives
When the verdict isn't clear: substitutes that do the same job without the rights problem. Title, creator, why it's similar, its status, and a link.

### Handoff links
Deep links to the specific records behind the verdict, in three groups — **verify** what we determined, **resolve** what we couldn't, **act** on licensing. Each link has a quality tier that should be visible:

- **Deep link** — a stable URL to this exact record
- **Pre-filled search** — search page with terms populated
- **Guided manual** — "search here, paste this exact string." Some sources are scanned card catalogs with no machine access. Saying so honestly is better than a fake link.

---

## 3. Screens

### Entry

**Job:** capture the query, set intent, and convey what this is — in about four seconds.

- A single, generously sized input
- **Intent selector**, prominent. This changes the answer, and users won't know that unless the interface tells them.
- **Jurisdiction selector**, defaulting to US
- **Clickable example queries** that load instantly. The highest-value element here — it's how a first-time visitor understands the product without typing anything.
- A plain statement of scope: music and books/film
- One line of positioning

States: default · focused · typing · submitting

### In progress

**Job:** make 30–90 seconds feel like work being done, not a hang.

Queries are genuinely slow because they're doing real multi-source research. This is a designed screen, not a spinner, and it accounts for a substantial share of total time in the product.

- **Staged pipeline** — classify, identify, decompose, research, apply rules, compare, assemble. Each stage shows started → complete, with elapsed time.
- **Live source counter.** "Consulted 14 sources" reassures in a way a progress bar doesn't.
- **Progressive results.** Layers resolved from fast sources appear immediately while deeper research continues. By the halfway point the user should already be reading something real.
- A calm indicator when a source failed and the system fell back to another

States: running · degraded · slow (past ~60s, acknowledge it) · failed

### Result

**Job:** one clear answer for the impatient, the full matrix for the careful, on one screen.

Regions, top to bottom:

1. **Verdict banner** — the answer, one line of why, confidence
2. **Controls** — jurisdiction and intent toggles. Re-rendering is instant; the full matrix is already client-side. This instantaneous change is one of the best moments in the product and should feel like it.
3. **Layer stack** — the core reveal. Each layer with its own verdict, required-or-not, and when layers disagree, *which one is blocking*. Expandable into holders, shares, and the evidence trail.
4. **Clearance difficulty**
5. **Disagreement note**, when present
6. **Unresolved questions**, when present
7. **Alternatives**, when the verdict isn't clear
8. **Handoff panel**
9. **Disclaimer** — present, quiet, not a modal

States: each of five verdicts × fresh or cached × with or without disagreement × with or without unresolved questions

**The hard part:** a two-layer disagreement must be readable in about three seconds. If someone has to study the screen to understand why the answer is no, the design hasn't done its job.

### Disambiguation

**Job:** when it's unclear which work was meant, ask — before doing any research.

Researching an ambiguous entity produces confidently wrong output, which is this product's worst failure mode. So this screen interrupts the flow deliberately.

- What was understood, and what's ambiguous
- Two to five candidates, each with a real disambiguator: year, artist, edition, translator
- An escape hatch: none of these / refine

Tone matters. "Which one did you mean?" is a competent question, not an error.

### Unsupported asset type

Triggered by images, fonts, characters, footage, trademarks — recognized but not researched.

Shows what was detected, what the tool can't do yet and honestly why, the general rules that apply to that type, where a human would look instead, and an invitation to try a supported type.

Should read as a deliberate scope decision, not a 404.

### Not found

Couldn't resolve the query to any work. Shows what was searched, how to narrow it (add the artist, add a year), and examples.

### Error

The pipeline broke or degraded past usefulness. Shows whatever *was* determined, states plainly what failed, offers retry. Never a stack trace.

### About / methodology

Serves users deciding whether to trust a verdict. Explains the layer model in plain language with the 1924-recording example, where the data comes from, what confidence levels mean, the known limits, and the full not-legal-advice statement.

---

## 4. Flows

```
Entry → submit → In progress → Result
                     ↓
               (ambiguous) → Disambiguation → In progress → Result
```

Within the result, no round trips:

```
Toggle jurisdiction  → instant re-render
Toggle intent        → instant re-render; the required-layer set changes
Expand a layer       → in-page: holders, shares, evidence
Expand an unresolved → in-page: search terms, links
Share                → copy permalink
```

Failure paths:

```
Unsupported type → Boundary screen → suggest a supported query
Unresolvable     → Not found → refine
Pipeline failure → Error, partial results retained → retry
```

Layer detail and unresolved-question detail are in-page expansion, not separate pages. Everything about a verdict lives on the verdict screen.

---

## 5. Cross-cutting states

Defined once, applied everywhere. Consistency here matters more than any individual screen.

| State | Where | Requirement |
|---|---|---|
| **Confidence** — high / medium / low / none | Every fact, layer, verdict | One visual language throughout. Low confidence noticeable without being alarming |
| **Required vs not required** | Layer stack | A non-required layer displays but is visibly excluded from the roll-up. Must not read as "ignored" |
| **Source tier** | Evidence trail | Provenance visible on hover or expansion |
| **Link tier** | Handoff panel | Deep link vs pre-filled search vs guided manual. Honest labeling is a feature |
| **Cached vs fresh** | Result | A quiet timestamp, not a badge |
| **Degraded** | In progress, Result | A source failed and the system fell back. Stated, not hidden |

---

## 6. Quality floor

- Responsive down to mobile. Full mobile-specific design isn't needed; the layout not collapsing is.
- Visible keyboard focus; tab order follows reading order
- `prefers-reduced-motion` respected — the progress screen is animated
- Accessible names on every interactive element
- AA text contrast
- **No layout shift when progressive results arrive.** Easy to get wrong, very visible

---

## 7. Design system needed

- Color tokens as named hex values, including the five verdict states and four confidence levels
- Type scale with assigned roles
- Spacing scale
- Component inventory: verdict banner, layer card, holder row, evidence item, confidence indicator, handoff link, pipeline stage row, candidate card, disclaimer
- Motion rules: what animates, for how long, and what reduced-motion disables

---

## 8. Decisions this design pass should settle

1. How the layer stack communicates disagreement at a glance
2. Whether intent and jurisdiction controls belong in the verdict banner or below it
3. What the progress screen shows at second 5, second 30, and second 75
4. Where confidence appears without becoming visual noise
5. Whether a disagreement note sits inside its layer or above the stack
6. How the handoff panel avoids reading as a footer nobody looks at
