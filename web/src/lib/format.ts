// Presentation mappings only. Nothing here decides a rights question: the
// verdicts, determinations and confidences arrive from the API and are
// rendered as they are. docs/design-system.md §2 (stamps, ticks) and §4.

import type { Confidence, Determination, Intent, Jurisdiction, LinkTier, ResearchMethod, Source, Verdict } from '../types'

// --- stamps ↔ Verdict ---------------------------------------------------------

export const VERDICT_WORD: Record<Verdict, string> = {
  clear: 'Clear',
  clear_with_conditions: 'Clear — conditions',
  license_required: 'License required',
  restricted: 'Restricted',
  undetermined: 'Not determined',
}

// Tailwind color utility per verdict (tokens from index.css).
export const VERDICT_COLOR: Record<Verdict, string> = {
  clear: 'text-green',
  clear_with_conditions: 'text-green',
  license_required: 'text-violet',
  restricted: 'text-red',
  undetermined: 'text-ink',
}

export const VERDICT_UNDERLINE: Record<Verdict, string> = {
  clear: 'border-b-4 border-solid border-green',
  clear_with_conditions: 'border-b-4 border-solid border-green',
  license_required: 'border-b-4 border-solid border-violet',
  restricted: 'border-b-4 border-solid border-red',
  undetermined: 'border-b-2 border-dashed border-ink',
}

// --- confidence ↔ ticks ---------------------------------------------------------

export const TICKS: Record<Confidence, number> = { high: 4, medium: 3, low: 2, none: 1 }

export function confidenceLabel(c: Confidence): string {
  return c === 'none' ? 'no confidence' : `${c} confidence`
}

// --- controls ↔ Intent / Jurisdiction -------------------------------------------

export const INTENT_OPTIONS: { value: Intent; label: string }[] = [
  { value: 'film_tv', label: 'Documentary — distributed' },
  { value: 'commercial', label: 'Sample — commercial release' },
  { value: 'rerecord', label: 'New recording — you perform it' },
]
export const JURISDICTIONS: Jurisdiction[] = ['US', 'UK', 'EU']

export function intentContext(intent: Intent): string {
  return { film_tv: 'DOCUMENTARY', commercial: 'COMMERCIAL', rerecord: 'NEW RECORDING' }[intent as string] ?? intent.toUpperCase().replace('_', ' ')
}

// --- tags ---------------------------------------------------------------------

export const TIER_LABEL: Record<LinkTier, string> = {
  deep_link: 'Deep link',
  prefilled_search: 'Pre-filled search',
  guided_manual: 'Guided manual',
}

export const METHOD_LABEL: Record<ResearchMethod, string> = {
  rights_uri: 'Rights URI',
  direct_api: 'Direct API',
  parallel_search: 'Web search',
  parallel_task: 'Research task',
  parallel_extract: 'Extract',
  rules_engine: 'Rules',
  user_provided: 'Supplied',
}

export const EFFORT_LABEL: Record<string, string> = { minutes: 'Minutes', hours: 'Hours', specialist: 'Specialist' }

// --- evidence values ---------------------------------------------------------------

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "22 Aug 2026" from an ISO timestamp. */
export function shortDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** The mono expiry line under a stamp: EXPIRES 1 JAN 2029 / EXPIRED 1 JAN 2024 / —. */
export function expiryLine(det: Determination, now = new Date()): string {
  if (det.expiry_year == null) return det.status === 'undetermined' ? 'TERM NOT COMPUTED' : '—'
  const past = det.expiry_year <= now.getUTCFullYear()
  return `${past ? 'EXPIRED' : 'EXPIRES'} 1 JAN ${det.expiry_year}`
}

/** A human page for the API URLs the pipeline cites, when one is known. */
export function sourceHref(s: Source): string | null {
  if (!s.url) return null
  const mb = s.url.match(/musicbrainz\.org\/ws\/2\/(work|recording|artist|release)\/([0-9a-f-]{36})/)
  if (mb) return `https://musicbrainz.org/${mb[1]}/${mb[2]}`
  const wd = s.url.match(/wikidata\.org\/w\/api\.php\?.*ids=(Q\d+)/)
  if (wd) return `https://www.wikidata.org/wiki/${wd[1]}`
  const wdsearch = s.url.match(/wikidata\.org\/w\/api\.php\?.*action=wbsearchentities/)
  if (wdsearch) return 'https://www.wikidata.org/'
  return s.url
}

export function pct(n: number | null): string {
  return n == null ? '—' : `${Number.isInteger(n) ? n : n.toFixed(1)}%`
}

/** Title and artist from the raw query ("West End Blues — Louis Armstrong"). */
export function splitQuery(raw: string): { title: string; artist: string | null } {
  for (const sep of [' — ', ' – ', ' - ', ' by ']) {
    const i = raw.indexOf(sep)
    if (i > 0) return { title: raw.slice(0, i).trim(), artist: raw.slice(i + sep.length).trim() || null }
  }
  return { title: raw.trim(), artist: null }
}

/** Fact eyebrows for term facts (the schema field → what a person calls it). */
export const FACT_LABEL: Record<string, string> = {
  first_publication_year: 'First publication',
  renewal_filed: 'Year-28 renewal',
  author_death_year: 'Last surviving author',
  recording_first_published_year: 'Recording first published',
}

export function factValue(key: string, value: unknown): string {
  if (key === 'renewal_filed') return value ? 'Renewed' : 'Not renewed'
  return String(value)
}
