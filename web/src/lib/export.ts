// Export — CSV, Markdown, and helpers. One column schema for a single result
// and for cue-sheet rows, so a spreadsheet built one search at a time and a
// pasted cue list land in the same columns. The permalink re-opens (re-runs)
// the record; the researched date is there because rights lists go stale.
import type { Intent, Jurisdiction, LayerVerdict, QueryParams, RightsResponse, Verdict } from '../types'
import { EFFORT_LABEL, FACT_LABEL, TIER_LABEL, VERDICT_WORD, confidenceLabel, expiryLine, factValue, shortDate, sourceHref, splitQuery } from './format'

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
      for (const l of q.resolution_links) push(`- [${l.source_name}](${l.url}) (${TIER_LABEL[l.tier]})${l.navigation_hint ? ` — ${l.navigation_hint}` : ''}`)
    }
  }
  if (resp.handoff_links.length) {
    push()
    push('## Records')
    for (const l of resp.handoff_links) {
      push(`- [${l.source_name}](${l.url}) (${TIER_LABEL[l.tier]}) — ${l.description}${l.paste_string ? ` Paste: \`${l.paste_string}\`` : ''}`)
    }
  }
  push()
  push(`---`)
  push()
  push(`_${resp.disclaimer}_`)
  push()
  return lines.join('\n')
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
