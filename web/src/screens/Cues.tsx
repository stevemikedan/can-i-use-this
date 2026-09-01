// Cue sheet mode — a clearance worksheet over the existing query path. A film
// has 20–40 cues; the list is the actual job. Each line runs through the same
// pipeline serially (MusicBrainz rate limit; the cache makes repeats instant),
// rows resolve as they land, and the summary line answers the supervisor's
// real question: how many need clearing. Same components, no new language.
import { useEffect, useRef, useState } from 'react'
import type { QueryParams, RightsResponse } from '../types'
import { Band, Doc, Eyebrow, SectionHead, Stamp } from '../components/ui'
import { BLOCK_REASON, confidenceLabel, expiryLine, splitQuery } from '../lib/format'
import { VERDICT_SEVERITY, blockingLayers, layerTitle, toCsv, downloadText } from '../lib/export'
import { runQuery } from '../lib/api'

export interface CueRow {
  line: string
  title: string
  artist?: string
  status: 'queued' | 'running' | 'done' | 'failed'
  resp?: RightsResponse
  error?: string
}

const EXAMPLE = [
  'West End Blues — Louis Armstrong',
  'Rhapsody in Blue — Paul Whiteman',
  'Blue Moon — Ella Fitzgerald',
  'Summertime — Billy Stewart',
  'St. Louis Blues — Bessie Smith',
  'Take Five — The Dave Brubeck Quartet',
  'Aliens Exist — blink-182',
  'Mack the Knife — Bobby Darin',
].join('\n')

function severity(r: CueRow): number {
  if (r.status === 'failed') return 6
  if (r.status !== 'done' || !r.resp) return -1
  if (r.resp.entity.layers.length === 0) return 5          // not found / interrupted
  return VERDICT_SEVERITY[r.resp.overall_verdict]
}

