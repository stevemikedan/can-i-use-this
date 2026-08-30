// Progress — the accession log. Renders the pipeline's own PipelineEvent
// messages as ledger lines; nothing here invents progress copy. The empty
// ruling problem at second 5 is handled the way the design file does it: every
// section is ruled in from the start as QUEUED, so the page reads as a plan
// being filled, not a void. Failures stay on the record, struck through.
import { useEffect, useMemo, useState } from 'react'
import type { PipelineEvent, QueryParams } from '../types'
import { Band, Doc, Eyebrow, SectionHead } from '../components/ui'
import { intentContext } from '../lib/format'

const SECTIONS = [
  { key: 'identify', title: 'I. Identify the work', stages: ['classify', 'identify'], last: 'identify', caret: 'Consulting the registries' },
  { key: 'decompose', title: 'II. Rights layers', stages: ['decompose'], last: 'decompose', caret: 'Splitting into separately-owned works' },
  { key: 'research', title: 'III. Research — both layers', stages: ['research'], last: 'research', caret: 'Researching, cheapest tier first' },
  { key: 'rules', title: 'IV. Determination', stages: ['rules', 'compare', 'assemble'], last: 'assemble', caret: 'Applying the rules' },
] as const

function fmt(s: number): string {
  return `${Math.floor(s / 60)}:${String(Math.floor(s) % 60).padStart(2, '0')}`
}

