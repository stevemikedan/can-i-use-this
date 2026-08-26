from registry import entries, handoff_links
from schemas import AssetType, Confidence, Identifier, LinkTier


def ids():
    return [
        Identifier(scheme="musicbrainz_recording", value="rec-1", layer_id="sound_recording",
                   confidence=Confidence.HIGH, is_primary=True),
        Identifier(scheme="musicbrainz_work", value="work-1", layer_id="composition",
                   confidence=Confidence.HIGH, is_primary=True),
        Identifier(scheme="iswc", value="T-1", layer_id="composition", confidence=Confidence.MEDIUM),
    ]


def test_yaml_loads_into_schema_entries():
    es = entries()
    assert len(es) >= 6
    assert all(e.url_template and e.requires_scheme for e in es)
    assert {e.tier for e in es} == {LinkTier.DEEP_LINK, LinkTier.PREFILLED_SEARCH, LinkTier.GUIDED_MANUAL}


def test_deep_links_from_identifiers_only():
    links = handoff_links(ids(), AssetType.MUSIC)
    urls = {l.url.unicode_string() if hasattr(l.url, "unicode_string") else str(l.url) for l in links}
    assert "https://musicbrainz.org/recording/rec-1" in urls
    assert "https://musicbrainz.org/work/work-1" in urls
    # no title extra -> no MLC / ASCAP / BMI; no renewal extra -> no CCE; no recording extra -> no DAHR
    names = {l.source_name for l in links}
    assert not any(n.startswith(("MLC", "ASCAP", "BMI", "Catalog", "DAHR")) for n in names)


def test_prefilled_search_is_url_encoded_and_guided_manual_carries_paste_string():
    links = handoff_links(ids(), AssetType.MUSIC, extra={"title": "West End Blues", "artist": "Louis Armstrong"})
    mlc = next(l for l in links if l.source_name.startswith("MLC"))
    assert "query=West+End+Blues" in str(mlc.url) and mlc.tier is LinkTier.PREFILLED_SEARCH
    assert mlc.purpose == "license"
    ascap = next(l for l in links if l.source_name.startswith("ASCAP"))
    assert ascap.tier is LinkTier.GUIDED_MANUAL and ascap.paste_string == "West End Blues"
    assert ascap.navigation_hint


def test_conditional_resolve_links():
    base = {"title": "Blue Moon", "artist": "The Marcels"}
    assert not any(l.source_name.startswith("Catalog") for l in handoff_links(ids(), AssetType.MUSIC, extra=base))
    links = handoff_links(ids(), AssetType.MUSIC,
                          extra={**base, "renewal_title": "Blue Moon", "year": 1961, "unconfirmed_recording": "Blue Moon"})
    cce = next(l for l in links if l.source_name.startswith("Catalog"))
    assert "1961" in cce.navigation_hint and cce.paste_string == "Blue Moon" and cce.purpose == "resolve"
    dahr = next(l for l in links if l.source_name.startswith("DAHR"))
    assert "The Marcels" in dahr.navigation_hint


def test_asset_type_filter():
    links = handoff_links(ids(), AssetType.TEXT, extra={"title": "x"})
    assert all("musicbrainz" not in str(l.url) for l in links)
