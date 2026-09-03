// Entry — capture the query, set intent, convey what this is, in seconds.
// The examples are pre-warmed records: they hit the warm cache and return in
// about a second, and the first one exposes the layer split — the idea the
// product turns on.
import { useEffect, useRef, useState } from 'react'
import type { Intent, Jurisdiction, QueryParams } from '../types'
import { Band, Controls, Doc, Eyebrow, SectionHead } from '../components/ui'

const EXAMPLES: { title: string; artist: string; meta: string; stamp: string; color: string; note: string }[] = [
  {
    title: 'West End Blues', artist: 'Louis Armstrong', meta: 'recording · 1928 · OKeh 8597',
    stamp: 'License required', color: 'text-violet',
    note: 'The song is public domain; this 1928 recording of it is not.',
  },
  {
    title: 'Rhapsody in Blue', artist: 'Paul Whiteman', meta: 'composition + recording · 1924',
    stamp: 'Clear', color: 'text-green',
    note: 'Both layers out of copyright in the US, with the records to prove it.',
  },
  {
    title: 'Blue Moon', artist: 'Ella Fitzgerald', meta: 'composition · 1934 · renewal window',
    stamp: 'License required', color: 'text-violet',
    note: 'The answer turns on a year-28 renewal, researched and cited from the copyright records.',
  },
  {
    title: 'Summertime', artist: 'Billy Stewart', meta: 'recording · 1965 · Chess',
    stamp: 'License required', color: 'text-violet',
    note: 'The only date on file may be a reissue, so the original release is researched.',
  },
]

export default function Entry({ busy, error, initial, onSubmit, onAbout, onCues }:
  { busy: boolean; error: string | null; initial?: Partial<QueryParams>; onSubmit: (p: QueryParams) => void; onAbout: () => void; onCues: () => void }) {
  const [raw, setRaw] = useState(initial?.title ? `${initial.title}${initial.artist ? ` — ${initial.artist}` : ''}` : '')
  const [intent, setIntent] = useState<Intent>(initial?.intent ?? 'film_tv')
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>(initial?.jurisdiction ?? 'US')
  const [duration, setDuration] = useState<QueryParams['duration']>(initial?.duration)
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { inputRef.current?.focus() }, [])

  const submit = (title: string, artist?: string) => {
    if (!title.trim()) return
    onSubmit({ title: title.trim(), artist: artist?.trim() || undefined, intent, jurisdiction, duration })
  }
  const submitRaw = () => {
    for (const sep of [' — ', ' – ', ' - ', ' by ']) {
      const i = raw.indexOf(sep)
      if (i > 0) return submit(raw.slice(0, i), raw.slice(i + sep.length))
    }
    submit(raw)
  }

  return (
    <>
      <Band label="Research record — New inquiry" padding="pt-7 pb-12"
        context={<Eyebrow tracking={12} className="text-paper-72">Music — compositions & recordings</Eyebrow>}>
        <div className="flex flex-col gap-5 -mt-4">
          <h1 className="m-0 font-black text-verdict leading-none tracking-[-0.01em] uppercase max-[560px]:text-stat">
            Can I use this<span className="text-blue-on-ink">?</span>
          </h1>
          <p className="m-0 text-title font-medium leading-[1.4] max-w-[60ch] text-pretty text-paper">
            Researches whether a piece of music is yours to use, layer by layer, with the records to prove it.
          </p>
        </div>
      </Band>

      <Doc>
        <section className="mt-14">
          <Eyebrow className="mb-[14px]">Subject of inquiry</Eyebrow>
          <input
            ref={inputRef}
            autoFocus
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submitRaw() }}
            placeholder="Type a song title to open an inquiry"
            aria-label="Subject of inquiry"
            className="w-full box-border bg-ink-04 rounded-t-6 border-0 border-b-[3px] border-ink px-3 pt-3 pb-4 text-stat max-[560px]:text-headline font-bold text-ink outline-none focus:border-blue placeholder:font-medium placeholder:text-title"
          />
          <div className="mt-2 font-medium text-meta text-ink-70">
            Title and artist works best, as in <span className="font-mono">“Aliens Exist — blink-182”</span>; a title alone lists who recorded it.
          </div>
          <div className="mt-8">
            <Controls intent={intent} jurisdiction={jurisdiction} onIntent={setIntent} onJurisdiction={setJurisdiction} duration={duration} onDuration={setDuration} />
          </div>
          <div className="mt-7">
            <button type="button" className="btn-primary" disabled={busy} onClick={submitRaw}>
              {busy ? 'Opening the record…' : 'Begin research'}
            </button>
          </div>
          <p className="text-body leading-[1.55] text-ink-70 mt-6 mb-0 max-w-[80ch]">
            Research runs 10–90 seconds against the public record. You’ll watch it happen, source by source.
            {' '}<a href="/cues" onClick={(e) => { e.preventDefault(); onCues() }}>Clearing a full cue sheet? →</a>
          </p>
          {error && <p className="text-body leading-[1.55] mt-4 mb-0 max-w-[80ch]">Could not start the research: {error}</p>}
        </section>

        <section className="mt-16">
          <SectionHead title="Or open an existing record" sub="Inquiries already researched. Open one to see how a record reads." />
          <div className="flex flex-col">
            {EXAMPLES.map((ex) => (
              <a key={ex.title} href="#" onClick={(e) => { e.preventDefault(); submit(ex.title, ex.artist) }}
                className="row-link flex-col gap-2 py-6 px-1 border-t border-ink-20 first:border-t-0 no-underline">
                <div className="flex gap-y-2 gap-x-[14px] items-start flex-wrap">
                  <div className="flex-[1_1_240px] min-w-0 flex flex-col gap-1">
                    <div className="font-bold text-headline leading-[1.15] text-balance">{ex.title} — {ex.artist}</div>
                    <div className="font-mono font-medium text-meta text-ink-70">{ex.meta}</div>
                  </div>
                  <div className={`ml-auto font-bold text-body uppercase tracking-[0.04em] whitespace-nowrap ${ex.color}`}>{ex.stamp}</div>
                </div>
                <div className="flex gap-y-2 gap-x-4 items-baseline flex-wrap">
                  <div className="text-body leading-[1.5] text-ink-70 flex-[1_1_320px] max-w-[80ch]">{ex.note}</div>
                  <div className="font-semibold text-body text-blue whitespace-nowrap">Open the record →</div>
                </div>
              </a>
            ))}
          </div>
        </section>

        <section className="mt-16 border-t-2 border-dashed border-ink-20 pt-5 flex flex-col gap-2">
          <Eyebrow className="text-ink-70">Scope of the register</Eyebrow>
          <p className="m-0 text-body leading-[1.55] text-ink-70 max-w-[80ch]">
            Music only: compositions and sound recordings, researched separately. Books, film and images are
            recognized but not researched. Territories: US, UK, EU.
            {' '}<a href="/about" onClick={(e) => { e.preventDefault(); onAbout() }}>How the register works, and its limits →</a>
          </p>
        </section>
      </Doc>
    </>
  )
}