export default function Progress({ params, events }: { params: QueryParams; events: PipelineEvent[] }) {
  const [t, setT] = useState(0)
  useEffect(() => {
    const t0 = Date.now()
    const timer = setInterval(() => setT((Date.now() - t0) / 1000), 1000)
    return () => clearInterval(timer)
  }, [])

  const sections = useMemo(() => {
    let prevSources = 0
    const byStage = new Map<string, PipelineEvent[]>()
    const marks: { ev: PipelineEvent; mark: string; kind: 'ok' | 'fail' | 'stamp' }[] = []
    for (const ev of events) {
      const delta = ev.sources_consulted - prevSources
      prevSources = ev.sources_consulted
      let mark = delta > 0 ? `${delta} ${delta === 1 ? 'SOURCE' : 'SOURCES'}` : '—'
      let kind: 'ok' | 'fail' | 'stamp' = 'ok'
      if (ev.degraded || ev.status === 'failed') { mark = 'FAILED'; kind = 'fail' }
      else if (ev.stage === 'rules' && ev.status === 'complete') { mark = 'STAMPED'; kind = 'stamp' }
      else if (ev.stage === 'assemble' && ev.status === 'complete') { mark = 'DONE'; kind = 'stamp' }
      else if (ev.status === 'complete' && ev.stage === 'identify') { mark = 'RESOLVED'; kind = 'stamp' }
      else if (ev.message.includes('resolved from evidence')) { mark = 'READ'; kind = 'stamp' }
      const entry = { ev, mark, kind }
      marks.push(entry)
      const list = byStage.get(ev.stage) ?? []
      list.push(ev)
      byStage.set(ev.stage, list)
    }
    const lineFor = (ev: PipelineEvent) => marks.find((m) => m.ev === ev)!
    let caretPlaced = false
    return SECTIONS.map((sd) => {
      const lines = sd.stages.flatMap((st) => byStage.get(st) ?? []).map(lineFor)
      const started = lines.length > 0
      const done = (byStage.get(sd.last) ?? []).some((e) => e.status === 'complete' || e.status === 'skipped' || e.status === 'failed')
      const showCaret = !caretPlaced && !done
      if (showCaret) caretPlaced = true
      return { ...sd, lines, started, done, showCaret }
    })
  }, [events])

  const last = events[events.length - 1]
  const stageLine = last ? last.message : 'Opening the record.'
  const consulted = last?.sources_consulted ?? 0
  const failures = events.filter((e) => e.degraded || e.status === 'failed').length
  const decomposed = events.some((e) => e.stage === 'decompose' && e.status === 'complete')
  const pace = t < 60 ? 'typically 30–90 seconds' : t < 95 ? 'deep research — up to 90 seconds is normal' : 'running long — archive sources can be slow'

  return (
    <>
      <Band label="Can I use this? — Research in progress" padding="pt-7 pb-10"
        context={<Eyebrow tracking={12} className="text-paper-72">{params.jurisdiction} · {intentContext(params.intent)}</Eyebrow>}>
        <div className="flex gap-y-6 gap-x-12 items-end flex-wrap">
          <div className="flex-[1_1_380px] min-w-[240px] flex flex-col gap-[10px]">
            <Eyebrow className="text-blue-on-ink">Query</Eyebrow>
            <div className="font-bold text-headline leading-[1.2] text-balance">
              {params.title}{params.artist ? ` — ${params.artist}` : ''}
            </div>
            <div className="text-body font-medium text-paper" aria-live="polite">{stageLine}</div>
          </div>
          <div className="flex flex-col gap-[6px] items-end">
            <Eyebrow className="text-paper-72">Elapsed</Eyebrow>
            <div className="font-mono font-medium text-stat leading-none">{fmt(t)}</div>
            <div className="text-meta font-medium text-paper-72">{pace}</div>
          </div>
        </div>
        <div className="flex gap-3 flex-wrap">
          {['Composition', 'Sound recording'].map((name) => (
            <div key={name} className={`flex flex-col gap-1 py-[10px] px-4 rounded-6 min-w-[150px] border ${decomposed ? 'border-solid' : 'border-dashed'} border-paper-25`}>
              <div className="text-meta font-semibold tracking-[0.1em] uppercase">{name}</div>
              <div className="font-bold text-body uppercase tracking-[0.04em] text-paper-72">{decomposed ? 'Researching…' : 'Decomposing…'}</div>
            </div>
          ))}
        </div>
      </Band>

      <Doc>
        <section className="mt-10">
          <SectionHead title="Accession log"
            sub="Every source consulted is entered here as it returns. Failures stay on the record, struck through — corrected, never erased." />
          {sections.map((sec) => (
            <div key={sec.key} className="pt-[22px] pb-[6px] border-t border-ink-20 first:border-t-0">
              <div className="flex gap-y-2 gap-x-[14px] items-baseline flex-wrap mb-[6px]">
                <Eyebrow className={sec.started ? 'text-ink' : 'text-ink-70'}>{sec.title}</Eyebrow>
                <div className={`text-meta font-semibold tracking-[0.08em] uppercase ${sec.done ? 'text-green' : sec.started ? 'text-blue' : 'text-ink-70'}`}>
                  {sec.done ? 'Complete' : sec.started ? 'In progress' : 'Queued'}
                </div>
              </div>
              <div className="flex flex-col">
                {sec.lines.map(({ ev, mark, kind }, i) => (
                  <div key={i} className="flex gap-y-[6px] gap-x-[14px] items-baseline flex-wrap py-[9px] border-t border-dashed border-ink-20">
                    <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_44px]">{fmt(ev.elapsed_ms / 1000)}</div>
                    <div className="flex-[1_1_300px] min-w-[200px]">
                      <div className={`text-body font-semibold ${kind === 'fail' ? 'line-through text-ink-70' : kind === 'stamp' ? 'text-green' : ''}`}>{ev.message}</div>
                      {(ev.detail || ev.error_message) && (
                        <div className={`text-body leading-[1.5] mt-[2px] ${kind === 'fail' ? 'text-red' : 'text-ink-70'}`}>
                          {ev.detail}{ev.error_message ? ` ${ev.error_message}` : ''}
                        </div>
                      )}
                    </div>
                    <div className={`font-mono font-medium text-meta whitespace-nowrap ${kind === 'fail' ? 'text-red' : kind === 'stamp' ? 'text-green' : 'text-ink-70'}`}>{mark}</div>
                  </div>
                ))}
                {sec.showCaret && (
                  <div className="flex gap-[14px] items-baseline py-[9px] border-t border-dashed border-ink-20">
                    <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_44px]">{fmt(t)}</div>
                    <div className="text-body font-semibold text-blue">{sec.caret}<span className="caret">▊</span></div>
                  </div>
                )}
              </div>
            </div>
          ))}

          <div className="border-t-2 border-ink mt-2 pt-[14px] flex gap-y-[10px] gap-x-8 flex-wrap items-baseline">
            <Eyebrow className="text-ink-70">Running tally</Eyebrow>
            <div className="text-meta font-semibold">sources consulted <span className="font-mono font-medium">{consulted}</span></div>
            <div className="text-meta font-semibold">failures on record <span className="font-mono font-medium">{failures}</span></div>
          </div>
        </section>
      </Doc>
    </>
  )
}
