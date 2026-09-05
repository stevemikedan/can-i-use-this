// Result — docs/design-system.md §5 "Result". Every value rendered here comes
// from the RightsResponse; the screen adds no judgement of its own.
import { useCallback, useEffect, useState } from 'react'
import type { ClearanceEnrichment, HandoffLink, Intent, LayerVerdict, QueryParams, ResearchedFact, RightsHolder, RightsLayer, RightsResponse, Source, UnresolvedQuestion, UserAnswerParam } from '../types'
import { fetchClearance } from '../lib/api'
import { Band, Controls, Doc, Eyebrow, SectionHead, Stamp, Tag, TextToggle, Ticks } from '../components/ui'
import { EFFORT_LABEL, FACT_LABEL, METHOD_LABEL, VERDICT_WORD, confidenceLabel, expiryLine, factValue, pct, shortDate, sourceHref, splitQuery } from '../lib/format'
import { VERDICT_SEVERITY, csvRow, CSV_HEADER, downloadText, licenseRequest, safeFilename, toMarkdown, toPrintHtml } from '../lib/export'

const ORDER = VERDICT_SEVERITY

export interface ResultProps {
  resp: RightsResponse
  params: QueryParams
  busy: boolean
  onIntent: (i: Intent) => void
  onDuration: (d: QueryParams['duration']) => void
  onJurisdiction: (j: QueryParams['jurisdiction']) => void
  onNewInquiry: () => void
  onAnswer: (questionId: string, payload: { answer?: boolean; value?: number; attestation: string }) => void
  onBack?: () => void
}

