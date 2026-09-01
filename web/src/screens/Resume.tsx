// Resume — a shared permalink whose record is no longer fresh. Opening a
// link must show a record, not silently spend a 10–45 second research run:
// the reader sees what the link is, when it was researched, and chooses.
// (Fresh records skip this screen entirely and auto-run, since a warm
// re-run is effectively instant.)
import type { QueryParams } from '../types'
import { Band, Doc, Eyebrow } from '../components/ui'
import { intentContext, shortDate } from '../lib/format'

export default function Resume({ params, researchedAt, onResearch, onNewInquiry }: {
  params: QueryParams
  researchedAt: string | null
  onResearch: () => void
  onNewInquiry: () => void
}) {
  return (
    <>
      <Band label="Can I use this? — Saved record" padding="pt-7 pb-10"
        context={<Eyebrow tracking={12} className="text-paper-72">{params.jurisdiction} · {intentContext(params.intent)}</Eyebrow>}>
        <div className="flex flex-col gap-[10px]">
          <Eyebrow className="text-blue-on-ink">Query</Eyebrow>
          <div className="font-bold text-headline leading-[1.2] text-balance">
            {params.title}{params.artist ? ` — ${params.artist}` : ''}
          </div>
          <div className="font-mono font-medium text-meta text-paper-72">
            {researchedAt ? `researched ${shortDate(researchedAt)}` : 'not yet researched from this register'}
          </div>
        </div>
      </Band>

      <Doc>
        <section className="mt-12 flex flex-col gap-5 max-w-[68ch]">
          <p className="m-0 text-body leading-[1.55]">
            {researchedAt
              ? 'The research cache has moved on since this record was made, so reopening it means running the inquiry again.'
              : 'This link points at an inquiry that has not been researched here recently.'}
            {' '}A run takes seconds when sources are warm and up to a couple of minutes cold.
          </p>
          <div className="flex gap-x-6 gap-y-3 items-baseline flex-wrap">
            <button type="button" className="btn-primary" onClick={onResearch}>Research this</button>
            <a href="/" onClick={(e) => { e.preventDefault(); onNewInquiry() }} className="font-semibold text-body">
              Start a new inquiry →
            </a>
          </div>
        </section>
      </Doc>
    </>
  )
}
