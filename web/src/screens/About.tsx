// About — for users deciding whether to trust a verdict. The layer model in
// plain language, the research tiers, what confidence means, the known
// limits, and the full disclaimer. Same design system, no new tokens.
import type { ReactNode } from 'react'
import { Band, Doc, Eyebrow, SectionHead } from '../components/ui'

function P({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <p className={`m-0 text-body leading-[1.55] max-w-[66ch] ${muted ? 'text-ink-70' : ''}`}>{children}</p>
}

export default function About({ onNewInquiry }: { onNewInquiry: () => void }) {
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
          <p className="m-0 mt-5 text-headline font-medium leading-[1.3] max-w-[42ch] text-pretty text-paper">
            Every verdict is built from public records, carries its sources, and says out loud what could not
            be determined.
          </p>
        </div>
      </Band>

      <Doc>
        <section className="mt-14">
          <SectionHead title="One search is several works" sub="The idea the product turns on." />
          <div className="pt-6 flex flex-col gap-4">
            <P>
              A song is two separately-owned works: the <span className="font-semibold">composition</span> — the
              song itself, owned by writers and publishers — and each <span className="font-semibold">sound
              recording</span> of it, owned by whoever owns that master. They age under different rules, so they
              get different answers, and the verdict rolls up from the layers your use actually requires.
            </P>
            <div className="border-l-2 border-ink-20 pl-4 flex flex-col gap-1">
              <Eyebrow tracking={12} className="text-ink-70">Worked example</Eyebrow>
              <div className="font-mono font-medium text-body">West End Blues — Louis Armstrong (1928)</div>
              <P muted>
                The composition was published in 1928, so its US copyright expired on 1 January 2024 — the song
                is public domain. The famous OKeh recording of it is protected until 2029 under the CLASSICS
                Act. For a documentary the answer is therefore <span className="font-semibold text-violet">license
                required</span>: the song is free, the master is not. Re-record it yourself and the master stops
                mattering — the same search, a different verdict.
              </P>
            </div>
            <P muted>
              The answer also varies by territory (US, UK, EU age works differently) and by purpose (a
              distributed film and a re-recording need different layers), which is why both are controls on
              every record.
            </P>
          </div>
        </section>

        <section className="mt-16">
          <SectionHead title="Three research tiers, cheapest first" sub="Where the facts come from." />
          <div className="flex flex-col">
            {[
              ['Tier 1', 'Static parsing', 'RightsStatements.org and Creative Commons URIs — no call, no model.'],
              ['Tier 2', 'Direct APIs', 'MusicBrainz (recordings, works, dated sessions, writer credits) and Wikidata (publication dates, writer cross-checks, death years). Cached, throttled, and every call fails soft.'],
              ['Tier 3', 'Deep research', 'Parallel Search over the public record — renewal catalogs, discographies — with a reading step that turns evidence into a cited fact or leaves the question open. A fact it cannot cite does not exist.'],
            ].map(([tier, name, desc]) => (
              <div key={tier} className="flex gap-y-1 gap-x-6 flex-wrap py-4 border-t border-dashed border-ink-20 first:border-t-0 first:pt-6">
                <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_44px] pt-1">{tier}</div>
                <div className="flex-[1_1_300px] min-w-[220px]">
                  <div className="font-semibold text-body">{name}</div>
                  <P muted>{desc}</P>
                </div>
              </div>
            ))}
          </div>
          <P muted>
            The copyright arithmetic itself — the 95-year term, the renewal window, the CLASSICS Act schedule,
            life-plus-70 — is a hand-written, unit-tested rules engine. No model ever computes a term.
          </P>
        </section>

        <section className="mt-16">
          <SectionHead title="What confidence means" sub="Shown as four ticks beside every fact, layer, and verdict." />
          <div className="flex flex-col pt-2">
            {[
              ['high', 'Multiple independent authoritative sources agree — or an official record states the fact outright.'],
              ['medium', 'A single authoritative source, or a rightsholder’s own notice ("© 1934, renewed 1961").'],
              ['low', 'Inference, or secondary sources only. A low-confidence fact may support "protected" but never "public domain" — a wrong "protected" costs a license; a wrong "public domain" ends in a takedown.'],
              ['none', 'Asserted by no source. Nothing is concluded from it.'],
            ].map(([level, desc]) => (
              <div key={level} className="flex gap-y-1 gap-x-6 flex-wrap py-3 border-t border-dashed border-ink-20 first:border-t-0 first:pt-4">
                <div className="font-mono font-medium text-meta flex-[0_0_60px] pt-[2px]">{level}</div>
                <div className="flex-[1_1_300px] min-w-[220px]"><P muted>{desc}</P></div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-16">
          <SectionHead title="Known limits" sub="Said here rather than discovered later." />
          <div className="pt-6 flex flex-col gap-4">
            <P>
              <span className="font-semibold">The 1931–1963 renewal window.</span> US works from those years lost
              protection after 28 years unless renewed, and most of the 20th-century songbook falls inside it.
              Renewals filed before 1978 exist only as scanned catalog pages; renewals filed later live in the
              Copyright Office&rsquo;s online catalog, which web search cannot reach. The register reads the records it
              can, and otherwise hands over the exact search terms and the right catalog — it does not guess.
              Expect many mid-century compositions to come back <span className="font-semibold">not determined</span>.
            </P>
            <P>
              <span className="font-semibold">Licensing contacts are not a database.</span> Sync licenses are
              negotiated one-off and nobody publishes prices. The register identifies the parties and the shape
              of the negotiation, and gives cost bands as ranges, never a point estimate.
            </P>
            <P>
              <span className="font-semibold">US-centric.</span> The US rules are the most complete; UK and EU
              determinations cover the composition (life + 70) and the recording (70 years from publication).
              Other territories are not modelled.
            </P>
            <P>
              <span className="font-semibold">Publisher and share data is thinner than the rest.</span> Ownership
              splits, administrators and one-stop status live in the MLC&rsquo;s public database; API access is
              pending, so the composition layer currently falls back to web research and the public repertory
              links for holder information — which is why the clearance panel is leaner than the evidence trail.
            </P>
            <P>
              <span className="font-semibold">Coverage follows the sources.</span> A recording MusicBrainz has
              not dated, or a work Wikidata has not described, ends in an open question, not an answer. Music
              only: books, film, images, fonts and trademarks are recognized and declined honestly.
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
              Back to the register — begin an inquiry →
            </a>
          </div>
        </section>
      </Doc>
    </>
  )
}
