# Compliance — Agentic Cinema, Parallel Track

Extracted from the official rules (Aug 25, 2026). **Deadline: Sep 9, 2026, 2:00pm PDT.**

Items marked **CODE** affect what gets built and must be satisfied in the repository. Items marked **PROCESS** are submission logistics.

---

## 1. CODE — Parallel Search API is required at runtime

> *"your project must actively use Parallel's **Search API** at runtime — for example, via the official parallel-web SDK (Python or TypeScript), a supported integration such as the Vercel AI SDK's @parallel-web/ai-sdk-tools or LangChain's ParallelWebSearchTool, or a Grounding configuration using Parallel Web Search as the search provider. Referencing Parallel in your README alone does not satisfy this requirement — the integration must be present in your code."*

**This is the single highest-risk compliance item.** The architecture was specced around Parallel's **Task** API (structured output with `output.basis` citations). Task is not Search. A project built entirely on Task may fail Stage One screening.

**Required design change:**

| Job | API | Why |
|---|---|---|
| **Renewal research** (1931–1963 window) | **Search** | Locating Stanford Copyright Renewal DB / USCO / CCE records is a search problem |
| **First-publication date research** for recordings without a dated performance relation | **Search** | DAHR, discographies, session logs |
| Structured multi-field layer research | Task | Where `output.basis` citations earn their place |
| JS-rendered pages (Songview, ISWCNet) | Extract | Unchanged |

Search must be **called on the primary request path**, not in a utility script or a dead code path. Both Search and Task appearing in the codebase is fine and desirable — Search is the one that is mandatory.

Use the official SDK: `pip install parallel-web`.

---

## 2. CODE — Accepted Google Cloud SDKs

> *"Accepted Google Cloud packages/SDKs: google-adk, google-genai, google-generativeai, or google-cloud-aiplatform (any generation — legacy libraries count equally)."*

**`google-adk` is explicitly accepted.** No Gemini Enterprise Agent Platform provisioning is required. `pip install google-adk` against Vertex AI satisfies the "Agent Builder" requirement. This resolves the open eligibility question in PROJECT.md §8.1.

At least one of these must be imported and actually called at runtime — "a library import, an app/backend entry point, or a loaded agent/flow/MCP config."

---

## 3. CODE — AI tooling restriction

> *"Projects may only use Google Cloud artificial intelligence tools... and the built-in AI-powered features of the specific Partner's product relevant to your chosen track. No other AI models, agent frameworks, or AI APIs are permitted, regardless of vendor — this includes but is not limited to AWS, Microsoft, OpenAI, and Anthropic AI tools. This restriction applies only to AI/agent tooling; it does not restrict your use of other non-AI third-party services (e.g., hosting, databases, standard web frameworks)."*

**At runtime, the project may call only:** Gemini via Vertex AI, other Google Cloud AI services, and Parallel's APIs.

**Must not appear in the shipped code:** OpenAI, Anthropic, AWS Bedrock, Azure OpenAI, Cohere, Mistral, or any non-Google model provider. No LangChain-to-non-Google model paths, no fallback providers, no `openai` or `anthropic` package in `requirements.txt`.

Non-AI third-party services are unrestricted: httpx, FastAPI, SQLite, MusicBrainz, Wikidata, HathiTrust, MLC, Spotify, Firestore, Cloud Run.

Development tooling is treated separately — the IBM and Replit tracks explicitly *require* their AI tools be used during development, which establishes that dev-process tools are not what this restricts. Regardless, keep the runtime clean.

---

## 4. CODE — Repository

- **Public**, on GitHub, GitLab, or Bitbucket
- **Open-source license file detectable at the top of the repository page (About section).** MIT in the first commit satisfies this — verify it actually renders in the sidebar
- Must contain all source, assets, and instructions needed to run
- Must demonstrate Google Cloud and Parallel usage **at runtime, imported and actually called** — not named in the README

---

## 5. CODE — Platform

Must run on web, Android, or iOS. Web satisfies this.

---

## 6. PROCESS — The hosted URL must stay live through Oct 7

Judging runs **Sept 23 – Oct 7, 2026**, two to four weeks *after* submission.

Cloud Run must remain deployed and reachable that entire time. Budget for a month of uptime, keep the billing alert active, and do not tear anything down after submitting. A dead URL during judging is a failed submission.

---

## 7. PROCESS — Video constraints are tighter than typical

- ≤ 3 minutes (only the first 3 minutes are evaluated)
- Public on **YouTube or Vimeo**; link on the submission form
- English, or English subtitles
- Must show the project **functioning on the platform it was built for**
- **Must not display any third-party advertising, slogan, logo, or trademark**
- **Must be an original, unpublished work that does not incorporate any content or element owned by a third party**

**Specific hazards for this project.** The demo uses real recordings and compositions as *subjects of research*. Displaying titles, dates, and factual determinations is fine. What is not:

- **Play no music.** Not a clip, not background, not under narration.
- **No album art, no label logos, no artist photographs.**
- **No streaming-service UI in frame** — no Spotify, Apple Music, or YouTube Music windows.
- Keep browser tabs, bookmarks, and desktop clean; incidental logos count.

---

## 8. PROCESS — Other

- **New projects only**, created during the Contest Period (July 27 – Sep 9, 2026)
- Submission form complete, **Parallel track selected**
- Text description covering features, technologies, data sources, and findings/learnings
- Hosted project URL provided
- Code repository URL provided
- **$100 Google Cloud credits: request form due Aug 31, 2026, 11:59 PM PST.** Approval takes 1–5 business days

---

## 9. Judging criteria — equally weighted

| Criterion | Question asked |
|---|---|
| Technological Implementation | How well is it built, and how effectively does it use Google Cloud *and* the Partner services? |
| Design | Does it deliver a complete, coherent product experience, not just a technical proof of concept? |
| Potential Impact | Credible, specific case for solving a real problem for a real audience — and does the demo actually show it? |
| Quality of the Idea | Creative, non-obvious use of Google Cloud and the Partner services; genuine understanding of the problem space |

**Stage One is pass/fail** on whether the submission includes all requirements and "reasonably applies both the required data provided by Partner and Google Cloud products." Screening may be automated — which is precisely why the Parallel Search call must be plainly visible in the code.

---

## Pre-submission checklist

- [ ] `parallel-web` imported and **Search API called on the primary request path**
- [ ] `google-adk` (or accepted equivalent) imported and called at runtime
- [ ] No non-Google AI providers anywhere in `requirements.txt` or the runtime
- [ ] Repo public; license visible in GitHub About sidebar
- [ ] Hosted URL live and reachable cold from a machine that isn't yours
- [ ] Cloud Run funded and monitored through **Oct 7**
- [ ] Video ≤ 3 min, public, English, no music, no logos, no third-party content
- [ ] Devpost form complete, **Parallel track selected**
- [ ] $100 credits requested (by Aug 31)
- [ ] Rules re-read in full before submitting
