// Result — docs/design-system.md §5 "Result". Every value rendered here comes
// from the RightsResponse; the screen adds no judgement of its own.
import { useEffect, useState } from 'react'
import type { HandoffLink, Intent, Jurisdiction, LayerVerdict, ResearchedFact, RightsHolder, RightsLayer, RightsResponse, Source, UnresolvedQuestion, Verdict } from '../types'
import { Band, Controls, Doc, Eyebrow, SectionHead, Stamp, Tag, TextToggle, Ticks } from '../components/ui'
import { EFFORT_LABEL, FACT_LABEL, METHOD_LABEL, TIER_LABEL, VERDICT_WORD, confidenceLabel, expiryLine, factValue, pct, shortDate, sourceHref, splitQuery } from '../lib/format'

const ORDER: Record<Verdict, number> = { clear: 0, clear_with_conditions: 1, license_required: 2, restricted: 3, undetermined: 4 }

export interface ResultProps {
  resp: RightsResponse
  intent: Intent
  jurisdiction: Jurisdiction
  busy: boolean
  onIntent: (i: Intent) => void
  onJurisdiction: (j: Jurisdiction) => void
  onNewInquiry: () => void
}

export default function Result({ resp, intent, jurisdiction, busy, onIntent, onJurisdiction, onNewInquiry }: ResultProps) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const toggle = (k: string) => setOpen((s) => ({ ...s, [k]: !s[k] }))
  const [stampKey, setStampKey] = useState(0)
  useEffect(() => { setStampKey((k) => k + 1) }, [resp])

  const { artist } = splitQuery(resp.query.raw_input)
  const year = resp.entity.year?.value
  const required = resp.layer_verdicts.filter((l) => l.is_required)
  const nonRequired = resp.layer_verdicts.filter((l) => !l.is_required)
  const worst = Math.max(...required.map((l) => ORDER[l.verdict]), 0)
  const blockingIds = worst > 0 ? required.filter((l) => ORDER[l.verdict] === worst).map((l) => l.layer_id) : []
  const layerOf = (id: string) => resp.entity.layers.find((l) => l.layer_id === id)
  const toClear = required.filter((l) => l.verdict === 'license_required')

  return (
    <>
      <Band
        label="Can I use this? — Research record"
        context={
          <div className="flex gap-5 items-baseline flex-wrap">
            <div className="font-mono font-medium text-meta text-paper-72">
              researched {shortDate(resp.generated_at).toLowerCase()} · {resp.served_from_cache ? 'cached' : 'fresh'}
            </div>
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
            <p className="m-0 mt-5 text-headline font-medium leading-[1.3] max-w-[40ch] text-pretty text-paper">{resp.overall_headline}</p>
          </div>
          <div className="flex flex-col gap-[22px]">
            <Controls intent={intent} jurisdiction={jurisdiction} onIntent={onIntent} onJurisdiction={onJurisdiction} onInk busy={busy} />
            <div className="flex flex-col gap-[10px]">
              <Eyebrow className="text-paper-72">Confidence</Eyebrow>
              <div className="min-h-10 flex items-center">
                <Ticks level={resp.overall_confidence} size="overall" onInk />
              </div>
            </div>
          </div>
        </div>
      </Band>

      <Doc>
        {/* Layer ledger */}
        <section className="mt-14">
          <SectionHead title="Rights layers" sub="One search is several separately-owned works. The answer rolls up from these." />
          {required.map((lv, i) => (
            <LayerRow key={lv.layer_id} lv={lv} layer={layerOf(lv.layer_id)} artist={artist} blocking={blockingIds.includes(lv.layer_id)}
              first={i === 0} open={!!open[lv.layer_id]} onToggle={() => toggle(lv.layer_id)} />
          ))}

          {/* Clearance */}
          <div className="border-t border-ink-20 py-5 px-1 flex gap-y-3 gap-x-8 flex-wrap">
            <div className="flex-[0_1_240px] min-w-[180px] pt-1"><Eyebrow>Clearance</Eyebrow></div>
            <div className="flex-[1_1_380px] min-w-[240px] flex flex-col gap-2">
              <div className="flex gap-y-2 gap-x-5 items-baseline flex-wrap">
                <div className="text-body leading-[1.55] max-w-[56ch]">
                  {toClear.length === 0
                    ? (worst === 0 ? 'Nothing to clear for this purpose.' : 'Nothing can be cleared until the open question below is settled.')
                    : `${toClear.length} ${toClear.length === 1 ? 'layer' : 'layers'} to clear · difficulty ${toClear.map((l) => l.clearance.difficulty).sort()[toClear.length - 1]}.`}
                </div>
                {toClear.length > 0 && <TextToggle open={!!open.clearance} closed="Breakdown" opened="Hide breakdown" onClick={() => toggle('clearance')} className="whitespace-nowrap" />}
              </div>
              {open.clearance && toClear.length > 0 && (
                <div className="flex flex-col gap-[14px] pt-[10px]">
                  <div className="flex gap-y-5 gap-x-10 flex-wrap">
                    <Stat value={String(toClear.length)} label="Layers to clear" />
                    <Stat value={pct(toClear.reduce<number | null>((a, l) => (l.clearance.unclaimed_share_percent ?? a), null))} label="Unclaimed" />
                    <Stat value={toClear.map((l) => l.clearance.difficulty).sort()[toClear.length - 1]} label="Difficulty" mono={false} />
                  </div>
                  <div className="flex flex-col gap-[10px] text-body leading-[1.55] text-ink-70 max-w-[60ch]">
                    {toClear.map((l) => (
                      <div key={l.layer_id}>
                        <span className="font-semibold text-ink">{titleOf(l)}.</span> {l.licensing_path}{l.cost_band ? ` Cost band: ${l.cost_band}.` : ''}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {nonRequired.map((lv) => (
            <div key={lv.layer_id} className="border-t-2 border-dashed border-ink-20 pt-6 pb-2 px-1">
              <Eyebrow tracking={12} className="text-ink-70 mb-[14px]">Not required for this purpose — shown for reference, excluded from the answer</Eyebrow>
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
            sub={resp.unresolved.length ? 'What research couldn’t settle, and exactly where to settle it.' : 'Research settled every question it asked.'} />
          {resp.unresolved.map((q, i) => (
            <QuestionRow key={q.question_id} q={q} open={!!open[`q${i}`]} onToggle={() => toggle(`q${i}`)} />
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
                  {a.why_similar}{a.url && <span> — <a href={a.url} target="_blank" rel="noopener">record</a> ↗</span>}
                </div>
              </div>
            ))}
          </section>
        )}

        {/* Records */}
        <section className="mt-16">
          <SectionHead title="Go to the records" sub="The records behind this verdict — check them, then act."
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

        <p className="mt-14 mb-0 text-meta font-medium leading-[1.7] text-ink-70 max-w-[78ch]">{resp.disclaimer}</p>
      </Doc>
    </>
  )
}

// --- rows ------------------------------------------------------------------------

function titleOf(lv: LayerVerdict): string {
  return lv.layer_label.split(' (')[0]
}

function subOf(lv: LayerVerdict, layer: RightsLayer | undefined, artist: string | null): string {
  const parts: string[] = []
  const tf = layer?.term_facts
  if (lv.layer_id === 'composition') {
    if (tf?.first_publication_year) parts.push(String(tf.first_publication_year.value))
    const writers = layer?.holders.map((h) => h.name.value) ?? []
    if (writers.length) parts.push(writers.join(' / '))
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

function LayerRow({ lv, layer, artist, blocking, first, open, onToggle }:
  { lv: LayerVerdict; layer: RightsLayer | undefined; artist: string | null; blocking: boolean; first: boolean; open: boolean; onToggle: () => void }) {
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
            <div className="font-mono font-medium text-meta text-ink-70">{subOf(lv, layer, artist)}</div>
          </div>
          <div className="text-body leading-[1.55] max-w-[62ch] text-pretty">{lv.reasoning}</div>
          {lv.verdict === 'license_required' && lv.licensing_path && (
            <div className="text-body leading-[1.55] max-w-[62ch] text-ink-70">{lv.licensing_path}.</div>
          )}
          <div className="flex items-center gap-5 flex-wrap mt-[2px]">
            <Ticks level={lv.determination.confidence} size="layer" />
            <TextToggle open={open} closed="Holders & evidence" opened="Hide holders & evidence" onClick={onToggle} />
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
    ? (lv.verdict === 'clear' ? 'No active rights holder — the copyright has expired.' : 'No rights holder identified from the records consulted — see the records below.')
    : (lv.verdict === 'clear' ? 'No active rights holder — the copyright has expired. Original parties, for the record:' : null)
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

function Stat({ value, label, mono = true }: { value: string; label: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <div className={`${mono ? 'font-mono font-medium' : 'font-bold uppercase tracking-[0.02em]'} text-stat leading-none`}>{value}</div>
      <Eyebrow className="text-ink-70 tracking-[0.1em]">{label}</Eyebrow>
    </div>
  )
}

function QuestionRow({ q, open, onToggle }: { q: UnresolvedQuestion; open: boolean; onToggle: () => void }) {
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
      <TextToggle open={open} closed="Where to check, and what it would change" opened="Hide where to check" onClick={onToggle} className="mt-[10px]" />
      {open && (
        <>
          <div className="text-body leading-[1.55] mt-[14px] text-ink-70 max-w-[68ch]">
            <span className="font-semibold text-ink">If yes:</span> {q.if_yes} <span className="font-semibold text-ink">If no:</span> {q.if_no}
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
  const note = [l.description, l.navigation_hint].filter(Boolean).join(' — ')
  return (
    <div className="text-body flex gap-y-[6px] gap-x-[10px] items-baseline flex-wrap">
      <Tag>{TIER_LABEL[l.tier]}</Tag>
      <a href={l.url} target="_blank" rel="noopener">{l.source_name}</a>
      {note && <span className="basis-full text-ink-70 text-body leading-[1.5] max-w-[64ch]">{note}{l.paste_string ? <> Paste: <span className="font-mono font-medium">{l.paste_string}</span></> : null}</span>}
    </div>
  )
}

function groupLinks(links: HandoffLink[]): { title: string; sub: string; items: HandoffLink[] }[] {
  const groups = [
    { key: 'verify', title: 'Verify', sub: 'Check what we determined.' },
    { key: 'resolve', title: 'Resolve', sub: 'Settle what research couldn’t.' },
    { key: 'license', title: 'Act', sub: 'Start the license.' },
    { key: 'alternative', title: 'Instead', sub: 'Substitutes without the rights problem.' },
  ]
  return groups.map((g) => ({ ...g, items: links.filter((l) => l.purpose === g.key) })).filter((g) => g.items.length > 0)
}
