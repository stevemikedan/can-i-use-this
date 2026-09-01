// Disambiguation — research stops here deliberately: researching an ambiguous
// entity produces confidently wrong output. "Which one?" is a competent
// question, not an error. The composition shortcut sets Intent.RERECORD and
// re-runs: that changes REQUIRED_LAYERS server-side and genuinely changes the
// verdict — one answer for every recording of the song.
import { useState } from 'react'
import type { Candidate, QueryParams, RightsResponse } from '../types'
import { Band, Doc, Eyebrow, SectionHead, TextToggle } from '../components/ui'
import { intentContext } from '../lib/format'

const SHOW = 5

function parseCandidate(c: Candidate): { artist: string; year: string; note: string; count: string } {
  const artist = c.label.split(' — ')[0]
  const year = c.disambiguator.match(/earliest release on file (\d{4})/)?.[1] ?? '—'
  const count = c.disambiguator.match(/(\d+) recording entit/)?.[1] ?? ''
  return { artist, year, note: c.disambiguator, count: count ? `${count} rec.` : '' }
}

export default function Disambiguation({ resp, params, onPick, onComposition, onRefine }: {
  resp: RightsResponse
  params: QueryParams
  onPick: (artist: string) => void
  onComposition: (artist: string) => void
  onRefine: () => void
}) {
  const [all, setAll] = useState(false)
  const candidates = resp.entity.alternate_candidates
  const shown = all ? candidates : candidates.slice(0, SHOW)
  const nArtists = resp.overall_headline.match(/(\d+) artists/)?.[1]
  const title = resp.entity.canonical_title
  const first = candidates[0] ? parseCandidate(candidates[0]) : null

  return (
    <>
      <Band label="Can I use this? — Inquiry paused"
        context={<Eyebrow tracking={12} className="text-paper-72">{params.jurisdiction} · {intentContext(params.intent)}</Eyebrow>}>
        <div className="-mt-3">
          <h1 className="m-0 font-black text-verdict leading-none tracking-[-0.01em] uppercase text-balance max-[560px]:text-stat">
            Which one<span className="text-blue-on-ink">?</span>
          </h1>
          <p className="m-0 mt-5 text-headline font-medium leading-[1.3] max-w-[60ch] text-pretty text-paper">
            “{title}” has been recorded by {nArtists ?? 'many'} different artists, and each master is separately
            owned. Research stops here until you point at one.
          </p>
        </div>
        <div className="flex gap-y-6 gap-x-10 flex-wrap items-start">
          <div className="flex flex-col gap-[6px] flex-[1_1_300px] min-w-[240px]">
            <Eyebrow className="text-paper-72">What we understood</Eyebrow>
            <div className="text-body leading-[1.5] text-paper">
              A musical work titled <span className="font-mono font-medium">{title}</span>, with no artist, year, or label given.
            </div>
          </div>
          <div className="flex flex-col gap-[6px] flex-[1_1_300px] min-w-[240px]">
            <Eyebrow className="text-paper-72">What’s ambiguous</Eyebrow>
            <div className="text-body leading-[1.5] text-paper">One composition, many recordings. The composition has one answer; each recording its own.</div>
          </div>
        </div>
      </Band>

      <Doc>
        <section className="mt-12">
          <SectionHead
            title={`Candidates — showing ${shown.length} of ${candidates.length}`}
            sub="Earliest on record first. Pick one and research resumes with the full pass." />
          <div className="flex flex-col">
            {shown.map((c) => {
              const p = parseCandidate(c)
              return (
                <a key={c.label} href="#" onClick={(e) => { e.preventDefault(); onPick(p.artist) }}
                  className="row-link gap-y-2 gap-x-6 items-baseline flex-wrap py-[18px] px-1 border-t border-ink-20 first:border-t-0 no-underline">
                  <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_36px]">{p.year}</div>
                  <div className="flex-[1_1_240px] min-w-[180px] flex flex-col gap-[2px]">
                    <div className="font-bold text-title">{p.artist}</div>
                    <div className="text-body leading-[1.5] text-ink-70">{p.note}</div>
                  </div>
                  <div className="font-mono font-medium text-meta text-ink-70 whitespace-nowrap">{p.count}</div>
                  <div className="font-semibold text-body text-blue whitespace-nowrap">Research this →</div>
                </a>
              )
            })}
          </div>
          {!all && candidates.length > SHOW && (
            <TextToggle open={false} closed={`Show the other ${candidates.length - SHOW} (mostly later covers and reissues)`}
              opened="" onClick={() => setAll(true)} className="py-[14px] px-1" />
          )}
        </section>

        {first && (
          <section className="mt-12 border border-dashed border-ink-20 rounded-6 py-5 px-[22px] flex gap-y-3 gap-x-6 items-baseline flex-wrap">
            <div className="flex-[1_1_320px] min-w-[240px] flex flex-col gap-1">
              <Eyebrow className="text-ink-70">Not using a specific recording?</Eyebrow>
              <div className="text-body leading-[1.55] max-w-[58ch]">
                If you’re performing or re-recording it yourself, only the composition matters. One answer for
                all {candidates.length}{nArtists && Number(nArtists) > candidates.length ? '+' : ''} of them.
              </div>
            </div>
            <a href="#" onClick={(e) => { e.preventDefault(); onComposition(first.artist) }} className="font-semibold text-body whitespace-nowrap">
              Research the composition only →
            </a>
          </section>
        )}

        <section className="mt-12 border-t-2 border-dashed border-ink-20 pt-5 flex gap-y-2 gap-x-6 items-baseline flex-wrap">
          <div className="text-body text-ink-70">None of these is it?</div>
          <a href="#" onClick={(e) => { e.preventDefault(); onRefine() }} className="font-semibold text-body">
            Add an artist, year, or label →
          </a>
        </section>
      </Doc>
    </>
  )
}
