// The parts of schemas.RightsResponse the interface reads. Field names match
// the JSON the API returns; nothing is derived here.

export type Verdict = 'clear' | 'clear_with_conditions' | 'license_required' | 'restricted' | 'undetermined'
export type Confidence = 'high' | 'medium' | 'low' | 'none'
export type Jurisdiction = 'US' | 'UK' | 'EU'
export type Intent = 'film_tv' | 'commercial' | 'rerecord' | 'personal' | 'education' | 'social_video' | 'podcast' | 'game' | 'print'
export type LinkTier = 'deep_link' | 'prefilled_search' | 'guided_manual'
export type DeterminationStatus = 'public_domain' | 'protected' | 'no_copyright_other_restrictions' | 'undetermined'
export type ResearchMethod = 'rights_uri' | 'direct_api' | 'parallel_task' | 'parallel_search' | 'parallel_extract' | 'rules_engine' | 'user_provided'

export interface Source {
  name: string
  url: string | null
  method: ResearchMethod
  retrieved_at: string
  excerpt: string | null
  authoritative: boolean
}

export interface ResearchedFact<T = unknown> {
  value: T
  confidence: Confidence
  sources: Source[]
  reasoning: string | null
  conflicting_values: string[]
}

export interface Identifier {
  scheme: string
  value: string
  layer_id: string
  confidence: Confidence
  is_primary: boolean
}

export interface RightsHolder {
  name: ResearchedFact<string>
  role: string
  is_administrator: boolean
  share_percent: number | null
  territory: string | null
  contact_path: string | null
  enforcement_posture: string
}

export interface ClearanceProfile {
  party_count: number | null
  unclaimed_share_percent: number | null
  is_one_stop: boolean | null
  difficulty: string
  difficulty_reasoning: string | null
}

export interface TermFacts {
  author_death_year: ResearchedFact<number> | null
  first_publication_year: ResearchedFact<number> | null
  renewal_filed: ResearchedFact<boolean> | null
  recording_first_published_year: ResearchedFact<number> | null
  recording_date_basis: string | null
  writer_list_corroborated: boolean
}

export interface RightsLayer {
  layer_id: string
  kind: string
  label: string
  identifiers: Identifier[]
  holders: RightsHolder[]
  term_facts: TermFacts
  clearance: ClearanceProfile
}

export interface Determination {
  layer_id: string
  jurisdiction: Jurisdiction
  status: DeterminationStatus
  expiry_year: number | null
  rule_id: string
  rule_explanation: string
  confidence: Confidence
  depends_on_facts: string[]
  blocked_by: string[]
}

export interface LayerVerdict {
  layer_id: string
  layer_label: string
  verdict: Verdict
  is_required: boolean
  headline: string
  reasoning: string
  determination: Determination
  holders: RightsHolder[]
  clearance: ClearanceProfile
  licensing_path: string | null
  cost_band: string | null
  intent_note: string | null
}

export interface HandoffLink {
  source_name: string
  url: string
  tier: LinkTier
  purpose: 'verify' | 'resolve' | 'license' | 'alternative'
  description: string
  paste_string: string | null
  navigation_hint: string | null
}

export interface UnresolvedQuestion {
  question_id: string
  question: string
  why_it_matters: string
  if_yes: string
  if_no: string
  affects_layer_ids: string[]
  resolution_links: HandoffLink[]
  search_terms: string[]
  estimated_effort: 'minutes' | 'hours' | 'specialist'
}

export interface Alternative {
  title: string
  creator: string | null
  why_similar: string
  status: string
  license_terms: string | null
  url: string | null
}

export interface Candidate {
  label: string
  disambiguator: string
  identifiers: Identifier[]
  likelihood: Confidence
}

export interface ResolvedEntity {
  canonical_title: string
  asset_type: string
  creators: ResearchedFact<string>[]
  year: ResearchedFact<number> | null
  layers: RightsLayer[]
  resolution_confidence: Confidence
  alternate_candidates: Candidate[]
}

export interface AssetQuery {
  raw_input: string
  intent: Intent
  jurisdiction: Jurisdiction
  asset_type_hint: string | null
}

export interface RightsResponse {
  query: AssetQuery
  entity: ResolvedEntity
  stop_for_disambiguation: boolean
  overall_verdict: Verdict
  overall_headline: string
  overall_confidence: Confidence
  layer_verdicts: LayerVerdict[]
  all_determinations: Determination[]
  unresolved: UnresolvedQuestion[]
  alternatives: Alternative[]
  handoff_links: HandoffLink[]
  boundary_note: string | null
  disclaimer: string
  generated_at: string
  served_from_cache: boolean
}

export interface PipelineEvent {
  stage: 'classify' | 'identify' | 'decompose' | 'research' | 'rules' | 'compare' | 'assemble'
  status: 'started' | 'progress' | 'complete' | 'failed' | 'skipped' | 'timeout'
  message: string
  detail: string | null
  sources_consulted: number
  elapsed_ms: number
  degraded: boolean
  error_message: string | null
  partial: Record<string, unknown> | null
}

export interface QueryParams {
  title: string
  artist?: string
  intent: Intent
  jurisdiction: Jurisdiction
}
