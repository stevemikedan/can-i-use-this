// The minimal terminal states: not found, boundary (recognized but not
// researched), and pipeline error. Same band grammar as every other screen —
// a 64/900 word, one honest explanation, a way forward. Never a stack trace.
import type { ReactNode } from 'react'
import type { QueryParams, RightsResponse } from '../types'
import { Band, Doc, Eyebrow } from '../components/ui'
import { intentContext } from '../lib/format'

function StatusPage({ word, glyph, children, params, actions }:
  { word: string; glyph: string; children: ReactNode; params?: QueryParams; actions: ReactNode }) {
  return (
    <>
      <Band label="Can I use this? — Research record"
        context={params && <Eyebrow tracking={12} className="text-paper-72">{params.jurisdiction} · {intentContext(params.intent)}</Eyebrow>}>
        <div className="-mt-3">
          <h1 className="m-0 font-black text-verdict leading-none tracking-[-0.01em] uppercase text-balance max-[560px]:text-stat">
            {word}<span className="text-blue-on-ink">{glyph}</span>
          </h1>
        </div>
      </Band>
      <Doc>
        <section className="mt-12 flex flex-col gap-6">
          {children}
          <div className="flex gap-y-2 gap-x-6 items-baseline flex-wrap border-t-2 border-dashed border-ink-20 pt-5">{actions}</div>
        </section>
      </Doc>
    </>
  )
}

export function NotFound({ resp, params, onRefine, onRetry }:
  { resp: RightsResponse; params: QueryParams; onRefine: () => void; onRetry: () => void }) {
  const q = resp.unresolved[0]
  return (
    <StatusPage word="Not found" glyph="." params={params}
      actions={<>
        <a href="#" onClick={(e) => { e.preventDefault(); onRefine() }} className="font-semibold text-body">Refine the inquiry — check the spelling, add the artist as credited →</a>
        <a href="#" onClick={(e) => { e.preventDefault(); onRetry() }} className="font-semibold text-body">Try again →</a>
      </>}>
      <div className="flex flex-col gap-2">
        <Eyebrow className="text-ink-70">What was searched</Eyebrow>
        <div className="text-body leading-[1.55] max-w-[66ch]">
          <span className="font-mono font-medium">{params.title}{params.artist ? ` — ${params.artist}` : ''}</span> against the MusicBrainz recording index.
        </div>
      </div>
      <div className="text-body leading-[1.55] text-ink-70 max-w-[66ch]">{resp.overall_headline}{q ? ` ${q.why_it_matters}` : ''}</div>
    </StatusPage>
  )
}

export function Boundary({ note, params, onNew }: { note: string; params: QueryParams; onNew: () => void }) {
  return (
    <StatusPage word="Out of scope" glyph="." params={params}
      actions={<a href="#" onClick={(e) => { e.preventDefault(); onNew() }} className="font-semibold text-body">Try a piece of music instead →</a>}>
      <div className="text-body leading-[1.55] max-w-[66ch]">{note}</div>
      <div className="text-body leading-[1.55] text-ink-70 max-w-[66ch]">
        This register researches music — compositions and sound recordings, separately. Other kinds of work are
        recognized and declined honestly rather than researched badly.
      </div>
    </StatusPage>
  )
}

export function ErrorScreen({ message, eventsSeen, params, onRetry, onNew }:
  { message: string; eventsSeen: number; params: QueryParams; onRetry: () => void; onNew: () => void }) {
  return (
    <StatusPage word="Interrupted" glyph="." params={params}
      actions={<>
        <a href="#" onClick={(e) => { e.preventDefault(); onRetry() }} className="font-semibold text-body">Run it again →</a>
        <a href="#" onClick={(e) => { e.preventDefault(); onNew() }} className="font-semibold text-body">New inquiry →</a>
      </>}>
      <div className="text-body leading-[1.55] max-w-[66ch]">
        The research run did not finish{eventsSeen > 0 ? ` — it stopped after ${eventsSeen} logged step${eventsSeen === 1 ? '' : 's'}` : ''}.
      </div>
      <div className="flex flex-col gap-2">
        <Eyebrow className="text-ink-70">What failed</Eyebrow>
        <div className="font-mono font-medium text-body text-ink-70 max-w-[66ch] break-words">{message}</div>
      </div>
      <div className="text-body leading-[1.55] text-ink-70 max-w-[66ch]">
        Nothing was concluded from the partial run — a half-researched verdict is worse than none. Running it
        again usually works; the caches keep what already succeeded.
      </div>
    </StatusPage>
  )
}
