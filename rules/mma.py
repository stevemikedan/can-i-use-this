"""
US sound recordings — Music Modernization Act / CLASSICS Act.

Function body unchanged from the original rules.py.
"""

from .terms import CURRENT_YEAR, Determination, us_standard_term


def us_sound_recording(pub_year: int, current_year: int = CURRENT_YEAR) -> Determination:
    """
    Fully deterministic from publication year alone. No rights database needed.

    Before 1923       PD since 1 Jan 2022
    1923-1946         95 + 5  = 100 years
    1947-1956         95 + 15 = 110 years
    1957 - Feb 1972   protected until 15 Feb 2067
    After Feb 1972    standard federal terms
    """
    if pub_year < 1923:
        return Determination(
            "public_domain", 2022, "us_sr_pre_1923",
            f"Published {pub_year}, before 1923. Entered the public domain "
            "1 January 2022 under the Music Modernization Act.",
        )

    if 1923 <= pub_year <= 1946:
        expiry = pub_year + 100 + 1  # term runs to end of the 100th year
        rule = "us_sr_mma_1923_1946"
    elif 1947 <= pub_year <= 1956:
        expiry = pub_year + 110 + 1
        rule = "us_sr_mma_1947_1956"
    elif 1957 <= pub_year <= 1972:
        expiry = 2067
        rule = "us_sr_mma_1957_1972"
    else:
        return us_standard_term(pub_year, current_year=current_year)

    if current_year >= expiry:
        return Determination(
            "public_domain", expiry, rule,
            f"Published {pub_year}. CLASSICS Act protection ended 1 January {expiry}.",
        )
    return Determination(
        "protected", expiry, rule,
        f"Published {pub_year}. The CLASSICS Act protects it until 1 January {expiry}.",
    )
