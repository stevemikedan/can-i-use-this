// About — for users deciding whether to trust a verdict, and for judges
// checking the stack. The layer model in plain language, the sources split
// into records we READ and destinations we POINT TO (that distinction is the
// architecture), the agent stack, what confidence means, the known limits,
// and the full disclaimer. Same design system, no new tokens. One text
// measure throughout (80ch) so the column reads deliberate against the
// 920px container instead of arbitrarily short.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Band, Doc, Eyebrow, SectionHead, TextToggle } from '../components/ui'

function P({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <p className={`m-0 text-body leading-[1.55] max-w-[80ch] ${muted ? 'text-ink-70' : ''}`}>{children}</p>
}

/** One source or destination: mono tier tag, name, role line, optional detail behind a toggle. */
function SourceRow({ tier, name, role, detail }: { tier: string; name: ReactNode; role: ReactNode; detail?: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex gap-y-1 gap-x-6 flex-wrap py-4 border-t border-dashed border-ink-20 first:border-t-0">
      <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_48px] pt-1">{tier}</div>
      <div className="flex-[1_1_320px] min-w-[240px] flex flex-col gap-1">
        <div className="font-semibold text-body">{name}</div>
        <P muted>{role}</P>
        {detail && (
          <>
            <TextToggle open={open} closed="More" opened="Close" onClick={() => setOpen(!open)} className="self-start" />
            {open && <P muted>{detail}</P>}
          </>
        )}
      </div>
    </div>
  )
}

const STAGES: [string, string][] = [
  ['Classify', 'Music means two works: a composition and a sound recording, owned separately.'],
  ['Identify', 'MusicBrainz resolves the work and the earliest dated recording. An ambiguous title stops for disambiguation; researching the wrong entity is the worst failure this product can have.'],
  ['Decompose', 'The layers split before any research, so each is researched as its own work.'],
  ['Research', 'Both layers concurrently, cheapest tier first. A failed source degrades to the next tier; it never fails the run.'],
  ['Consistency', 'Facts that constrain each other are cross-checked. Each can be defensible alone while the pair is impossible; a conflict degrades both and opens a question naming the honest readings.'],
  ['Determine', 'The rules engine computes each term per territory and records which rule fired and why.'],
  ['Assemble', 'Verdicts roll up conservatively. The most restrictive required layer sets the answer, and unknown outranks clear.'],
]