export default function Result({ resp, params, busy, onIntent, onJurisdiction, onDuration, onNewInquiry, onAnswer, onBack }: ResultProps) {
  const { intent, jurisdiction } = params
  const [openState, setOpenState] = useState<Record<string, boolean>>({})
  const [printing, setPrinting] = useState(false)
  const open: Record<string, boolean> = printing
    ? new Proxy(openState, { get: () => true }) as Record<string, boolean>
    : openState
  const toggle = (k: string) => setOpenState((s) => ({ ...s, [k]: !s[k] }))
  const [copied, setCopied] = useState(false)
  const [reqCopied, setReqCopied] = useState<string | null>(null)
  const [stampKey, setStampKey] = useState(0)
  // Rights-holder enrichment: fetched after the verdict renders, never
  // before. On fixtures or endpoint failure it stays null and the static
  // MLC note stands.
  const [enrich, setEnrich] = useState<ClearanceEnrichment | null>(null)
  const [enrichBusy, setEnrichBusy] = useState(false)
  useEffect(() => { setStampKey((k) => k + 1) }, [resp])
  useEffect(() => {
    setEnrich(null)
    const needs = resp.layer_verdicts.some((l) => l.is_required && (l.verdict === 'license_required' || l.verdict === 'restricted'))
    if (!needs || !params.title) return
    const ac = new AbortController()
    setEnrichBusy(true)
    fetchClearance(params, ac.signal)
      .then((e) => { if (!ac.signal.aborted) setEnrich(e) })
      .catch(() => { /* fixtures or endpoint down: the static note stands */ })
      .finally(() => { if (!ac.signal.aborted) setEnrichBusy(false) })
    return () => ac.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resp])

  // Cmd/Ctrl-P and the Print button both render every section expanded.
  useEffect(() => {
    const before = () => setPrinting(true)
    const after = () => setPrinting(false)
    window.addEventListener('beforeprint', before)
    window.addEventListener('afterprint', after)
    return () => { window.removeEventListener('beforeprint', before); window.removeEventListener('afterprint', after) }
  }, [])
  const printPdf = useCallback(() => {
    // The PDF comes from the export template, not the screen: a research
    // memo in a fresh document, black on white, paged breaks. The screen's
    // print stylesheet still serves a plain Ctrl+P.
    const win = window.open('', '_blank')
    if (!win) { setPrinting(true); setTimeout(() => window.print(), 60); return }
    win.document.write(toPrintHtml(resp, params))
    win.document.close()
    win.focus()
    setTimeout(() => win.print(), 200)
  }, [resp, params])
  const exportCsv = useCallback(() => {
    downloadText(`${safeFilename(params.title)}.csv`, CSV_HEADER.join(',') + '\r\n' + csvRow(resp, params) + '\r\n', 'text/csv')
  }, [resp, params])
  const copyMarkdown = useCallback(() => {
    navigator.clipboard?.writeText(toMarkdown(resp, params))
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }, [resp, params])

  const { artist } = splitQuery(resp.query.raw_input)
  const year = resp.entity.year?.value
  const required = resp.layer_verdicts.filter((l) => l.is_required)
  const nonRequired = resp.layer_verdicts.filter((l) => !l.is_required)
  const worst = Math.max(...required.map((l) => ORDER[l.verdict]), 0)
  const blockingIds = worst > 0 ? required.filter((l) => ORDER[l.verdict] === worst).map((l) => l.layer_id) : []
  const layerOf = (id: string) => resp.entity.layers.find((l) => l.layer_id === id)
  const toClear = required.filter((l) => l.verdict === 'license_required')
  const actLinks = resp.handoff_links.filter((l) => l.purpose === 'license')
  const derivative = resp.unresolved.some((u) => u.question_id === 'composition:derivative')
  // The enrichment stage reads as a deliberate skip, a run, or a failure -
  // never as silence.
  const needsEnrich = required.some((l) => l.verdict === 'license_required' || l.verdict === 'restricted')
  const enrichmentLine = !needsEnrich
    ? 'Rights-holder enrichment skipped: nothing to clear for this verdict.'
    : enrichBusy ? 'Rights-holder enrichment running (Parallel Task)\u2026'
      : enrich ? 'Rights-holder enrichment complete (Parallel Task); the parties are under Clearance.'
        : 'Rights-holder enrichment did not return; Clearance shows the manual route.'

  return (
    <>
      <Band
        label="Can I use this? — Research record"
        context={
          <div className="flex gap-5 items-baseline flex-wrap">
            <div className="font-mono font-medium text-meta text-paper-72">
              researched {shortDate(resp.generated_at).toLowerCase()} · {resp.served_from_cache ? 'cached' : 'fresh'}
            </div>
            {onBack && <button type="button" onClick={onBack} className="bg-transparent border-none p-0 cursor-pointer text-meta font-semibold tracking-[0.08em] uppercase text-blue-on-ink underline decoration-[1.5px] underline-offset-[3px] hover:text-paper">Back to the cue sheet</button>}
            <button type="button" onClick={onNewInquiry} className="bg-transparent border-none p-0 cursor-pointer text-meta font-semibold tracking-[0.08em] uppercase text-blue-on-ink underline decoration-[1.5px] underline-offset-[3px] hover:text-paper">New inquiry</button>
          </div>
        }
      >
        <div className="flex flex-col gap-9 -mt-[22px]">
          <div className="flex gap-3 items-baseline flex-wrap">
            <Eyebrow className="text-blue-on-ink">Query</Eyebrow>
            <div className="text-body font-medium text-paper">
              {resp.entity.canonical_title}{artist ? ` — ${artist}` : ''}{year ? ` (${year})` : ''}
            </div>
          </div>
          <div>
            <h1 key={stampKey} className="restamp m-0 font-black text-verdict leading-none tracking-[-0.01em] uppercase text-balance max-[560px]:text-stat">
              {VERDICT_WORD[resp.overall_verdict]}<span className="text-blue-on-ink">.</span>
            </h1>
            <p className="m-0 mt-5 text-headline font-medium leading-[1.3] max-w-[60ch] text-pretty text-paper">{resp.overall_headline}</p>
          </div>
          <div className="flex flex-col gap-[22px]">
            <Controls intent={intent} jurisdiction={jurisdiction} onIntent={onIntent} onJurisdiction={onJurisdiction} duration={params.duration ?? null} onDuration={onDuration} onInk busy={busy} />
            <div className="flex flex-col gap-[10px]">
              <Eyebrow className="text-paper-72">{resp.overall_verdict === 'undetermined' ? 'Status' : 'Confidence'}</Eyebrow>
              <div className="min-h-10 flex items-center">
                {resp.overall_verdict === 'undetermined'
                  ? <div className="text-body font-medium text-paper max-w-[46ch]">No answer yet. The term can&rsquo;t be computed until the open question below is settled.</div>
                  : <Ticks level={resp.overall_confidence} size="overall" onInk />}
              </div>
            </div>
          </div>
        </div>
      </Band>

      <Doc>
        <div className="no-print flex gap-x-5 gap-y-1 justify-end items-baseline flex-wrap pt-4 -mb-8">
          <Eyebrow className="text-ink-70 !tracking-[0.1em]">Export</Eyebrow>
          <button type="button" className="text-toggle !text-meta" onClick={exportCsv}>CSV row</button>
          <button type="button" className="text-toggle !text-meta" onClick={copyMarkdown}>{copied ? 'Markdown copied ✓' : 'Copy Markdown'}</button>
          <button type="button" className="text-toggle !text-meta" onClick={printPdf}>Print / PDF</button>
        </div>
        {/* Layer ledger */}
        <section className="mt-14">
          <SectionHead title="Rights layers" sub="Separately owned. The answer rolls up from these." />
          {required.map((lv, i) => (
            <LayerRow key={lv.layer_id} lv={lv} layer={layerOf(lv.layer_id)} artist={artist} blocking={blockingIds.includes(lv.layer_id)}
              disputed={derivative && lv.layer_id === 'composition'}
              first={i === 0} open={!!open[lv.layer_id]} onToggle={() => toggle(lv.layer_id)} />
          ))}

          {/* Clearance — which layer, what license, where to go. */}
          <div className="border-t border-ink-20 py-5 px-1 flex gap-y-3 gap-x-8 flex-wrap">
            <div className="flex-[0_1_240px] min-w-[180px] pt-1"><Eyebrow>Clearance</Eyebrow></div>
            <div className="flex-[1_1_380px] min-w-[240px] flex flex-col gap-3">
              {toClear.length === 0 ? (
                <div className="text-body leading-[1.55] max-w-[56ch]">
                  {worst === 0 ? 'Nothing to clear for this purpose.' : 'Nothing can be cleared until the open question below is settled.'}
                </div>
              ) : (
                <>
                  {toClear.map((l) => (
                    <div key={l.layer_id} className="flex flex-col gap-1 max-w-[62ch]">
                      <Eyebrow tracking={12} className="text-ink-70">{titleOf(l)}</Eyebrow>
                      <div className="text-body leading-[1.55]">
                        {l.licensing_path}.{l.cost_band ? ` Typically ${l.cost_band}.` : ''}
                      </div>
                      <button type="button" className="text-toggle !text-meta self-start no-print"
                        onClick={() => {
                          navigator.clipboard?.writeText(licenseRequest(resp, params, l.layer_id,
                            enrich?.layers?.[l.layer_id]?.holders?.map((h) => ({ name: h.name.value, role: h.role }))))
                          setReqCopied(l.layer_id)
                          setTimeout(() => setReqCopied(null), 1600)
                        }}>
                        {reqCopied === l.layer_id ? 'Request copied ✓'
                          : `Copy ${l.layer_id === 'composition' ? 'sync' : 'master use'} request`}
                      </button>
                    </div>
                  ))}
                  <div className="text-meta font-medium leading-[1.7] text-ink-70 max-w-[70ch]">
                    Cost bands are rough orders of magnitude from trade practice, not quotes; nobody
                    publishes sync prices. The request templates carry the standard fields publishers
                    expect, with the production-specific parts left as marked blanks.
                  </div>
                  {actLinks.length > 0 && (
                    <div className="flex flex-col gap-3 pt-2">
                      <Eyebrow tracking={12} className="text-ink-70">Where to find them</Eyebrow>
                      {actLinks.map((l) => <LinkLine key={l.url + l.source_name} l={l} />)}
                    </div>
                  )}
                  {toClear.map((l) => {
                    const e = enrich?.layers?.[l.layer_id]
                    if (!e?.holders?.length) return null
                    return (
                      <div key={l.layer_id + '-parties'} className="flex flex-col gap-2 pt-2 max-w-[62ch]">
                        <Eyebrow tracking={12} className="text-ink-70">The parties — {titleOf(l).toLowerCase()}, researched</Eyebrow>
                        {e.holders.map((h, i) => (
                          <div key={i} className="flex gap-x-4 gap-y-1 items-baseline flex-wrap text-body leading-[1.5]">
                            <span className="font-semibold">{h.name.value}</span>
                            <span className="text-ink-70">{h.is_administrator ? 'administrator' : h.role}</span>
                            {h.share_percent != null && <span className="font-mono font-medium text-meta">{h.share_percent}%</span>}
                            {h.territory && <span className="font-mono font-medium text-meta text-ink-70">{h.territory}</span>}
                          </div>
                        ))}
                        {(e.questions ?? []).map((q) => (
                          <div key={q.question_id} className="text-body leading-[1.5] text-ink-70 border-l-2 border-ink-20 pl-3">
                            {q.question} {q.why_it_matters}
                          </div>
                        ))}
                        <div className="text-meta font-medium leading-[1.7] text-ink-70">
                          {e.completeness_note} {e.mlc_note}
                        </div>
                      </div>
                    )
                  })}
                  {(enrich?.ledger?.length ?? 0) > 0 && (
                    <div className="font-mono font-medium text-meta text-ink-70 leading-[1.8]">
                      {enrich!.ledger.map((line, i) => <div key={i}>{line}</div>)}
                    </div>
                  )}
                  {!enrich && (
                    <div className="text-meta font-medium leading-[1.7] text-ink-70 max-w-[70ch]">
                      {enrichBusy
                        ? 'Researching the parties (Parallel Task)\u2026'
                        : <>We can&rsquo;t yet tell you how many parties are involved or whether one company controls
                           everything. That data is in the MLC&rsquo;s database and we don&rsquo;t have API access yet.
                           The links above are the manual route.</>}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {nonRequired.map((lv) => (
            <div key={lv.layer_id} className="border-t-2 border-dashed border-ink-20 pt-6 pb-2 px-1">
              <Eyebrow tracking={12} className="text-ink-70 mb-[14px]">Not required for this purpose</Eyebrow>
              <div className="flex gap-y-4 gap-x-8 flex-wrap">
                <div className="flex-[0_1_240px] min-w-[180px]"><Stamp verdict={lv.verdict} size={16} /></div>
                <div className="flex-[1_1_380px] min-w-[240px]">
                  <div className="flex gap-y-[6px] gap-x-[14px] items-baseline flex-wrap">
                    <div className="font-bold text-title text-ink-70">{titleOf(lv)}</div>
                    <div className="font-mono font-medium text-meta text-ink-70">{subOf(lv, layerOf(lv.layer_id), artist)}</div>
                  </div>
                  <div className="text-body leading-[1.55] text-ink-70 mt-[6px] max-w-[62ch]">{lv.reasoning} {lv.intent_note}</div>
                </div>
              </div>
            </div>
          ))}
        </section>

        {/* Open questions */}
        <section className="mt-16">
          <SectionHead title={`Open questions — ${resp.unresolved.length}`}
            sub={!resp.unresolved.length ? 'Research settled every question it asked.'
              : resp.unresolved.some((u) => ANSWER_CFG[u.question_id])
                ? 'Some take an answer directly — supply what you found and the verdict re-runs at a confidence that follows your source. The rest carry the search terms and links to settle them externally.'
                : undefined} />
          {resp.unresolved.map((q, i) => (
            <QuestionRow key={q.question_id} q={q} open={!!open[`q${i}`]} onToggle={() => toggle(`q${i}`)}
              busy={busy} prior={params.answers?.[q.question_id]} onAnswer={onAnswer} />
          ))}
        </section>

        {/* Alternatives */}
        {resp.alternatives.length > 0 && (
          <section className="mt-16">
            <SectionHead title="Alternatives" sub="The same job without the rights problem." />
            {resp.alternatives.map((a) => (
              <div key={a.title} className="flex gap-y-2 gap-x-4 items-baseline flex-wrap py-4 border-t border-ink-20">
                <Stamp verdict="clear" size={16} className="flex-none" />
                <div className="font-semibold text-body">{a.title}</div>
                {a.creator && <div className="text-meta font-medium text-ink-70">{a.creator}</div>}
                <div className="text-body text-ink-70 flex-[1_1_100%] max-w-[70ch] leading-[1.5]">
                  {a.why_similar}{a.url && <span> · <a href={a.url} target="_blank" rel="noopener">record</a> ↗</span>}
                </div>
              </div>
            ))}
          </section>
        )}

        {/* Records */}
        <section className="mt-16">
          <SectionHead title="The records"
            right={<TextToggle open={!!open.records} closed="Show links" opened="Hide links" onClick={() => toggle('records')} className="whitespace-nowrap" />} />
          {open.records && (
            <div className="flex gap-y-8 gap-x-12 flex-wrap pt-[22px]">
              {groupLinks(resp.handoff_links).map((g) => (
                <div key={g.title} className="flex-[1_1_320px] min-w-[240px]">
                  <Eyebrow className="mb-1">{g.title}</Eyebrow>
                  <div className="text-body text-ink-70 mb-[14px]">{g.sub}</div>
                  <div className="flex flex-col gap-3">
                    {g.items.map((l) => <LinkLine key={l.url + l.source_name} l={l} />)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* The run - the accession log kept on the record, so a warm query
            stays legible after the fact. Every query in a demo is warm. */}
        {(resp.run_log?.length ?? 0) > 0 && (
          <section className="mt-16">
            <SectionHead title="The run"
              sub={`${(resp.run_log[resp.run_log.length - 1].elapsed_ms / 1000).toFixed(1)}s \u00b7 ${resp.run_log[resp.run_log.length - 1].sources_consulted} sources consulted \u00b7 what ran, which tier answered, what was cached`} />
            <TextToggle open={!!open['run']} closed="Show the log" opened="Close" onClick={() => toggle('run')} className="mt-3" />
            {open['run'] && (
              <div className="mt-2 flex flex-col">
                {resp.run_log.map((ev, i) => (
                  <div key={i} className="flex gap-x-[14px] gap-y-1 items-baseline flex-wrap py-[7px] border-t border-dashed border-ink-20 first:border-t-0">
                    <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_52px]">{(ev.elapsed_ms / 1000).toFixed(1)}s</div>
                    <div className={`text-body leading-[1.5] flex-[1_1_320px] min-w-[220px] ${ev.status === 'failed' || ev.degraded ? 'line-through text-ink-70' : ''}`}>
                      {ev.message}
                      {ev.detail && <span className="font-mono font-medium text-meta text-ink-70"> {ev.detail}</span>}
                      {ev.error_message && <span className="text-ink-70"> {ev.error_message}</span>}
                    </div>
                    <div className="font-mono font-medium text-meta text-ink-70 uppercase whitespace-nowrap">{ev.stage}</div>
                  </div>
                ))}
                <div className="flex gap-x-[14px] gap-y-1 items-baseline flex-wrap py-[7px] border-t border-dashed border-ink-20">
                  <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_52px]">after</div>
                  <div className="text-body leading-[1.5] flex-[1_1_320px] min-w-[220px]">{enrichmentLine}</div>
                  <div className="font-mono font-medium text-meta text-ink-70 uppercase whitespace-nowrap">clearance</div>
                </div>
                {(enrich?.ledger ?? []).map((line, i) => (
                  <div key={`e${i}`} className="flex gap-x-[14px] gap-y-1 items-baseline flex-wrap py-[7px] border-t border-dashed border-ink-20">
                    <div className="font-mono font-medium text-meta text-ink-70 flex-[0_0_52px]"></div>
                    <div className="text-body leading-[1.5] flex-[1_1_320px] min-w-[220px]">{line}</div>
                    <div className="font-mono font-medium text-meta text-ink-70 uppercase whitespace-nowrap">clearance</div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <p className="mt-14 mb-0 text-meta font-medium leading-[1.7] text-ink-70 max-w-[78ch]">{resp.disclaimer}</p>
      </Doc>
    </>
  )
}

// --- rows ------------------------------------------------------------------------

function titleOf(lv: LayerVerdict): string {
  return lv.layer_label.split(' (')[0]
}

function subOf(lv: LayerVerdict, layer: RightsLayer | undefined, artist: string | null, disputed = false): string {
  const parts: string[] = []
  const tf = layer?.term_facts
  if (lv.layer_id === 'composition') {
    if (tf?.first_publication_year) parts.push(String(tf.first_publication_year.value))
    const writers = layer?.holders.map((h) => h.name.value) ?? []
    if (writers.length) parts.push(writers.join(' / '))
    if (disputed) parts.push('authorship in question')
  } else {
    if (artist) parts.push(artist)
    if (tf?.recording_first_published_year) parts.push(String(tf.recording_first_published_year.value))
    const basis = tf?.recording_date_basis
    if (basis === 'dated_performance') parts.push('dated session')
    else if (basis === 'first_release_date') parts.push('release on file only')
    else if (basis === 'researched') parts.push('researched release')
  }
  return parts.join(' · ')
}

function LayerRow({ lv, layer, artist, blocking, first, open, onToggle, disputed = false }:
  { lv: LayerVerdict; layer: RightsLayer | undefined; artist: string | null; blocking: boolean; first: boolean; open: boolean; onToggle: () => void; disputed?: boolean }) {
  const wrap = blocking
    ? 'my-7 border border-ink-20 border-l-4 border-l-red rounded-6 py-6 px-7 max-[560px]:py-[18px] max-[560px]:px-4'
    : `py-7 px-1 ${first ? '' : 'border-t border-ink-20'}`
  return (
    <div className={wrap}>
      {blocking && <Eyebrow tracking={12} className="text-red mb-[18px]">Blocking — this layer sets the answer</Eyebrow>}
      <div className="flex gap-y-6 gap-x-8 flex-wrap">
        <div className="flex-[0_1_240px] min-w-[180px] flex flex-col gap-2">
          <Stamp verdict={lv.verdict} size={blocking ? 38 : 28} underline />
          <div className="font-mono font-medium text-meta tracking-[0.06em] text-ink-70">{expiryLine(lv.determination)}</div>
        </div>
        <div className="flex-[1_1_380px] min-w-[240px] flex flex-col gap-[10px]">
          <div className="flex gap-y-[6px] gap-x-[14px] items-baseline flex-wrap">
            <h2 className="m-0 font-bold text-title">{titleOf(lv)}</h2>
            <div className="font-mono font-medium text-meta text-ink-70">{subOf(lv, layer, artist, disputed)}</div>
          </div>
          <div className="text-body leading-[1.55] max-w-[62ch] text-pretty">{lv.reasoning}</div>
          {lv.verdict === 'license_required' && lv.licensing_path && (
            <div className="text-body leading-[1.55] max-w-[62ch] text-ink-70">{lv.licensing_path}.</div>
          )}
          <div className="flex items-center gap-5 flex-wrap mt-[2px]">
            {lv.verdict === 'undetermined'
              ? <div className="text-meta font-medium text-ink-70">awaits the open question below</div>
              : <Ticks level={lv.determination.confidence} size="layer" />}
            <TextToggle open={open} closed="Evidence" opened="Hide evidence" onClick={onToggle} />
          </div>
          {open && <LayerDetail lv={lv} layer={layer} />}
        </div>
      </div>
    </div>
  )
}

function LayerDetail({ lv, layer }: { lv: LayerVerdict; layer: RightsLayer | undefined }) {
  const facts = layer ? (Object.entries(layer.term_facts) as [string, unknown][])
    .filter(([k, v]) => k in FACT_LABEL && v && typeof v === 'object')
    .map(([k, v]) => [k, v as ResearchedFact] as const) : []
  const note = lv.holders.length === 0
    ? (lv.verdict === 'clear' ? 'No active rights holder; the copyright has expired.' : 'No rights holder identified from the records consulted.')
    : (lv.verdict === 'clear' ? 'No active rights holder; the copyright has expired. Original parties, for the record:' : null)
  return (
    <div className="mt-[14px] border-t border-ink-20 pt-[18px] flex flex-col gap-6">
      <div>
        <Eyebrow className="mb-[10px]">Rights holders</Eyebrow>
        {note && <div className="text-body italic text-ink-70 mb-2">{note}</div>}
        <div className="flex flex-col">
          {lv.holders.map((h) => <HolderRow key={h.name.value + h.role} h={h} />)}
        </div>
      </div>
      <div>
        <Eyebrow className="mb-[10px]">Evidence</Eyebrow>
        <div className="flex flex-col gap-[18px]">
          {layer && layer.identifiers.length > 0 && (
            <EvidenceItem label="Identifiers" level={layer.identifiers[0].confidence}
              value={layer.identifiers.map((i) => `${i.scheme.replace('musicbrainz_', 'mb ')} ${i.value}`).join(' · ')} />
          )}
          {facts.map(([k, f]) => (
            <EvidenceItem key={k} label={FACT_LABEL[k]} level={f.confidence} value={factValue(k, f.value)}
              reasoning={f.reasoning} conflicting={f.conflicting_values} sources={f.sources} />
          ))}
          {facts.length === 0 && !layer?.identifiers.length && <div className="text-body italic text-ink-70">No researched facts on this layer.</div>}
        </div>
      </div>
    </div>
  )
}

function HolderRow({ h }: { h: RightsHolder }) {
  return (
    <div className="flex flex-col items-start gap-[6px] py-3 border-t border-dashed border-ink-20">
      <div className="flex gap-3 items-center flex-wrap">
        <div className="font-semibold text-body">{h.name.value}</div>
        <div className="text-meta font-medium text-ink-70">{h.role}</div>
        {h.is_administrator && <div className="text-meta font-semibold tracking-[0.06em] uppercase bg-ink text-paper rounded-6 px-2 py-[2px] whitespace-nowrap">Administers licensing</div>}
      </div>
      <div className="flex gap-y-[6px] gap-x-[18px] items-start flex-wrap font-mono font-medium text-meta leading-[1.5]">
        <div className="text-ink">share {h.share_percent == null ? '—' : pct(h.share_percent)}</div>
        <div className="text-ink-70">{h.territory ?? '—'}</div>
        <div className="text-ink-70">enforcement: {h.enforcement_posture}</div>
        <div className="text-ink-70">{confidenceLabel(h.name.confidence)}</div>
      </div>
      {h.contact_path && (
        <div className="text-body">{h.contact_path} <span className="text-meta font-medium text-ink-70">↗ licensing contact</span></div>
      )}
    </div>
  )
}

function EvidenceItem({ label, level, value, reasoning, conflicting = [], sources = [] }:
  { label: string; level: ResearchedFact['confidence']; value: string; reasoning?: string | null; conflicting?: string[]; sources?: Source[] }) {
  return (
    <div className="border-l-2 border-ink-20 pl-4">
      <div className="flex gap-y-[6px] gap-x-[10px] items-start flex-wrap">
        <Eyebrow tracking={12} className="leading-[1.5] text-ink-70">{label}</Eyebrow>
        <div className="mt-[3px]"><Ticks level={level} size="evidence" /></div>
      </div>
      <div className="font-mono font-medium text-body mt-[6px] break-words">{value}</div>
      {reasoning && <div className="text-body leading-[1.55] text-ink-70 mt-[6px] max-w-[60ch]">{reasoning}</div>}
      {conflicting.length > 0 && (
        <div className="text-body leading-[1.55] text-ink-70 mt-[6px] max-w-[60ch]">Also reported: <span className="font-mono font-medium">{conflicting.join('; ')}</span></div>
      )}
      {sources.length > 0 && (
        <div className="flex flex-col gap-[6px] mt-[10px]">
          {sources.map((s, i) => <SourceLine key={i} s={s} />)}
        </div>
      )}
    </div>
  )
}

function SourceLine({ s }: { s: Source }) {
  const href = sourceHref(s)
  return (
    <div className="text-body flex gap-y-[6px] gap-x-[10px] items-baseline flex-wrap">
      <Tag>{METHOD_LABEL[s.method] ?? s.method}</Tag>
      {href ? <a href={href} target="_blank" rel="noopener">{s.name}</a> : <span>{s.name}</span>}
      <span className="font-mono font-medium text-meta text-ink-70">retrieved {shortDate(s.retrieved_at)}</span>
      {s.excerpt && <span className="basis-full italic text-ink-70 text-body">“{s.excerpt}”</span>}
    </div>
  )
}

// Questions with an answer control. One entry today; more question types are
// entries here plus a handler in pipeline/user_facts.py, not a redesign.
type AnswerCfg = { kind: 'boolean' | 'year'; prompt: string; source: string; yes?: string; no?: string }

// Every answerable question and the shape of the fact it takes. Backend
// truth is pipeline/user_facts.py HANDLERS; this mirrors it.
const ANSWER_CFG: Record<string, AnswerCfg> = {
  'composition:renewal': { kind: 'boolean', yes: 'Renewed', no: 'Not renewed',
    prompt: 'Found the answer? Enter it',
    source: 'The record: an RE number and date, or what you searched and what came back' },
  'composition:publication_year': { kind: 'year',
    prompt: 'Know the year? Enter it',
    source: 'Where you found it, e.g. the copyright registration' },
  'sound_recording:first_publication': { kind: 'year',
    prompt: 'Know the first-release year? Enter it',
    source: 'The original pressing: label and catalogue number' },
  'composition:death_years': { kind: 'year',
    prompt: 'Know when the last writer died? Enter the year',
    source: 'The writer and death year, and how you know the list is complete' },
  'composition:writers': { kind: 'year',
    prompt: 'Know when the last writer died? Enter the year',
    source: 'The writer and death year, and how you know the list is complete' },
}

function AnswerControl({ cfg, prior, busy, onAnswer }: {
  cfg: AnswerCfg
  prior?: UserAnswerParam
  busy: boolean
  onAnswer: (payload: { answer?: boolean; value?: number; attestation: string }) => void
}) {
  // Consequence stated before the click. A bare answer is an opinion (low
  // confidence); with a source it is a finding (medium — the ceiling for
  // anything user-supplied). A value implying public domain without a source
  // is withheld. Mirrors pipeline/user_facts.py + LOW_CONFIDENCE_PD_RULE.
  const [choice, setChoice] = useState<boolean | null>(prior?.answer ?? null)
  const [year, setYear] = useState<string>(prior?.value != null ? String(prior.value) : '')
  const [att, setAtt] = useState(prior?.attestation ?? '')
  const attested = att.trim().length > 0
  const yearOk = /^\d{3,4}$/.test(year.trim())
  const touched = cfg.kind === 'boolean' ? choice !== null : yearOk
  const consequence = !touched ? null
    : attested
      ? 'An attested answer is a medium-confidence finding; the verdict updates and the question closes.'
      : 'Without a source this stays low confidence: the verdict updates where it can move toward protected, but a result implying public domain is withheld and the question stays open.'
  const submit = () => {
    if (cfg.kind === 'boolean' && choice !== null) onAnswer({ answer: choice, attestation: att.trim() })
    else if (cfg.kind === 'year' && yearOk) onAnswer({ value: Number(year.trim()), attestation: att.trim() })
  }
  return (
    <div className="mt-1 mb-2 border border-ink-20 rounded-6 px-[18px] py-4 flex flex-col gap-3 max-w-[64ch] print:hidden">
      <Eyebrow tracking={12} className="text-ink-70">{cfg.prompt}</Eyebrow>
      {cfg.kind === 'boolean' ? (
        <div className="flex gap-2 flex-wrap">
          <button type="button" className="btn-answer" aria-pressed={choice === true} onClick={() => setChoice(true)}>{cfg.yes}</button>
          <button type="button" className="btn-answer" aria-pressed={choice === false} onClick={() => setChoice(false)}>{cfg.no}</button>
        </div>
      ) : (
        <input value={year} onChange={(e) => setYear(e.target.value)} inputMode="numeric" maxLength={4}
          placeholder="Year, e.g. 1971"
          className="font-mono font-medium text-body text-ink bg-transparent border border-ink-20 rounded-6 px-[14px] py-[10px] w-[180px] placeholder:text-ink-70" />
      )}
      {touched && (
        <>
          <div className="flex flex-col gap-[6px]">
            <Eyebrow tracking={12} className="text-ink-70">Your source</Eyebrow>
            <input value={att} onChange={(e) => setAtt(e.target.value)} maxLength={300}
              placeholder={cfg.source}
              className="font-mono font-medium text-body text-ink bg-transparent border border-ink-20 rounded-6 px-[14px] py-[10px] w-full placeholder:text-ink-70" />
          </div>
          <div className="text-meta font-medium text-ink-70 leading-[1.6] max-w-[58ch]">
            {consequence} The answer is entered on the record as asserted by you.
          </div>
          <button type="button" className="btn-copy self-start" disabled={busy} onClick={submit}>
            {busy ? 'Re-running research…' : 'Record the answer and re-run'}
          </button>
        </>
      )}
    </div>
  )
}

function QuestionRow({ q, open, onToggle, busy, prior, onAnswer }: {
  q: UnresolvedQuestion; open: boolean; onToggle: () => void; busy: boolean
  prior?: UserAnswerParam; onAnswer: (questionId: string, payload: { answer?: boolean; value?: number; attestation: string }) => void
}) {
  const cfg = ANSWER_CFG[q.question_id]
  const [copied, setCopied] = useState(false)
  const terms = q.search_terms.join('  ·  ')
  const copy = () => {
    navigator.clipboard?.writeText(q.search_terms.join('\n'))
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }
  return (
    <div className="pt-6 pb-2">
      <div className="flex gap-y-[10px] gap-x-4 items-start flex-wrap">
        <h3 className="m-0 font-bold text-title flex-[1_1_240px] max-w-[48ch] text-pretty">{q.question}</h3>
        <Tag className="ml-auto tracking-[0.1em] !px-[9px] !py-[3px]">Effort: {EFFORT_LABEL[q.estimated_effort] ?? q.estimated_effort}</Tag>
      </div>
      <div className="text-body leading-[1.55] mt-[10px] max-w-[68ch]">{q.why_it_matters}</div>
      <TextToggle open={open}
        closed={cfg ? 'Enter what you found, or settle it externally' : 'Where to settle it'}
        opened="Close" onClick={onToggle} className="mt-[10px]" />
      {open && (
        <>
          {cfg && <AnswerControl cfg={cfg} prior={prior} busy={busy} onAnswer={(p) => onAnswer(q.question_id, p)} />}
          <div className="mt-[14px] flex flex-col max-w-[68ch]">
            {[['If yes', q.if_yes], ['If no', q.if_no]].map(([k, v]) => (
              <div key={k} className="flex gap-x-4 py-2 border-t border-dashed border-ink-20 first:border-t-0">
                <Eyebrow tracking={12} className="text-ink-70 flex-[0_0_52px] pt-[2px]">{k}</Eyebrow>
                <div className="text-body leading-[1.5] text-ink-70">{v}</div>
              </div>
            ))}
          </div>
          {q.search_terms.length > 0 && (
            <div className="mt-4 border border-dashed border-ink-20 rounded-6 px-[18px] py-4 flex gap-4 items-center flex-wrap">
              <div className="font-mono font-medium text-body flex-[1_1_320px] min-w-[220px] leading-[1.5]">{terms}</div>
              <button type="button" className="btn-copy" onClick={copy}>{copied ? 'Copied ✓' : 'Copy search'}</button>
            </div>
          )}
          {q.resolution_links.length > 0 && (
            <div className="flex flex-col gap-2 mt-[14px]">
              {q.resolution_links.map((l, i) => <LinkLine key={i} l={l} />)}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function LinkLine({ l }: { l: HandoffLink }) {
  // Label above content: the type hierarchy carries what tier tags and
  // punctuation were carrying. The instruction says whether the link goes
  // straight there, opens a search, or needs hand-work.
  const parts = [l.description, l.navigation_hint].filter(Boolean) as string[]
  if (l.tier === 'prefilled_search') parts.push('Opens a search already filled in')
  const note = parts.join('. ')
  return (
    <div className="flex flex-col gap-[2px] max-w-[64ch]">
      <div>
        <a href={l.url} target="_blank" rel="noopener"
          className="font-mono font-medium text-meta tracking-[0.08em] uppercase">{l.source_name}</a>
      </div>
      {(note || l.paste_string) && (
        <div className="text-ink-70 text-body leading-[1.5]">
          {note}{note ? '. ' : ''}
          {l.paste_string && <>Copy <span className="font-mono font-medium text-ink">“{l.paste_string}”</span>.</>}
        </div>
      )}
    </div>
  )
}

function groupLinks(links: HandoffLink[]): { title: string; sub: string; items: HandoffLink[] }[] {
  // Act links render in the Clearance section, next to the decision they serve.
  const groups = [
    { key: 'verify', title: 'Verify', sub: 'Check what we determined.' },
    { key: 'resolve', title: 'Resolve', sub: 'Settle what research couldn’t.' },
    { key: 'alternative', title: 'Instead', sub: 'Substitutes without the rights problem.' },
  ]
  return groups.map((g) => ({ ...g, items: links.filter((l) => l.purpose === g.key) })).filter((g) => g.items.length > 0)
}
