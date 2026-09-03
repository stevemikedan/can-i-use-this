// Presentation mappings only. Nothing here decides a rights question: the
// verdicts, determinations and confidences arrive from the API and are
// rendered as they are. docs/design-system.md §2 (stamps, ticks) and §4.

import type { QueryParams, Confidence, Determination, Intent, Jurisdiction, LinkTier, ResearchMethod, Source, Verdict } from '../types'

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

/** The distribution context: sets the cost band and licensing path. One
 *  select, because nine buttons don't fit a row. */
export const CONTEXT_OPTIONS: { value: Intent; label: string }[] = [
  { value: 'documentary', label: 'Documentary' },
  { value: 'film_tv', label: 'Film or TV' },
  { value: 'social_video', label: 'Social video' },
  { value: 'podcast', label: 'Podcast' },
  { value: 'commercial', label: 'Commercial or advertising' },
  { value: 'print', label: 'Print' },
  { value: 'game', label: 'Game' },
  { value: 'education', label: 'Education' },
  { value: 'personal', label: 'Personal' },
]
export const DEFAULT_CONTEXT: Intent = 'documentary'

export const DURATION_OPTIONS: { value: NonNullable<QueryParams['duration']>; label: string }[] = [
  { value: 'under_10s', label: 'Under 10s' },
  { value: 's10_30', label: '10–30s' },
  { value: 's30_60', label: '30–60s' },
  { value: 'over_60s', label: 'Over a minute' },
]

/** The misconception the duration control exists to correct. */
export const NO_SAFE_HARBOR =
  'US copyright has no short-use exception. No duration is safe, and the verdict does not change. ' +
  'Length affects what a license costs, not whether you need one. Fair use can apply to short uses, ' +
  'but it is a defense a court weighs after the fact, not a rule to rely on beforehand.'

export const JURISDICTIONS: Jurisdiction[] = ['US', 'UK', 'EU']

export function intentContext(intent: Intent): string {
  return {
    documentary: 'DOCUMENTARY', film_tv: 'FILM / TV', social_video: 'SOCIAL VIDEO', podcast: 'PODCAST',
    commercial: 'COMMERCIAL', print: 'PRINT', game: 'GAME', education: 'EDUCATION',
    personal: 'PERSONAL', rerecord: 'NEW RECORDING',
  }[intent as string] ?? intent.toUpperCase().replace('_', ' ')
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
  user_provided: 'Asserted by you',
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

/** Why a layer is blocked, at a glance — for the cue table's blocking column. */
export const BLOCK_REASON: Record<string, string> = {
  us_renewal_unknown: 'renewal unknown',
  life_plus_70_writers_uncorroborated: 'writer list unconfirmed',
  recording_pub_year_unconfirmed: 'release date unconfirmed',
  us_publication_year_unknown: 'publication year unknown',
  public_domain_withheld_low_confidence: 'evidence too weak for public domain',
  uk_death_year_unknown: 'death year unknown',
  eu_death_year_unknown: 'death year unknown',
}

export function factValue(key: string, value: unknown): string {
  if (key === 'renewal_filed') return value ? 'Renewed' : 'Not renewed'
  return String(value)
}
