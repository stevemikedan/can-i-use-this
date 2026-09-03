// Export — CSV, Markdown, and helpers. One column schema for a single result
// and for cue-sheet rows, so a spreadsheet built one search at a time and a
// pasted cue list land in the same columns. The permalink re-opens (re-runs)
// the record; the researched date is there because rights lists go stale.
import type { Intent, Jurisdiction, LayerVerdict, QueryParams, RightsResponse, Verdict } from '../types'
import { EFFORT_LABEL, FACT_LABEL, VERDICT_WORD, confidenceLabel, expiryLine, factValue, shortDate, sourceHref, splitQuery } from './format'

export const VERDICT_SEVERITY: Record<Verdict, number> = {
  clear: 0, clear_with_conditions: 1, license_required: 2, restricted: 3, undetermined: 4,
}

/** The required layers whose verdict sets the answer (empty when the roll-up is clear). */
export function blockingLayers(resp: RightsResponse): LayerVerdict[] {
  const required = resp.layer_verdicts.filter((l) => l.is_required)
  const worst = Math.max(...required.map((l) => VERDICT_SEVERITY[l.verdict]), 0)
  return worst > 0 ? required.filter((l) => VERDICT_SEVERITY[l.verdict] === worst) : []
}

export function layerTitle(lv: LayerVerdict): string {
  return lv.layer_label.split(' (')[0]
}

export function permalinkFor(p: QueryParams): string {
  const qs = new URLSearchParams({ q: p.title + (p.artist ? ` — ${p.artist}` : ''), i: p.intent, j: p.jurisdiction })
  if (p.duration) qs.set('d', p.duration)
  return `${window.location.origin}/?${qs.toString()}`
}

export function paramsFromUrl(search: string): QueryParams | null {
  const sp = new URLSearchParams(search)
  const q = sp.get('q')
  if (!q?.trim()) return null
  const { title, artist } = splitQuery(q)
  return {
    title,
    artist: artist ?? undefined,
    intent: (sp.get('i') as Intent) || 'film_tv',
    jurisdiction: (sp.get('j') as Jurisdiction) || 'US',
    duration: (sp.get('d') as QueryParams['duration']) || undefined,
  }
}

// --- CSV --------------------------------------------------------------------------

export const CSV_HEADER = [
  'title', 'artist', 'overall verdict', 'blocking layer', 'composition status', 'composition expiry',
  'recording status', 'recording expiry', 'confidence', 'open questions', 'jurisdiction', 'intent',
  'permalink', 'researched',
] as const