export default function Cues({ params, rows, setRows, onOpen, onNewInquiry }: {
  params: QueryParams
  rows: CueRow[]
  setRows: (rows: CueRow[] | ((r: CueRow[]) => CueRow[])) => void
  onOpen: (resp: RightsResponse, p: QueryParams) => void
  onNewInquiry: () => void
}) {
  const [text, setText] = useState(rows.length ? rows.map((r) => r.line).join('\n') : '')
  const [running, setRunning] = useState(false)
  const cancelled = useRef(false)
  useEffect(() => () => { cancelled.current = true }, [])

  const run = async () => {
    const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
    if (!lines.length || running) return
    cancelled.current = false
    const initial: CueRow[] = lines.map((line) => {
      const { title, artist } = splitQuery(line)
      return { line, title, artist: artist ?? undefined, status: 'queued' }
    })
    setRows(initial)
    setRunning(true)
    for (let i = 0; i < initial.length; i++) {
      if (cancelled.current) break
      setRows((rs) => rs.map((r, j) => (j === i ? { ...r, status: 'running' } : r)))
      try {
        const resp = await runQuery({ ...params, title: initial[i].title, artist: initial[i].artist })
        setRows((rs) => rs.map((r, j) => (j === i ? { ...r, status: 'done', resp } : r)))
      } catch (e) {
        setRows((rs) => rs.map((r, j) => (j === i ? { ...r, status: 'failed', error: e instanceof Error ? e.message : String(e) } : r)))
      }
    }
    setRunning(false)
  }

  const done = rows.filter((r) => r.status === 'done' && r.resp)
  const finished = rows.length > 0 && !running && rows.every((r) => r.status === 'done' || r.status === 'failed')
  const display = finished ? [...rows].sort((a, b) => severity(b) - severity(a)) : rows

  const counts = {
    clear: done.filter((r) => ['clear', 'clear_with_conditions'].includes(r.resp!.overall_verdict) && r.resp!.entity.layers.length > 0).length,
    license: done.filter((r) => ['license_required', 'restricted'].includes(r.resp!.overall_verdict)).length,
    undet: done.filter((r) => r.resp!.overall_verdict === 'undetermined' && r.resp!.entity.layers.length > 0).length,
    unresolved: rows.filter((r) => r.status === 'failed' || (r.status === 'done' && r.resp!.entity.layers.length === 0)).length,
  }

  const exportCsv = () => {
    const exportRows = done
      .filter((r) => r.resp!.entity.layers.length > 0)
      .map((r) => ({ resp: r.resp!, params: { ...params, title: r.title, artist: r.artist } }))
    if (exportRows.length) downloadText('cue-sheet-clearance.csv', toCsv(exportRows), 'text/csv')
  }

  return (
    <>
      <Band label="Can I use this? — Cue sheet"
        context={
          <button type="button" onClick={onNewInquiry}
            className="bg-transparent border-none p-0 cursor-pointer text-meta font-semibold tracking-[0.08em] uppercase text-blue-on-ink underline decoration-[1.5px] underline-offset-[3px] hover:text-paper">
            Single inquiry
          </button>
        }>
        <div className="-mt-3">
          <h1 className="m-0 font-black text-verdict leading-none tracking-[-0.01em] uppercase text-balance max-[560px]:text-stat">
            Cue sheet<span className="text-blue-on-ink">.</span>
          </h1>
          <p className="m-0 mt-5 text-headline font-medium leading-[1.3] max-w-[60ch] text-pretty text-paper">
            A film is a list of cues. Paste it; every line gets the full layered check.
          </p>
        </div>
        <p className="m-0 text-body leading-[1.5] max-w-[62ch] text-paper-72">
          A clearance worksheet, not a filed cue sheet; a filed one needs timings and use types this research
          doesn’t have. Music only. {params.jurisdiction} · {params.intent === 'film_tv' ? 'documentary' : params.intent}.
        </p>
      </Band>

      <Doc>
        <section className="mt-14 no-print">
          <Eyebrow className="mb-[14px]">One cue per line, as title — artist</Eyebrow>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={Math.min(12, Math.max(5, text.split('\n').length + 1))}
            placeholder={'Paste a cue list, one per line\nWest End Blues — Louis Armstrong\nBlue Moon — Ella Fitzgerald'}
            aria-label="Cue list, one cue per line"
            className="w-full box-border bg-ink-04 rounded-t-6 border-0 border-b-[3px] border-ink px-3 py-3 text-body font-mono font-medium leading-[1.6] text-ink outline-none focus:border-blue resize-y"
          />
          <div className="mt-4 flex gap-x-5 gap-y-2 items-baseline flex-wrap">
            <button type="button" className="btn-primary" disabled={running} onClick={run}>
              {running ? 'Working the list…' : 'Research the list'}
            </button>
            <button type="button" className="text-toggle" onClick={() => setText(EXAMPLE)}>
              Load an example list (8 cues, already researched)
            </button>
          </div>
        </section>

        {rows.length > 0 && (
          <section className="mt-12">
            <SectionHead
              title={`Clearance — ${rows.length} cue${rows.length === 1 ? '' : 's'}`}
              sub={
                `${counts.license} need${counts.license === 1 ? 's' : ''} clearing · ${counts.clear} clear · ` +
                `${counts.undet} not determined · ${counts.unresolved} not resolved` +
                (finished ? '. Most restrictive first.' : running ? '. Resolving…' : '.')
              }
              right={done.length > 0 ? (
                <button type="button" className="text-toggle whitespace-nowrap no-print" onClick={exportCsv}>Export CSV</button>
              ) : undefined}
            />
            <div className="flex flex-col" aria-live="polite">
              {display.map((r) => {
                const resp = r.resp
                const failed = r.status === 'failed' || (resp && resp.entity.layers.length === 0)
                const blocking = resp && !failed ? blockingLayers(resp) : []
                return (
                  <div key={r.line} className="flex gap-y-1 gap-x-5 items-baseline flex-wrap py-[14px] px-1 border-t border-ink-20 first:border-t-0">
                    <div className="flex-[1_1_260px] min-w-[200px]">
                      <div className="font-semibold text-body">{r.title}{r.artist ? <span className="font-medium text-ink-70"> — {r.artist}</span> : null}</div>
                    </div>
                    {r.status === 'queued' && <div className="text-meta font-semibold tracking-[0.08em] uppercase text-ink-70">Queued</div>}
                    {r.status === 'running' && <div className="text-meta font-semibold tracking-[0.08em] uppercase text-blue">Researching<span className="caret">▊</span></div>}
                    {failed && (r.status === 'done' || r.status === 'failed') && (
                      <div className="flex gap-x-4 gap-y-1 items-baseline flex-wrap">
                        <div className="font-bold text-body uppercase tracking-[0.04em] text-ink">Not resolved</div>
                        <div className="text-meta font-medium text-ink-70 max-w-[40ch]">{resp ? resp.overall_headline.slice(0, 80) : r.error}</div>
                        {resp && <button type="button" className="text-toggle !text-meta" onClick={() => onOpen(resp, { ...params, title: r.title, artist: r.artist })}>Open →</button>}
                      </div>
                    )}
                    {resp && !failed && (
                      <>
                        <div className="flex-[0_0_auto]"><Stamp verdict={resp.overall_verdict} size={16} /></div>
                        <div className="text-meta font-medium text-ink-70 flex-[0_1_auto]">
                          {blocking.length
                            ? blocking.map((b) => {
                                const why = BLOCK_REASON[b.determination.rule_id]
                                return layerTitle(b).toLowerCase() + (why ? ` · ${why}` : '')
                              }).join(' + ')
                            : 'nothing blocking'}
                        </div>
                        <div className="font-mono font-medium text-meta text-ink-70 whitespace-nowrap">
                          {/* the LATER constraint: the row's expiry is when the last block lifts */}
                          {blocking.length
                            ? expiryLine([...blocking].sort((a, b) => (b.determination.expiry_year ?? 9999) - (a.determination.expiry_year ?? 9999))[0].determination)
                            : expiryLine(resp.layer_verdicts.filter((l) => l.is_required)[0]?.determination ?? resp.layer_verdicts[0].determination)}
                        </div>
                        {resp.overall_verdict !== 'undetermined' && (
                          <div className="text-meta font-medium text-ink-70 whitespace-nowrap">{confidenceLabel(resp.overall_confidence)}</div>
                        )}
                        <button type="button" className="text-toggle whitespace-nowrap" onClick={() => onOpen(resp, { ...params, title: r.title, artist: r.artist })}>
                          Open record →
                        </button>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
            <p className="mt-6 mb-0 text-meta font-medium leading-[1.7] text-ink-70 max-w-[78ch]">
              Each row links to its full cited record.
            </p>
          </section>
        )}
      </Doc>
    </>
  )
}
