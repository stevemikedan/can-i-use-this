"""Boundary tests. Run: python test_rules.py"""

from rules import (
    us_sound_recording, us_standard_term, life_plus_70, roll_up,
    status_to_verdict,
)

Y = 2026
fails = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}\n        got={got!r}\n        want={want!r}"
          if not ok else f"PASS  {label}")
    if not ok:
        fails.append(label)


print("=== US SOUND RECORDINGS (MMA / CLASSICS) ===")
check("1922 -> PD (pre-1923)", us_sound_recording(1922, Y).status, "public_domain")
check("1925 -> PD in 2026",    us_sound_recording(1925, Y).status, "public_domain")
check("1925 expiry 2026",      us_sound_recording(1925, Y).expiry_year, 2026)
check("1926 -> protected",     us_sound_recording(1926, Y).status, "protected")
check("1926 expiry 2027",      us_sound_recording(1926, Y).expiry_year, 2027)
check("1928 -> protected",     us_sound_recording(1928, Y).status, "protected")
check("1928 expiry 2029",      us_sound_recording(1928, Y).expiry_year, 2029)
check("1946 expiry 2047",      us_sound_recording(1946, Y).expiry_year, 2047)
check("1947 expiry 2058",      us_sound_recording(1947, Y).expiry_year, 2058)
check("1956 expiry 2067",      us_sound_recording(1956, Y).expiry_year, 2067)
check("1960 expiry 2067",      us_sound_recording(1960, Y).expiry_year, 2067)

print("\n=== ROLLING BOUNDARY (advances 1 Jan) ===")
check("1926 PD in 2027",       us_sound_recording(1926, 2027).status, "public_domain")
check("1927 protected in 2027", us_sound_recording(1927, 2027).status, "protected")

print("\n=== US PUBLISHED WORKS ===")
check("1928 -> PD",            us_standard_term(1928, current_year=Y).status, "public_domain")
check("1928 expiry 2024",      us_standard_term(1928, current_year=Y).expiry_year, 2024)
check("1930 -> PD",            us_standard_term(1930, current_year=Y).status, "public_domain")
check("1931 renewal unknown",  us_standard_term(1931, current_year=Y).status, "undetermined")
check("1931 blocked_by",       us_standard_term(1931, current_year=Y).blocked_by, "renewal_filed")
check("1955 not renewed -> PD", us_standard_term(1955, renewal_filed=False, current_year=Y).status, "public_domain")
check("1955 renewed -> prot.",  us_standard_term(1955, renewal_filed=True, current_year=Y).status, "protected")
check("1955 renewed exp 2051",  us_standard_term(1955, renewal_filed=True, current_year=Y).expiry_year, 2051)
check("1970 -> protected",      us_standard_term(1970, current_year=Y).status, "protected")

print("\n=== LIFE + 70 ===")
check("d.1938,1965 -> protected", life_plus_70([1938, 1965], "EU", Y).status, "protected")
check("d.1938,1965 exp 2036",     life_plus_70([1938, 1965], "EU", Y).expiry_year, 2036)
check("d.1924 -> PD",             life_plus_70([1924], "EU", Y).status, "public_domain")
check("unknown death -> undet.",  life_plus_70([1938, None], "EU", Y).status, "undetermined")

print("\n=== WEST END BLUES — the spike's gate case ===")
comp = us_standard_term(1928, current_year=Y)
rec = us_sound_recording(1928, Y)
check("composition PD",        comp.status, "public_domain")
check("composition exp 2024",  comp.expiry_year, 2024)
check("recording protected",   rec.status, "protected")
check("recording exp 2029",    rec.expiry_year, 2029)

verdict, blocking = roll_up([
    ("composition", status_to_verdict(comp.status), True),
    ("recording",   status_to_verdict(rec.status), True),
])
check("roll-up = license_required", verdict, "license_required")
check("blocking layer = recording", blocking, "recording")

print("\n=== ROLL-UP EDGE CASES ===")
check("undetermined beats license",
      roll_up([("a", "undetermined", True), ("b", "license_required", True)])[0],
      "undetermined")
check("non-required excluded",
      roll_up([("a", "clear", True), ("b", "restricted", False)])[0],
      "clear")
check("re-record: comp only",
      roll_up([("composition", "clear", True), ("recording", "license_required", False)])[0],
      "clear")

print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILURES: {fails}'}")