function esc(v: string | number | null | undefined): string {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function csvRow(resp: RightsResponse, params: QueryParams): string {
  const layer = (id: string) => resp.layer_verdicts.find((l) => l.layer_id === id)
  const comp = layer('composition')
  const rec = layer('sound_recording')
  const blocking = blockingLayers(resp)
  return [
    params.title,
    params.artist ?? '',
    VERDICT_WORD[resp.overall_verdict],
    blocking.map(layerTitle).join(' + '),
    comp ? VERDICT_WORD[comp.verdict] : '',
    comp?.determination.expiry_year ?? '',
    rec ? VERDICT_WORD[rec.verdict] : '',
    rec?.determination.expiry_year ?? '',
    resp.overall_confidence,
    resp.unresolved.length,
    params.jurisdiction,
    params.intent,
    permalinkFor(params),
    shortDate(resp.generated_at),
  ].map(esc).join(',')
}

export function toCsv(rows: { resp: RightsResponse; params: QueryParams }[]): string {
  return [CSV_HEADER.join(','), ...rows.map((r) => csvRow(r.resp, r.params))].join('\r\n') + '\r\n'
}

// --- Markdown ----------------------------------------------------------------------

export function toMarkdown(resp: RightsResponse, params: QueryParams): string {
  const lines: string[] = []
  const push = (s = '') => lines.push(s)
  const layerOf = (id: string) => resp.entity.layers.find((l) => l.layer_id === id)

  push(`# ${params.title}${params.artist ? ` — ${params.artist}` : ''}`)
  push()
  push(`**${VERDICT_WORD[resp.overall_verdict].toUpperCase()}.** ${resp.overall_headline}`)
  push()
  push(`${params.jurisdiction} · ${params.intent} · ${confidenceLabel(resp.overall_confidence)} · researched ${shortDate(resp.generated_at)} · [open the record](${permalinkFor(params)})`)
  push()
  push('## Rights layers')
  for (const lv of resp.layer_verdicts) {
    push()
    push(`### ${layerTitle(lv)} — ${VERDICT_WORD[lv.verdict]}${lv.is_required ? '' : ' (not required for this purpose)'}`)
    push()
    push(`- ${expiryLine(lv.determination)} · ${confidenceLabel(lv.determination.confidence)}`)
    push(`- ${lv.reasoning}`)
    if (lv.licensing_path) push(`- Licensing: ${lv.licensing_path}${lv.cost_band ? ` — ${lv.cost_band}` : ''}`)
    const tf = layerOf(lv.layer_id)?.term_facts
    if (tf) {
      for (const [key, label] of Object.entries(FACT_LABEL)) {
        const fact = (tf as unknown as Record<string, { value: unknown; confidence: string; reasoning: string | null; sources: { name: string; url: string | null; retrieved_at: string; excerpt: string | null }[] } | null>)[key]
        if (!fact) continue
        push(`- ${label}: **${factValue(key, fact.value)}** (${fact.confidence})${fact.reasoning ? ` — ${fact.reasoning}` : ''}`)
        for (const s of fact.sources) {
          const href = sourceHref(s as never)
          push(`  - ${href ? `[${s.name}](${href})` : s.name}, retrieved ${shortDate(s.retrieved_at)}${s.excerpt ? ` — “${s.excerpt}”` : ''}`)
        }
      }
    }
  }
  if (resp.unresolved.length) {
    push()
    push(`## Open questions — ${resp.unresolved.length}`)
    for (const q of resp.unresolved) {
      push()
      push(`### ${q.question} (effort: ${EFFORT_LABEL[q.estimated_effort] ?? q.estimated_effort})`)
      push()
      push(q.why_it_matters)
      push()
      push(`- If yes: ${q.if_yes}`)
      push(`- If no: ${q.if_no}`)
      if (q.search_terms.length) push(`- Search: ${q.search_terms.map((t) => `\`${t}\``).join(' · ')}`)
      for (const l of q.resolution_links) push(`- [${l.source_name}](${l.url})${l.navigation_hint ? ` — ${l.navigation_hint}` : ''}`)
    }
  }
  if (resp.handoff_links.length) {
    push()
    push('## Records')
    for (const l of resp.handoff_links) {
      push(`- [${l.source_name}](${l.url}) — ${linkNote(l)}`)
    }
  }
  push()
  push(`---`)
  push()
  push(`_${resp.disclaimer}_`)
  push()
  return lines.join('\n')
}

/** The same treatment the LinkLine component got: instruction sentences, no
 *  tier enums, no field-name prefixes. */
function linkNote(l: { description: string | null; navigation_hint: string | null; tier: string; paste_string: string | null }): string {
  const parts = [l.description, l.navigation_hint].filter(Boolean) as string[]
  if (l.tier === 'prefilled_search') parts.push('Opens a search already filled in')
  let note = parts.join('. ')
  if (note && !note.endsWith('.')) note += '.'
  if (l.paste_string) note += ` Copy \`${l.paste_string}\`.`
  return note
}

// --- the print memo ----------------------------------------------------------------
//
// The PDF is generated from the export template, not the screen: plain
// typographic hierarchy, black on white, URLs printed after their links,
// breaks where a paged document breaks. A research memo, not a screenshot.

function hx(v: unknown): string {
  return String(v ?? '').split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;')
}

const MEMO_CSS = `
  @page { margin: 20mm; }
  body { font: 11pt/1.5 Georgia, 'Times New Roman', serif; color: #000; background: #fff; margin: 0; }
  h1 { font-size: 17pt; line-height: 1.2; margin: 0; }
  .verdict { font-size: 12pt; margin: 8pt 0 2pt; }
  .meta { font-size: 9pt; color: #333; margin: 0 0 6pt; }
  h2 { font-size: 12.5pt; border-bottom: 1pt solid #000; padding-bottom: 2pt; margin: 16pt 0 6pt; break-after: avoid; }
  h3 { font-size: 11pt; margin: 10pt 0 3pt; break-after: avoid; }
  ul { margin: 3pt 0; padding-left: 14pt; }
  li { margin: 2pt 0; break-inside: avoid; }
  .src { font-size: 9pt; color: #333; }
  .why { margin: 3pt 0; }
  a { color: #000; text-decoration: none; }
  a[href]::after { content: " (" attr(href) ")"; font-size: 8pt; color: #444; word-break: break-all; }
  .disclaimer { font-size: 9pt; color: #333; border-top: 1pt solid #000; margin-top: 16pt; padding-top: 6pt; }
`

export function toPrintHtml(resp: RightsResponse, params: QueryParams): string {
  const layerOf = (id: string) => resp.entity.layers.find((l) => l.layer_id === id)
  const out: string[] = []
  const w = (s: string) => out.push(s)
  const title = `${params.title}${params.artist ? ` — ${params.artist}` : ''}`

  w(`<!doctype html><html><head><meta charset="utf-8"><title>${hx(title)} — rights record</title><style>${MEMO_CSS}</style></head><body>`)
  w(`<h1>${hx(title)}</h1>`)
  w(`<p class="verdict"><strong>${hx(VERDICT_WORD[resp.overall_verdict].toUpperCase())}.</strong> ${hx(resp.overall_headline)}</p>`)
  w(`<p class="meta">${hx(params.jurisdiction)} · ${hx(params.intent)} · ${hx(confidenceLabel(resp.overall_confidence))} · researched ${hx(shortDate(resp.generated_at))} · ${hx(permalinkFor(params))}</p>`)

  w('<h2>Rights layers</h2>')
  for (const lv of resp.layer_verdicts) {
    w(`<h3>${hx(layerTitle(lv))} — ${hx(VERDICT_WORD[lv.verdict])}${lv.is_required ? '' : ' (not required for this purpose)'}</h3>`)
    w('<ul>')
    w(`<li>${hx(expiryLine(lv.determination))} · ${hx(confidenceLabel(lv.determination.confidence))}</li>`)
    w(`<li>${hx(lv.reasoning)}${lv.intent_note ? ' ' + hx(lv.intent_note) : ''}</li>`)
    if (lv.licensing_path) w(`<li>Licensing: ${hx(lv.licensing_path)}.${lv.cost_band ? ` ${hx(lv.cost_band)}.` : ''}</li>`)
    const tf = layerOf(lv.layer_id)?.term_facts
    if (tf) {
      for (const [key, label] of Object.entries(FACT_LABEL)) {
        const fact = (tf as unknown as Record<string, { value: unknown; confidence: string; reasoning: string | null; sources: { name: string; url: string | null; retrieved_at: string; excerpt: string | null }[] } | null>)[key]
        if (!fact) continue
        w(`<li>${hx(label)}: <strong>${hx(factValue(key, fact.value))}</strong> (${hx(fact.confidence)})${fact.reasoning ? ` — ${hx(fact.reasoning)}` : ''}<ul>`)
        for (const s of fact.sources) {
          const href = sourceHref(s as never)
          w(`<li class="src">${href ? `<a href="${hx(href)}">${hx(s.name)}</a>` : hx(s.name)}, retrieved ${hx(shortDate(s.retrieved_at))}${s.excerpt ? ` — “${hx(s.excerpt)}”` : ''}</li>`)
        }
        w('</ul></li>')
      }
    }
    w('</ul>')
  }

  if (resp.unresolved.length) {
    w(`<h2>Open questions — ${resp.unresolved.length}</h2>`)
    for (const q of resp.unresolved) {
      w(`<h3>${hx(q.question)} (effort: ${hx(EFFORT_LABEL[q.estimated_effort] ?? q.estimated_effort)})</h3>`)
      w(`<p class="why">${hx(q.why_it_matters)}</p>`)
      w('<ul>')
      w(`<li>If yes: ${hx(q.if_yes)}</li>`)
      w(`<li>If no: ${hx(q.if_no)}</li>`)
      if (q.search_terms.length) w(`<li>Search: ${q.search_terms.map((t) => hx(t)).join(' · ')}</li>`)
      for (const l of q.resolution_links) w(`<li><a href="${hx(l.url)}">${hx(l.source_name)}</a>${l.navigation_hint ? ` — ${hx(l.navigation_hint)}` : ''}</li>`)
      w('</ul>')
    }
  }

  if (resp.handoff_links.length) {
    w('<h2>Records</h2><ul>')
    for (const l of resp.handoff_links) {
      w(`<li><a href="${hx(l.url)}">${hx(l.source_name)}</a> — ${hx(linkNote(l).split('\`').join(''))}</li>`)
    }
    w('</ul>')
  }

  w(`<p class="disclaimer">${hx(resp.disclaimer)}</p>`)
  w('</body></html>')
  return out.join('\n')
}

// --- licensing requests -------------------------------------------------------------
//
// The open questions say exactly what to check and where; clearance says
// exactly what to send and to whom. A sync request is a standard form and
// publishers expect the same fields, so the record fills what it knows and
// leaves the production-specific parts as marked blanks. Sync and master
// use are separate negotiations, so a two-layer block gets two requests.

const INTENT_PRODUCTION: Record<string, string> = {
  documentary: 'a documentary',
  film_tv: 'a film / television production',
  social_video: 'an online video',
  podcast: 'a podcast',
  commercial: 'a commercial / advertisement',
  print: 'a print publication',
  game: 'a video game',
  education: 'an educational production',
  personal: 'a personal project',
  rerecord: 'a new recording we will produce ourselves',
}

const TERRITORY_NAME: Record<string, string> = { US: 'the United States', UK: 'the United Kingdom', EU: 'the European Union' }

const DURATION_PHRASE: Record<string, string> = {
  under_10s: 'under 10 seconds', s10_30: '10\u201330 seconds', s30_60: '30\u201360 seconds', over_60s: 'over one minute',
}

export function licenseRequest(resp: RightsResponse, params: QueryParams, layerId: string,
  enrichedParties?: { name: string; role: string }[]): string {
  const layer = resp.entity.layers.find((l) => l.layer_id === layerId)
  const writers = resp.entity.creators.map((c) => c.value).join(', ')
  const year = resp.entity.year?.value
  const isSync = layerId === 'composition'
  const parties = (enrichedParties ?? []).map((p) => p.name).join(', ')
  const to = parties || (isSync ? 'the publisher of record' : 'the label or current master owner')
  const kind = isSync ? 'synchronization license' : 'master use license'
  const subjectOf = isSync
    ? `the musical composition \u201c${params.title}\u201d${writers ? ` (written by ${writers}${year ? `, ${year}` : ''})` : ''}`
    : `the sound recording of \u201c${params.title}\u201d${params.artist ? ` by ${params.artist}` : ''}`
  const other = isSync
    ? `The specific recording in the cut${params.artist ? ` is by ${params.artist}` : ''} and its master is being licensed separately.`
    : 'The underlying composition is being licensed separately with the publisher.'
  const production = INTENT_PRODUCTION[params.intent] ?? 'a production'
  const duration = params.duration ? DURATION_PHRASE[params.duration] : '[DURATION OF USE]'
  return [
    `Subject: ${isSync ? 'Sync' : 'Master use'} license request \u2014 \u201c${params.title}\u201d${params.artist && !isSync ? ` (${params.artist})` : ''}`,
    '',
    `To ${to}:`,
    '',
    `I am seeking a ${kind} for ${subjectOf}.`,
    '',
    `Production: [PRODUCTION TITLE] \u2014 ${production}`,
    'Use: [HOW THE CUE IS USED \u2014 scene, background or featured]',
    `Duration of use: ${duration}`,
    `Territory: ${TERRITORY_NAME[params.jurisdiction] ?? params.jurisdiction} [or worldwide, if needed]`,
    'Term: [TERM \u2014 e.g. 10 years, or perpetuity]',
    'Media: [MEDIA \u2014 e.g. festivals, streaming, broadcast]',
    'Budget: [MUSIC BUDGET OR FEE OFFERED]',
    '',
    other,
    '',
    'Please let me know the fee and any conditions, or who currently administers these rights if they have moved.',
    '',
    '[NAME / PRODUCTION COMPANY / CONTACT]',
  ].join('\n')
}

// --- delivery ----------------------------------------------------------------------

export function downloadText(filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function safeFilename(s: string): string {
  return s.replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-').toLowerCase() || 'record'
}