export default function About({ onNewInquiry }: { onNewInquiry: () => void }) {
  const [stagesOpen, setStagesOpen] = useState(false)
  return (
    <>
      <Band label="Can I use this? — How the register works"
        context={
          <button type="button" onClick={onNewInquiry}
            className="bg-transparent border-none p-0 cursor-pointer text-meta font-semibold tracking-[0.08em] uppercase text-blue-on-ink underline decoration-[1.5px] underline-offset-[3px] hover:text-paper">
            New inquiry
          </button>
        }>
        <div className="-mt-3">
          <h1 className="m-0 font-black text-verdict leading-none tracking-[-0.01em] uppercase text-balance max-[560px]:text-stat">
            Methodology<span className="text-blue-on-ink">.</span>
          </h1>
          <p className="m-0 mt-5 text-headline font-medium leading-[1.3] max-w-[60ch] text-pretty text-paper">
            This is a register of rights research: every verdict is built from public records, carries its
            sources, and says out loud what could not be determined.
          </p>
        </div>
      </Band>

      <Doc>
        <section className="mt-14">
          <SectionHead title="One search is several works" sub="The idea the product turns on." />
          <div className="pt-6 flex flex-col gap-4">
            <P>
              A song is two separately-owned works: the <span className="font-semibold">composition</span>, owned
              by its writers and publishers, and each <span className="font-semibold">sound
              recording</span> of it, owned by whoever owns that master. Their copyrights run and expire under different rules, so
              they get different answers, and the verdict rolls up from the layers your use actually requires.
            </P>
            <div className="border-l-2 border-ink-20 pl-4 flex flex-col gap-1">
              <Eyebrow tracking={12} className="text-ink-70">Worked example</Eyebrow>
              <div className="font-mono font-medium text-body">West End Blues — Louis Armstrong (1928)</div>
              <P muted>
                The composition was published in 1928, so its US copyright expired on 1 January 2024. The song
                is public domain. The 1928 OKeh recording of it is protected until 2029 under the CLASSICS
                Act. For a documentary the answer is therefore <span className="font-semibold text-violet">license
                required</span>: the song is free, the master is not. Re-record it yourself and the master stops
                mattering. The same search, a different verdict.
              </P>
            </div>
            <P muted>
              The answer also varies by territory (the US, UK and EU set different terms) and by purpose (a
              distributed film and a re-recording need different layers), which is why both are controls on
              every record.
            </P>
            <P muted>
              Duration is a control for the opposite reason: it changes nothing. US copyright has no
              short-use exception, no seven seconds, no eight bars; Bridgeport put it as &ldquo;get a
              license or do not sample.&rdquo; Length scales what a license costs, never whether you need
              one, and fair use is a defense a court weighs after the fact, not a rule to rely on
              beforehand.
            </P>
            <P muted>
              The layer model is not specific to music: a book is a work, an edition, and sometimes a
              translation, each with its own term and owners. The register is scoped to music because the
              sources are strongest there and the composition/recording split is sharpest, but the
              architecture does not assume it.
            </P>
          </div>
        </section>

        <section className="mt-16">
          <SectionHead title="Where every fact comes from"
            sub="Two kinds of source. Records the register reads at runtime, and places it sends you because the answer lives there." />

          <div className="pt-6 flex flex-col gap-1">
            <Eyebrow tracking={12} className="text-ink-70">Sources we read</Eyebrow>
            <P muted>Queried on every inquiry, cheapest tier first. Every fact on a record cites one of these.</P>
          </div>
          <div className="mt-2 flex flex-col">
            <SourceRow tier="Tier 1" name="License URIs"
              role="Creative Commons license relations on the MusicBrainz recording, its work, or its releases, matched against a static table. No model."
              detail="A license on the recording or work settles the layer outright and research for it stops. A release-level license settles it only when every release on file carries one; a single licensed release is usually a compilation, and treating it as settled would license the master generally on one issue's say-so. Attribution and share-alike surface as conditions (cleared with conditions, not clear), and an NC license does not cover a commercial use." />
            <SourceRow tier="Tier 2" name="MusicBrainz"
              role="Recordings, works, writer credits, dated performances."
              detail="The recording is selected by earliest dated session, never by first-release date, which is frequently a reissue. Calls are cached persistently, throttled, and fail soft into Tier 3." />
            <SourceRow tier="Tier 2" name="Wikidata"
              role="Publication dates, writer death years, corroboration."
              detail="Writer lists are cross-checked here before life-plus-70 runs: the term follows the last surviving author, so an incomplete list blocks the determination rather than shading it." />
            <SourceRow tier="Tier 3" name="Parallel Search, read by Gemini"
              role="Web evidence for what no API holds: renewal records, original release dates, writer corroboration."
              detail="Search gathers candidate passages, and each query is entered in the ledger as it runs. The reader turns a passage into a cited fact or abstains; its confidence is capped by the class of source it cites, enforced in a validator rather than a prompt." />
            <SourceRow tier="Tier 3" name="Parallel Task, validated"
              role="Rights-holder research after the verdict: publishers, administrators, shares, one-stop status, each field cited."
              detail="A different job from Search: structured multi-field research rather than evidence gathering. It runs only for layers that need clearing, never on the verdict path, and its output is research rather than registry data; confidence is capped at medium, found shares that fall short of 100% conclude nothing about unclaimed shares, and the MLC record supersedes all of it if access arrives." />
          </div>

          <div className="mt-8 flex flex-col gap-1">
            <Eyebrow tracking={12} className="text-ink-70">Destinations we point to</Eyebrow>
            <P muted>
              Never queried. These hold answers we cannot pull, so records link to them with the search already
              filled in, and Clearance drafts the sync and master-use requests themselves, filled from the
              record with the production-specific parts left as marked blanks. If a fact ever cited one of
              these as read, that would be a bug; the distinction is the architecture.
            </P>
          </div>
          <div className="mt-2 flex flex-col">
            <SourceRow tier="link" name={<>The MLC <span className="font-normal text-ink-70">(API access requested, pending)</span></>}
              role="Publishers, administrators, ownership splits and unclaimed shares. A work with an unclaimed share cannot be fully cleared at any price, which is why this is the destination that matters most."
              detail="Until API access arrives, every record links to the MLC's public search, and the Clearance section shows the path to the parties rather than computed splits." />
            <SourceRow tier="link" name="US Copyright Office"
              role="Renewal records. Filings from 1978 on sit in an online catalog closed to web search; earlier ones are scanned catalog pages."
              detail="When renewal cannot be determined, the open question hands over the exact search terms and names the catalog that holds the record. You can bring the answer back: every renewal question carries an answer control." />
            <SourceRow tier="link" name="ASCAP and BMI repertories"
              role="Writer and publisher credits, for finding who to license from." />
          </div>

          <div className="mt-6">
            <P muted>
              The copyright arithmetic itself (the 95-year term, the renewal window, the CLASSICS Act schedule,
              life plus 70) is a hand-written, unit-tested rules engine. No model ever computes a term.
            </P>
          </div>
        </section>

        <section className="mt-16">
          <SectionHead title="The agent stack"
            sub="Built for the Agentic Cinema hackathon on Devpost, Parallel track." />
          <div className="pt-2 flex flex-col">
            {[
              ['Google ADK', 'Orchestrates the run as an agent graph: sequential stages, with the two research layers fanned out concurrently.'],
              ['Gemini 2.5 Flash', 'The reading step only, on Vertex AI. Evidence in; a cited fact or an abstention out. It never computes a term and cannot assert a fact it cannot cite.'],
              ['Parallel Search', 'On the primary request path, not a side channel. Renewal research, release research and writer corroboration run through it, and every search appears in the ledger.'],
              ['Parallel Task', 'After the verdict, for rights-holder research: structured output with a citation per field, filling the clearance profile while the answer is already on screen. The verdict never waits for it, and its output is capped at medium: research, not registry data, superseded by the MLC if access arrives.'],
              ['The consistency layer', 'Cross-checks between facts that constrain each other: a recording dated before its composition, a writer implausibly long-lived for the work, shares that sum past 100%. A conflict degrades confidence and opens a question rather than trusting one side.'],
              ['The rules engine', 'Deterministic Python computes every term. Each determination records which rule fired and why, so a verdict can be audited line by line.'],
            ].map(([name, desc]) => (
              <div key={name} className="flex gap-y-1 gap-x-6 flex-wrap py-4 border-t border-dashed border-ink-20 first:border-t-0 first:pt-6">
                <div className="font-semibold text-body flex-[0_0_150px]">{name}</div>
                <div className="flex-[1_1_320px] min-w-[240px]"><P muted>{desc}</P></div>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <P muted>
              Every completed record keeps its run log: what ran, which tier answered, what was cached, and
              whether enrichment ran or was skipped. A warm query resolves in under a second, and the log is
              how it stays legible after the fact.
            </P>
          </div>
          <TextToggle open={stagesOpen} closed="How a query runs, stage by stage" opened="Close"
            onClick={() => setStagesOpen(!stagesOpen)} className="mt-2" />
          {stagesOpen && (
            <div className="mt-2 flex flex-col">
              {STAGES.map(([name, desc], i) => (
                <div key={name} className="flex gap-y-1 gap-x-6 flex-wrap py-3 border-t border-dashed border-ink-20 first:border-t-0">
                  <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_48px] pt-[2px]">{i + 1}</div>
                  <div className="flex-[1_1_320px] min-w-[240px]">
                    <span className="font-semibold text-body">{name}. </span>
                    <span className="text-body leading-[1.55] text-ink-70">{desc}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="mt-16">
          <SectionHead title="What confidence means" sub="Shown as four ticks beside every fact, layer, and verdict." />
          <div className="flex flex-col pt-2">
            {[
              ['high', 'Multiple independent authoritative sources agree, or an official record states the fact outright.'],
              ['medium', 'A single authoritative source, or a rightsholder’s own notice ("© 1934, renewed 1961").'],
              ['low', 'Inference, or secondary sources only. A low-confidence fact may support "protected" but never "public domain": a wrong "protected" costs a license; a wrong "public domain" ends in a takedown.'],
              ['none', 'Asserted by no source. Nothing is concluded from it.'],
            ].map(([level, desc]) => (
              <div key={level} className="flex gap-y-1 gap-x-6 flex-wrap py-3 border-t border-dashed border-ink-20 first:border-t-0 first:pt-4">
                <div className="font-mono font-medium text-meta flex-[0_0_60px] pt-[2px]">{level}</div>
                <div className="flex-[1_1_300px] min-w-[220px]"><P muted>{desc}</P></div>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <P muted>
              A fact you supply when answering an open question is marked <span className="font-mono font-medium">asserted
              by you</span> on the record and capped at medium; high is reserved for records the register retrieved
              and read itself.
            </P>
          </div>
        </section>

        <section className="mt-16">
          <SectionHead title="Known limits" sub="Said here rather than discovered later." />
          <div className="pt-6 flex flex-col gap-4">
            <P>
              <span className="font-semibold">The 1931–1963 renewal window.</span> US works from those years lost
              protection after 28 years unless renewed, and most of the 20th-century songbook falls inside it.
              The register reads the renewal records it can reach, and otherwise hands over the exact search
              terms and the right catalog. It does not guess. Expect many mid-century compositions to come
              back <span className="font-semibold">not determined</span>.
            </P>
            <P>
              <span className="font-semibold">Licensing contacts are not a database.</span> Sync licenses are
              negotiated one-off and nobody publishes prices. The register identifies the parties and the shape
              of the negotiation, and gives cost bands as ranges, never a point estimate. The ranges are rough
              orders of magnitude from trade practice, not quotes.
            </P>
            <P>
              <span className="font-semibold">US-centric.</span> The US rules are the most complete; UK and EU
              determinations cover the composition (life plus 70) and the recording (70 years from publication).
              Other territories are not modelled.
            </P>
            <P>
              <span className="font-semibold">Ownership shares are researched, not authoritative.</span> The
              parties in the Clearance panel come from Parallel Task web research, capped at medium. The
              authoritative record is the MLC&rsquo;s, and it supersedes this research if access arrives; a
              shortfall in found shares says nothing about unclaimed shares.
            </P>
            <P>
              <span className="font-semibold">Coverage follows the sources.</span> A recording MusicBrainz has
              not dated, or a work Wikidata has not described, ends in an open question, not an answer. The
              register handles music; other kinds of work are not covered, and the schema reserves the shape
              for them.
            </P>
          </div>
        </section>

        <section className="mt-16 border-t-2 border-dashed border-ink-20 pt-5 flex flex-col gap-2">
          <Eyebrow className="text-ink-70">Not legal advice</Eyebrow>
          <P muted>
            This is research, not legal advice. Determinations are built from public records and can be wrong
            where those records are wrong or incomplete. Confidence levels describe the evidence, not a
            guarantee. For a distributed production, have a clearance professional confirm before you rely on
            it; the handoff links on every record point at the primary sources so they can.
          </P>
          <div className="mt-3">
            <a href="/" onClick={(e) => { e.preventDefault(); onNewInquiry() }} className="font-semibold text-body">
              Back to the register →
            </a>
          </div>
        </section>
      </Doc>
    </>
  )
}
