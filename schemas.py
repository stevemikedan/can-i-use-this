"""
Rights determination pipeline — canonical schemas. v2.

Supersedes schemas.py. Changes from v1 are listed at the bottom of this
docstring.

REQUIREMENTS
============
Python 3.11+ and Pydantic 2.x. v1 used PEP 695 generic syntax
(`class ResearchedFact[T]`) which requires Python 3.12 AND recent Pydantic;
v2 uses `Generic[T]` instead, which works on 3.11 and every Pydantic 2.x.
Do not "modernize" it back — the environment is not guaranteed.

DESIGN NOTES (read before changing anything here)
=================================================

1. THE LAYER PROBLEM
   A single user query does not map to a single copyrightable work. It maps to
   a HIERARCHY of separate works, each with distinct owners, distinct
   identifiers, and potentially DIFFERENT VERDICTS.

       "Bohemian Rhapsody"
         └── composition        (Mercury; publisher-controlled; ISWC; MLC)
         └── 1975 master        (label-controlled; ISRC; MusicBrainz)

       "The Metamorphosis"
         └── text work          (Kafka, d. 1924 — public domain)
         └── translation        (translator's own term — often protected)

   A composition can be public domain while every recording of it is
   protected, and vice versa. This is the most common source of wrong answers
   in this domain. Handling it correctly IS the product.

2. THE VERDICT IS THREE-DIMENSIONAL
       verdict = f(layer, jurisdiction, intent)
   Never store a single scalar verdict. Determination is computed per layer
   per jurisdiction, then filtered by intent. The UI's toggles re-read this
   matrix; they do not re-query.

3. IDENTIFIERS ATTACH TO LAYERS, NOT TO THE QUERY
   Identifiers are a LIST, not a dict: the same scheme can yield multiple
   candidates, each belongs to one layer, each carries its own confidence.

4. EVERY ASSERTED FACT CARRIES PROVENANCE
   A ResearchedFact bundles value + sources + confidence. If it can't be
   sourced it becomes an UnresolvedQuestion. There is no third option.

5. UNKNOWNS ARE FIRST-CLASS OUTPUT
   UnresolvedQuestion is a product feature, not an error type.

CHANGES IN v2
=============
- Generic[T] instead of PEP 695 syntax (portability)
- Added ClearanceProfile: party count, unclaimed shares, one-stop detection
- Added explicit VERDICT_ORDER and STATUS_TO_VERDICT mapping constants
- Added REQUIRED_LAYERS table so the roll-up rule is data, not prose
- Added ProcessorTier to make latency budget explicit at the call site
- Removed AssetType.IMAGE from SUPPORTED_TYPES (cut from scope)
- Added stop_for_disambiguation flag to RightsResponse
- Added failure/timeout fields to PipelineEvent
- Tightened Source.excerpt to 200 chars
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, HttpUrl

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AssetType(str, Enum):
    MUSIC = "music"
    TEXT = "text"
    FILM = "film"
    # Recognized but NOT researched. Routed to a graceful boundary message.
    # Being explicit about the edge reads as rigor; faking coverage does not.
    IMAGE = "image"
    FONT = "font"
    CHARACTER = "character"
    FOOTAGE = "footage"
    TRADEMARK = "trademark"
    UNKNOWN = "unknown"


# IMAGE is deliberately absent — cut from scope. See PROJECT.md §2.
SUPPORTED_TYPES: frozenset[AssetType] = frozenset(
    {AssetType.MUSIC, AssetType.TEXT, AssetType.FILM}
)


class RightsLayerKind(str, Enum):
    COMPOSITION = "composition"
    SOUND_RECORDING = "sound_recording"
    TEXT_WORK = "text_work"
    EDITION = "edition"
    TRANSLATION = "translation"
    AUDIOVISUAL_WORK = "audiovisual_work"
    EMBEDDED_ELEMENT = "embedded_element"


class Jurisdiction(str, Enum):
    US = "US"
    UK = "UK"
    EU = "EU"
    OTHER = "other"


class Intent(str, Enum):
    PERSONAL = "personal"
    EDUCATION = "education"
    SOCIAL_VIDEO = "social_video"
    PODCAST = "podcast"
    COMMERCIAL = "commercial"
    FILM_TV = "film_tv"
    # The primary audience. Shares REQUIRED_LAYERS with film/TV but not
    # cost bands: festival-only vs broadcast rates differ, and fair use
    # plays a larger role for incidental captures.
    DOCUMENTARY = "documentary"
    PRINT = "print"
    GAME = "game"
    # Music-specific: user intends to commission a re-recording rather than
    # license the original master. Removes the master use license from the
    # equation entirely — US mechanical is compulsory, sync is not.
    RERECORD = "rerecord"


class Verdict(str, Enum):
    CLEAR = "clear"
    CLEAR_WITH_CONDITIONS = "clear_with_conditions"
    LICENSE_REQUIRED = "license_required"
    RESTRICTED = "restricted"
    UNDETERMINED = "undetermined"


# Restrictiveness ordering for the conservative roll-up.
# UNDETERMINED is MOST restrictive: if we don't know, we don't say clear.
VERDICT_ORDER: dict[Verdict, int] = {
    Verdict.CLEAR: 0,
    Verdict.CLEAR_WITH_CONDITIONS: 1,
    Verdict.LICENSE_REQUIRED: 2,
    Verdict.RESTRICTED: 3,
    Verdict.UNDETERMINED: 4,
}


class DeterminationStatus(str, Enum):
    PUBLIC_DOMAIN = "public_domain"
    PROTECTED = "protected"
    NO_COPYRIGHT_OTHER_RESTRICTIONS = "no_copyright_other_restrictions"
    UNDETERMINED = "undetermined"


class Confidence(str, Enum):
    HIGH = "high"       # multiple independent authoritative sources agree
    MEDIUM = "medium"   # single authoritative source, or weak agreement
    LOW = "low"         # inference, or sources conflict
    NONE = "none"       # asserted by no source


class ResearchMethod(str, Enum):
    RIGHTS_URI = "rights_uri"           # tier 1
    DIRECT_API = "direct_api"           # tier 2
    PARALLEL_TASK = "parallel_task"     # tier 3
    PARALLEL_SEARCH = "parallel_search"
    PARALLEL_EXTRACT = "parallel_extract"
    RULES_ENGINE = "rules_engine"
    USER_PROVIDED = "user_provided"


class ProcessorTier(str, Enum):
    """
    Parallel processor selection. Encoded in the schema so latency budget is
    visible at the call site rather than buried in config.

    NEVER use pro/ultra in the request path — they run minutes to hours.
    See PROJECT.md §4.6.
    """

    LITE = "lite"
    BASE_FAST = "base-fast"
    CORE_FAST = "core-fast"
    CORE = "core"


class LinkTier(str, Enum):
    DEEP_LINK = "deep_link"
    PREFILLED_SEARCH = "prefilled_search"
    GUIDED_MANUAL = "guided_manual"


class RecordingDateBasis(str, Enum):
    """
    Provenance of a sound recording's date. Determines whether the MMA /
    CLASSICS schedule may be applied confidently.

    Established by the Aug 2026 spike: MusicBrainz `first-release-date` is the
    earliest release ON FILE, which is frequently a later reissue. Applying the
    CLASSICS schedule to it silently produces decades-wrong expiry dates.
    """

    DATED_PERFORMANCE = "dated_performance"      # MB performance relation. Trustworthy.
    LABEL_MATRIX = "label_matrix"                # Session/matrix data. Trustworthy.
    RESEARCHED = "researched"                    # Tier 3 (DAHR, discographies). Trustworthy.
    FIRST_RELEASE_DATE = "first_release_date"    # MAY BE A REISSUE. Never confident.
    UNKNOWN = "unknown"


# Only these bases may drive a confident sound-recording determination.
# Anything else must emit an UnresolvedQuestion for first publication year.
TRUSTWORTHY_DATE_BASES: frozenset[RecordingDateBasis] = frozenset({
    RecordingDateBasis.DATED_PERFORMANCE,
    RecordingDateBasis.LABEL_MATRIX,
    RecordingDateBasis.RESEARCHED,
})


# ---------------------------------------------------------------------------
# Roll-up rules — data, not prose
# ---------------------------------------------------------------------------

# Which layers must be clear for the overall verdict to be clear.
# Layers not listed still get determinations and still appear in the response;
# they are simply excluded from the roll-up.
REQUIRED_LAYERS: dict[tuple[AssetType, Intent], frozenset[RightsLayerKind]] = {
    (AssetType.MUSIC, Intent.FILM_TV): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.DOCUMENTARY): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.COMMERCIAL): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.SOCIAL_VIDEO): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.PODCAST): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.GAME): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.PERSONAL): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    (AssetType.MUSIC, Intent.EDUCATION): frozenset(
        {RightsLayerKind.COMPOSITION, RightsLayerKind.SOUND_RECORDING}
    ),
    # Re-recording removes the master use license from the equation.
    (AssetType.MUSIC, Intent.RERECORD): frozenset({RightsLayerKind.COMPOSITION}),
    # Printing lyrics or sheet music never touches the master.
    (AssetType.MUSIC, Intent.PRINT): frozenset({RightsLayerKind.COMPOSITION}),
    (AssetType.TEXT, Intent.PRINT): frozenset({RightsLayerKind.TEXT_WORK}),
    (AssetType.TEXT, Intent.COMMERCIAL): frozenset({RightsLayerKind.TEXT_WORK}),
    (AssetType.TEXT, Intent.PERSONAL): frozenset({RightsLayerKind.TEXT_WORK}),
    (AssetType.TEXT, Intent.EDUCATION): frozenset({RightsLayerKind.TEXT_WORK}),
    (AssetType.FILM, Intent.FILM_TV): frozenset({RightsLayerKind.AUDIOVISUAL_WORK}),
    (AssetType.FILM, Intent.COMMERCIAL): frozenset({RightsLayerKind.AUDIOVISUAL_WORK}),
}

# Fallback when the (type, intent) pair isn't in the table: every layer is
# required. Conservative by design.
DEFAULT_ALL_LAYERS_REQUIRED = True

# NOTE: TRANSLATION and EDITION are added to the required set dynamically when
# the resolved entity actually contains one — you only need the translation
# you're using. Implement in the rules engine, not here.


def map_status_to_verdict(
    status: DeterminationStatus,
    *,
    has_other_restrictions: bool = False,
    license_covers_intent: bool = False,
    has_unclaimed_shares: bool = False,
    holder_refuses_use_class: bool = False,
    licensing_path_exists: bool = True,
) -> Verdict:
    """
    The single authoritative status -> verdict mapping. See PROJECT.md §4.1.

    Kept as a plain function, not model logic, so it is unit-testable in
    isolation and so the rules engine has exactly one place to change.
    """
    if status is DeterminationStatus.UNDETERMINED:
        return Verdict.UNDETERMINED
    if status is DeterminationStatus.NO_COPYRIGHT_OTHER_RESTRICTIONS:
        return Verdict.CLEAR_WITH_CONDITIONS
    if status is DeterminationStatus.PUBLIC_DOMAIN:
        return (
            Verdict.CLEAR_WITH_CONDITIONS if has_other_restrictions else Verdict.CLEAR
        )
    # PROTECTED
    if has_unclaimed_shares or holder_refuses_use_class:
        return Verdict.RESTRICTED
    if license_covers_intent:
        return Verdict.CLEAR_WITH_CONDITIONS
    if licensing_path_exists:
        return Verdict.LICENSE_REQUIRED
    return Verdict.RESTRICTED


# ---------------------------------------------------------------------------
# Provenance primitives
# ---------------------------------------------------------------------------


class Source(BaseModel):
    name: str = Field(..., description="Human name, e.g. 'MusicBrainz'")
    url: HttpUrl | None = None
    method: ResearchMethod
    retrieved_at: datetime
    excerpt: str | None = Field(
        None,
        max_length=200,
        description="Short supporting excerpt. Evidence, not reproduction — "
                    "keep it well under the limit.",
    )
    authoritative: bool = Field(
        False,
        description="True for rights registries and official records (MLC, "
                    "Copyright Office, HathiTrust). False for secondary or "
                    "aggregated sources.",
    )


class ResearchedFact(BaseModel, Generic[T]):
    """A value that came from somewhere. Never store bare values."""

    value: T
    confidence: Confidence
    sources: list[Source] = Field(default_factory=list)
    reasoning: str | None = None
    conflicting_values: list[str] = Field(
        default_factory=list,
        description="Other values sources asserted. Surfacing disagreement is "
                    "a feature.",
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class Identifier(BaseModel):
    scheme: str = Field(
        ...,
        description="wikidata | musicbrainz_work | musicbrainz_recording | "
                    "isrc | iswc | ipi | mlc_work | isbn | oclc | lccn | "
                    "openlibrary | hathitrust | spotify_track | discogs | imdb",
    )
    value: str
    layer_id: str
    confidence: Confidence
    source: Source | None = None
    is_primary: bool = Field(
        False,
        description="Preferred identifier for this scheme+layer. Primary "
                    "identifiers across all layers form the cache key.",
    )


class Candidate(BaseModel):
    label: str = Field(..., description="e.g. 'Queen — 1975 studio recording'")
    disambiguator: str = Field(..., description="e.g. 'A Night at the Opera'")
    identifiers: list[Identifier] = Field(default_factory=list)
    likelihood: Confidence


# ---------------------------------------------------------------------------
# Rights structure
# ---------------------------------------------------------------------------


class RightsHolder(BaseModel):
    name: ResearchedFact[str]
    role: str = Field(
        ...,
        description="publisher | administrator | label | author | translator | "
                    "estate | agency | museum",
    )
    is_administrator: bool = Field(
        False,
        description="MLC distinguishes original publisher from administrator. "
                    "The ADMINISTRATOR is who actually licenses and answers "
                    "the phone. Surfacing the publisher alone sends users to "
                    "the wrong door.",
    )
    share_percent: float | None = Field(None, ge=0, le=100)
    territory: str | None = None
    contact_path: str | None = Field(
        None,
        description="How to reach them for licensing. Usually requires Tier 3 "
                    "research — no database publishes sync contacts.",
    )
    enforcement_posture: Literal[
        "aggressive", "standard", "permissive", "unknown"
    ] = "unknown"
    enforcement_evidence: list[Source] = Field(default_factory=list)


class ClearanceProfile(BaseModel):
    """
    How hard this layer is to actually clear — separate from whether it's
    protected. Drives the licensing-path output.

    No database publishes sync licensing contacts or prices: sync is
    negotiated one-off and is not collectively administered by anyone. What
    IS available is the shape of the negotiation, which is most of the value.
    """

    party_count: int | None = Field(
        None, description="Number of distinct rights holders who must consent."
    )
    unclaimed_share_percent: float | None = Field(
        None,
        ge=0,
        le=100,
        description="MLC publishes unmatched ownership percentage. Any "
                    "unclaimed share means the work CANNOT be fully cleared "
                    "at any price — an orphan dead-end worth surfacing loudly.",
    )
    is_one_stop: ResearchedFact[bool] | None = Field(
        None,
        description="Same entity controls both publishing and master. "
                    "Dramatically faster and cheaper; the single most useful "
                    "signal for an indie production.",
    )
    difficulty: Literal["easy", "moderate", "hard", "likely_impossible"] = "moderate"
    difficulty_reasoning: str | None = None


class TermFacts(BaseModel):
    """
    Determinative inputs to the rules engine. All optional — an unknown here
    becomes an UnresolvedQuestion rather than a guess.
    """

    author_death_year: ResearchedFact[int] | None = None
    first_publication_year: ResearchedFact[int] | None = None
    first_publication_country: ResearchedFact[str] | None = None
    creation_year: ResearchedFact[int] | None = None
    copyright_notice_present: ResearchedFact[bool] | None = None
    renewal_filed: ResearchedFact[bool] | None = Field(
        None,
        description="Decisive for US works published 1931-1963 (window rolls "
                    "forward each 1 January as the 95-year cliff advances). "
                    "SPIKE FINDING: 4 of 6 real test cases landed here — this "
                    "is most of the 20th-century songbook, not an edge case. "
                    "Treat as a TIER 3 RESEARCH TASK (Stanford Copyright "
                    "Renewal Database, Copyright Office records, Catalog of "
                    "Copyright Entries) before emitting an UnresolvedQuestion. "
                    "Automatic 'undetermined' here makes the product useless "
                    "for the majority of real queries.",
    )
    is_work_for_hire: ResearchedFact[bool] | None = None
    is_anonymous_or_pseudonymous: ResearchedFact[bool] | None = None
    is_derivative: ResearchedFact[bool] | None = None
    underlying_work_ref: str | None = None
    # Music-specific: drives the MMA/CLASSICS schedule, which is fully
    # deterministic given only this one field.
    recording_first_published_year: ResearchedFact[int] | None = None
    recording_fixed_before_feb_1972: ResearchedFact[bool] | None = None

    # SPIKE FINDING (Aug 2026): where the recording year came from matters
    # more than the year itself. MusicBrainz first-release-date returned a
    # 1975 reissue for a 1928 session — a 42-year error on the single fact
    # the entire CLASSICS calculation depends on.
    #
    # Only DATED_PERFORMANCE may drive a confident determination.
    # FIRST_RELEASE_DATE must produce an UnresolvedQuestion instead.
    recording_date_basis: RecordingDateBasis | None = None

    # SPIKE FINDING: MusicBrainz listed King Oliver but not Clarence Williams
    # for "West End Blues". life+70 runs from the LAST SURVIVING author, so an
    # incomplete writer list silently produces a wrong EU/UK expiry. US terms
    # are unaffected (95-year rule ignores death dates).
    #
    # False => life_plus_70 determinations are LOW confidence at best and
    # should carry an UnresolvedQuestion.
    writer_list_corroborated: bool = False


class ClaimedStatus(BaseModel):
    """
    What a third party asserts. Kept separate from our own Determination so
    both can be shown side by side.

    Archives over- and under-claim routinely: museums assert copyright over
    faithful reproductions of public domain 2D works (Bridgeman v. Corel), and
    'Copyright Undetermined' is applied defensively at scale because
    determination is expensive and caution is free for the institution.
    """

    claimant: str
    rights_uri: str | None = Field(
        None, description="RightsStatements.org or Creative Commons URI."
    )
    statement_label: str
    source: Source
    applies_to_layer_id: str | None = None


class RightsLayer(BaseModel):
    """One copyrightable stratum. THE central abstraction."""

    layer_id: str
    kind: RightsLayerKind
    label: str = Field(..., description="e.g. 'Composition (1939)'")
    identifiers: list[Identifier] = Field(default_factory=list)
    holders: list[RightsHolder] = Field(default_factory=list)
    term_facts: TermFacts = Field(default_factory=TermFacts)
    clearance: ClearanceProfile = Field(default_factory=ClearanceProfile)
    claimed_statuses: list[ClaimedStatus] = Field(default_factory=list)
    existing_license: ResearchedFact[str] | None = None


# ---------------------------------------------------------------------------
# Determination
# ---------------------------------------------------------------------------


class Determination(BaseModel):
    """
    One cell of the (layer x jurisdiction) matrix.

    Produced by the deterministic rules engine, NEVER by the model. rule_id
    and rule_explanation make the reasoning auditable and unit-testable
    against known-answer works.
    """

    layer_id: str
    jurisdiction: Jurisdiction
    status: DeterminationStatus
    expiry_year: int | None = None
    rule_id: str = Field(
        ...,
        description="Must match a rule_id emitted by rules/. Canonical set: "
                    "us_sr_pre_1923, us_sr_mma_1923_1946, us_sr_mma_1947_1956, "
                    "us_sr_mma_1957_1972, us_published_expired, "
                    "us_renewal_unknown, us_renewal_not_filed, "
                    "us_renewal_filed, us_published_1964_1977, "
                    "us_published_post_1978, eu_life_plus_70, uk_life_plus_70. "
                    "rules/ is authoritative — never invent a rule_id here.",
    )
    rule_explanation: str
    confidence: Confidence
    depends_on_facts: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(
        default_factory=list, description="UnresolvedQuestion ids."
    )


class DisagreementNote(BaseModel):
    """
    Generated when our determination differs from a ClaimedStatus.
    Never silently override an institution — always show both, with reasoning.
    """

    layer_id: str
    claimed: ClaimedStatus
    our_status: DeterminationStatus
    explanation: str
    likely_cause: Literal[
        "institutional_caution",
        "reproduction_copyfraud",
        "jurisdiction_mismatch",
        "digitization_layer_rights",
        "stale_record",
        "we_may_be_wrong",
    ]
    confidence: Confidence


class HandoffLink(BaseModel):
    source_name: str
    url: HttpUrl
    tier: LinkTier
    purpose: Literal["verify", "resolve", "license", "alternative"]
    description: str
    paste_string: str | None = Field(
        None, description="For GUIDED_MANUAL: exact text to search for."
    )
    navigation_hint: str | None = Field(
        None, description="e.g. 'Renewal records, 1955-1963 drawer'."
    )


class UnresolvedQuestion(BaseModel):
    """
    Something research could not settle. A first-class output, not an error.
    Must carry enough detail for a human to finish the job in minutes.
    """

    question_id: str
    question: str
    why_it_matters: str
    if_yes: str
    if_no: str
    affects_layer_ids: list[str] = Field(default_factory=list)
    resolution_links: list[HandoffLink] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    estimated_effort: Literal["minutes", "hours", "specialist"] = "minutes"


class Alternative(BaseModel):
    """
    A substitute that does the same job without the rights problem.

    v2: these are CURATED STATIC entries per asset type, not researched at
    runtime. Same user value, no latency or cost. See PROJECT.md §2.
    """

    title: str
    creator: str | None = None
    why_similar: str
    status: Literal["public_domain", "cc_licensed", "royalty_free", "licensable"]
    license_terms: str | None = None
    url: HttpUrl | None = None
    source: Source | None = None


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------


class Duration(str, Enum):
    """
    How much of the work is used. Deliberately NOT an input to any
    determination: US copyright has no short-use safe harbor (no seven
    seconds, no eight bars; Bridgeport went as far as "get a license or do
    not sample"). Length scales what a license costs, never whether one is
    needed - the control exists to correct that misconception, and the cost
    bands are the only thing it touches.
    """

    UNDER_10S = "under_10s"
    S10_TO_30 = "s10_30"
    S30_TO_60 = "s30_60"
    OVER_60S = "over_60s"


class UserAnswer(BaseModel):
    """
    A user's answer to an UnresolvedQuestion, supplied on resubmission.

    The attestation is what turns an assertion into a finding: for "renewed"
    an RE number and date; for "not renewed" what was searched and where.
    Confidence policy — MEDIUM ceiling with an attestation, LOW without,
    authoritative=False always — lives in pipeline/user_facts.py.
    """

    answer: bool
    attestation: str | None = Field(
        None, max_length=300,
        description="The source behind the answer: an RE number and date, or "
                    "what was searched and what came back.")


class AssetQuery(BaseModel):
    raw_input: str
    intent: Intent = Intent.PERSONAL
    jurisdiction: Jurisdiction = Jurisdiction.US
    asset_type_hint: AssetType | None = None
    disambiguation_choice: str | None = Field(
        None, description="Set on resubmission after the user picks a Candidate."
    )
    user_answers: dict[str, UserAnswer] = Field(
        default_factory=dict,
        description="question_id -> the user's answer, on a re-run after they "
                    "settle an open question. See pipeline/user_facts.py.")
    duration: Duration | None = Field(
        None, description="Length of the use. Scales cost bands only; never a "
                          "determination input (no short-use safe harbor exists).")


class ResolvedEntity(BaseModel):
    canonical_title: str
    asset_type: AssetType
    creators: list[ResearchedFact[str]] = Field(default_factory=list)
    year: ResearchedFact[int] | None = None
    layers: list[RightsLayer] = Field(default_factory=list)
    resolution_confidence: Confidence
    alternate_candidates: list[Candidate] = Field(default_factory=list)


class LayerVerdict(BaseModel):
    layer_id: str
    layer_label: str
    verdict: Verdict
    is_required: bool = Field(
        ...,
        description="Whether this layer counts toward overall_verdict for the "
                    "requested intent. See REQUIRED_LAYERS.",
    )
    headline: str = Field(..., max_length=120)
    reasoning: str
    determination: Determination
    holders: list[RightsHolder] = Field(default_factory=list)
    clearance: ClearanceProfile = Field(default_factory=ClearanceProfile)
    licensing_path: str | None = None
    cost_band: str | None = Field(
        None,
        description="Ranges only, e.g. '$500-$5,000 for indie film sync'. "
                    "Never a point estimate — we cannot know the price.",
    )
    intent_note: str | None = None


class RightsResponse(BaseModel):
    """
    Top-level output.

    layer_verdicts is filtered to the requested jurisdiction and intent;
    all_determinations holds the full matrix so the client can toggle without
    a new request.
    """

    query: AssetQuery
    entity: ResolvedEntity

    stop_for_disambiguation: bool = Field(
        False,
        description="True when resolution_confidence is LOW with multiple "
                    "candidates. Research did NOT run. The UI must present "
                    "alternate_candidates and await a choice. Researching an "
                    "ambiguous entity produces confidently wrong output — the "
                    "worst failure mode this product has.",
    )

    overall_verdict: Verdict = Field(
        ...,
        description="Most restrictive verdict across REQUIRED layers only, "
                    "per VERDICT_ORDER. Never 'clear' if any required layer "
                    "is not clear.",
    )
    overall_headline: str = Field(..., max_length=160)
    overall_confidence: Confidence

    layer_verdicts: list[LayerVerdict] = Field(default_factory=list)
    all_determinations: list[Determination] = Field(default_factory=list)

    disagreements: list[DisagreementNote] = Field(default_factory=list)
    unresolved: list[UnresolvedQuestion] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    handoff_links: list[HandoffLink] = Field(default_factory=list)

    boundary_note: str | None = Field(
        None,
        description="Set when the asset type is recognized but unsupported "
                    "(image, font, character, footage, trademark). Explicit "
                    "boundaries read as rigor; faked coverage does not.",
    )
    disclaimer: str = Field(
        default="Research, not legal advice. Where the public record is wrong, "
                "this is wrong. Have a professional confirm before you rely on it."
    )

    generated_at: datetime
    cache_key: str | None = Field(
        None,
        description="Sorted colon-joined is_primary identifiers across all "
                    "layers, prefixed by asset type. NEVER the raw query "
                    "string. Jurisdiction and intent are excluded — the full "
                    "matrix is cached together.",
    )
    served_from_cache: bool = False
    permalink: HttpUrl | None = None
    run_log: list[PipelineEvent] = Field(
        default_factory=list,
        description="The accession log of the run that produced this record. "
                    "Kept on the record so a warm query stays legible after "
                    "the fact: which tier answered, what Parallel ran, what "
                    "was cached. Volatile (timings differ run to run) and "
                    "excluded from fixture comparison.")


# ---------------------------------------------------------------------------
# Pipeline streaming
# ---------------------------------------------------------------------------


class PipelineStage(str, Enum):
    CLASSIFY = "classify"
    IDENTIFY = "identify"
    DECOMPOSE = "decompose"
    RESEARCH = "research"
    RULES = "rules"
    COMPARE = "compare"
    ASSEMBLE = "assemble"


class PipelineEvent(BaseModel):
    """
    SSE event driving the live progress UI.

    This is not decoration. A cold query takes 30-90s (PROJECT.md §4.6) and
    the staged progress display is what makes that tolerable. Stages must be
    legible to a viewer who has never seen the product.
    """

    stage: PipelineStage
    status: Literal["started", "progress", "complete", "failed", "skipped", "timeout"]
    message: str = Field(..., description="Human-readable, e.g. 'Found 2 rights layers'")
    detail: str | None = None
    sources_consulted: int = 0
    elapsed_ms: int
    degraded: bool = Field(
        False,
        description="True when a tier failed and the stage fell back to a "
                    "lower tier. Tier 2 failures degrade to Tier 3; they must "
                    "never fail the whole query.",
    )
    error_message: str | None = Field(
        None, description="User-facing on failure. Never a raw stack trace."
    )
    partial: dict | None = Field(
        None,
        description="Partial results for progressive rendering. Layers "
                    "resolved from Tier 2 should appear while Tier 3 runs.",
    )


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------


class SourceRegistryEntry(BaseModel):
    """
    Static config, one per integrated source. Drives HandoffLink generation by
    template substitution over already-resolved identifiers.
    """

    name: str
    tier: LinkTier
    url_template: str = Field(
        ..., description="e.g. 'https://musicbrainz.org/recording/{value}'"
    )
    requires_scheme: str
    applicable_types: list[AssetType]
    purpose: Literal["verify", "resolve", "license", "alternative"]
    description: str
    navigation_hint: str | None = None
    authoritative: bool = False


RightsResponse.model_rebuild()
UnresolvedQuestion.model_rebuild()
