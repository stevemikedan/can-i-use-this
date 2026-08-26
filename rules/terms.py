"""
Deterministic copyright term rules. No network, no model, no I/O.

Every function returns (status, expiry_year, rule_id, explanation).
Status is one of: public_domain, protected, undetermined.

CURRENT_YEAR is a module constant because several US rules are relative to
"now" and roll forward every January 1. Tests pin it explicitly.

This module holds the shared types plus the US published-work term and
life+70. The MMA/CLASSICS sound-recording schedule is in mma.py; the roll-up
is in rollup.py. Function bodies are unchanged from the original rules.py.
"""

from dataclasses import dataclass
from typing import Literal, Optional

CURRENT_YEAR = 2026

Status = Literal["public_domain", "protected", "undetermined"]


@dataclass
class Determination:
    status: Status
    expiry_year: Optional[int]      # year it enters PD (Jan 1)
    rule_id: str
    explanation: str
    blocked_by: Optional[str] = None


# ---------------------------------------------------------------------------
# US published works — compositions, texts, films
# ---------------------------------------------------------------------------

def us_standard_term(
    pub_year: int,
    renewal_filed: Optional[bool] = None,
    current_year: int = CURRENT_YEAR,
) -> Determination:
    """
    US published works. The 95-year cliff rolls forward each 1 January.

    In 2026 the cliff sits at 1931: anything published 1930 or earlier is PD
    regardless of renewal, which is why renewal only matters from 1931-1963.
    """
    cliff = current_year - 95

    if pub_year < cliff:
        return Determination(
            "public_domain", pub_year + 95 + 1, "us_published_expired",
            f"Published {pub_year} in the US. The 95-year term expired "
            f"1 January {pub_year + 96}.",
        )

    # Renewal window: works still inside the 95-year term that required a
    # year-28 renewal filing.
    if cliff <= pub_year <= 1963:
        if renewal_filed is None:
            return Determination(
                "undetermined", None, "us_renewal_unknown",
                f"Published {pub_year} in the US. Works published between "
                f"{cliff} and 1963 required renewal in year 28. Renewal "
                "status could not be determined.",
                blocked_by="renewal_filed",
            )
        if renewal_filed is False:
            return Determination(
                "public_domain", pub_year + 28 + 1, "us_renewal_not_filed",
                f"Published {pub_year} in the US with no renewal filed in "
                f"year 28. Entered the public domain 1 January {pub_year + 29}.",
            )
        return Determination(
            "protected", pub_year + 95 + 1, "us_renewal_filed",
            f"Published {pub_year} in the US and renewed. Protected until "
            f"1 January {pub_year + 96}.",
        )

    # 1964-1977: renewal became automatic.
    if 1964 <= pub_year <= 1977:
        return Determination(
            "protected", pub_year + 95 + 1, "us_published_1964_1977",
            f"Published {pub_year} in the US. Renewal was automatic; "
            f"protected until 1 January {pub_year + 96}.",
        )

    return Determination(
        "protected", pub_year + 95 + 1, "us_published_post_1978",
        f"Published {pub_year} in the US. Protected until at least "
        f"1 January {pub_year + 96}.",
    )


# ---------------------------------------------------------------------------
# EU / UK sound recordings — term runs from publication, not from a life
# ---------------------------------------------------------------------------

def eu_sound_recording(
    pub_year: int,
    jurisdiction: str = "EU",
    current_year: int = CURRENT_YEAR,
) -> Determination:
    """
    PUBLISHED sound recordings: the term runs from first publication —
    50 years, extended to 70 by Directive 2011/77/EU (UK: Copyright and
    Duration of Rights in Performances Regulations 2013) for recordings
    still protected on 1 November 2013, i.e. first published 1963 or
    later. A recording published 1962 or earlier had already expired under
    the 50-year term and was not revived.

    pub_year must be the year of first publication, not the session date.
    An unpublished recording runs from the year it was made instead; the
    pipeline never calls this for unpublished recordings.

    The UK retained the 70-year term after leaving the EU, so the two
    jurisdictions are aligned today; they could diverge, which is why the
    rule_id carries the jurisdiction.
    """
    j = jurisdiction.lower()
    if pub_year <= 1962:
        return Determination(
            "public_domain", pub_year + 50 + 1, f"{j}_sr_pre_1963",
            f"Published {pub_year}. The 50-year term expired 1 January "
            f"{pub_year + 51}, before the 2013 extension to 70 years, which "
            "did not revive expired recordings.",
        )
    expiry = pub_year + 70 + 1
    if current_year >= expiry:
        return Determination(
            "public_domain", expiry, f"{j}_sr_70_from_publication",
            f"Published {pub_year}. The 70-year term from publication expired "
            f"1 January {expiry}.",
        )
    return Determination(
        "protected", expiry, f"{j}_sr_70_from_publication",
        f"Published {pub_year}. Protected for 70 years from publication, "
        f"until 1 January {expiry}.",
    )


# ---------------------------------------------------------------------------
# Life + 70 — EU, UK, and US works created after 1978
# ---------------------------------------------------------------------------

def life_plus_70(
    death_years: list[Optional[int]],
    jurisdiction: str = "EU",
    current_year: int = CURRENT_YEAR,
) -> Determination:
    """
    Term runs from the death of the LAST surviving author.
    A single unknown death year blocks the whole determination.
    """
    if not death_years or any(d is None for d in death_years):
        return Determination(
            "undetermined", None, f"{jurisdiction.lower()}_death_year_unknown",
            "Term runs from the death of the last surviving author, and at "
            "least one death year could not be determined.",
            blocked_by="author_death_year",
        )

    last_death = max(d for d in death_years if d is not None)
    expiry = last_death + 70 + 1

    if current_year >= expiry:
        return Determination(
            "public_domain", expiry, f"{jurisdiction.lower()}_life_plus_70",
            f"Last surviving author died {last_death}. Term expired "
            f"1 January {expiry}.",
        )
    return Determination(
        "protected", expiry, f"{jurisdiction.lower()}_life_plus_70",
        f"Last surviving author died {last_death}. Protected until "
        f"1 January {expiry}.",
    )
