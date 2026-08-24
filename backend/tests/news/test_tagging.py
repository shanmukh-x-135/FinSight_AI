"""Unit tests for company tagging (aliases + matching, false-positive guards)."""

from __future__ import annotations

from app.news.tagging import build_aliases, tag_article


def test_aliases_drop_generic_and_short_tokens() -> None:
    reliance = build_aliases("RELIANCE.NS", "RELIANCE INDUSTRIES LTD")
    assert "RELIANCE" not in reliance
    assert "RELIANCE INDUSTRIES" in reliance
    hdfc = build_aliases("HDFCBANK.NS", "HDFC BANK LTD")
    assert {"HDFCBANK", "HDFC BANK"} <= hdfc
    assert "HDFC" not in hdfc


def test_aliases_all_filtered_out_is_empty() -> None:
    # Short ticker + only a legal suffix leaves no safe match phrase.
    assert build_aliases("IT.NS", "LTD") == set()


def test_tag_matches_by_name_token() -> None:
    aliases = {1: {"RELIANCE"}, 2: {"HDFCBANK", "HDFC BANK"}}
    assert tag_article("Reliance shares surge today", "", aliases) == {1}
    assert tag_article("HDFC Bank posts record profit", "", aliases) == {2}


def test_tag_is_whole_word_not_substring() -> None:
    # "RELIANCESOMETHING" should not match the alias "RELIANCE".
    aliases = {1: {"RELIANCE"}}
    assert tag_article("Reliancesomething unrelated", "", aliases) == set()


def test_tag_none_when_no_alias_present() -> None:
    aliases = {1: {"RELIANCE"}, 2: {"TCS"}}
    assert tag_article("Market rises on global cues", "broad rally", aliases) == set()


def test_tag_can_match_multiple_stocks() -> None:
    aliases = {1: {"RELIANCE"}, 2: {"TCS"}}
    assert tag_article("Reliance and TCS both gain", "", aliases) == {1, 2}


def test_conglomerate_group_prefix_is_not_an_alias() -> None:
    # "TATA" spans many companies → must be dropped so "Tata Power" doesn't tag TCS.
    aliases = build_aliases("TCS.NS", "TATA CONSULTANCY SERVICES")
    assert "TATA" not in aliases
    assert {"TCS", "TATA CONSULTANCY SERVICES"} <= aliases
    assert tag_article("Tata Power signs a new deal", "", {2: aliases}) == set()
    assert tag_article("TCS wins a large contract", "", {2: aliases}) == {2}


def test_generic_name_tokens_do_not_create_false_positive_tags() -> None:
    ongc = build_aliases("ONGC.NS", "OIL AND NATURAL GAS CORP.")
    hdfc_life = build_aliases("HDFCLIFE.NS", "HDFC LIFE INS CO LTD")
    techm = build_aliases("TECHM.NS", "TECH MAHINDRA LIMITED")

    assert "OIL" not in ongc
    assert "LIFE" not in hdfc_life
    assert "TECH" not in techm
    aliases = {1: ongc, 2: hdfc_life, 3: techm}
    assert (
        tag_article("Crude oil rises as global tensions increase", "", aliases) == set()
    )
    assert (
        tag_article("Insurer reports stronger life premium growth", "", aliases) == set()
    )
    assert tag_article("Technology IPO calendar expands", "", aliases) == set()


def test_ordinary_reliance_word_does_not_tag_reliance_industries() -> None:
    aliases = build_aliases("RELIANCE.NS", "RELIANCE INDUSTRIES LTD")

    assert (
        tag_article(
            "Rupee steady as traders assess oil prices",
            "The conflict raises risks for India's import reliance.",
            {1: aliases},
        )
        == set()
    )
    assert tag_article(
        "Reliance Industries expands retail network", "", {1: aliases}
    ) == {1}


def test_shared_brand_requires_the_company_phrase() -> None:
    bank = build_aliases("HDFCBANK.NS", "HDFC BANK LTD")
    life = build_aliases("HDFCLIFE.NS", "HDFC LIFE INS CO LTD")
    aliases = {1: bank, 2: life}

    assert tag_article("HDFC Bank raises deposit rates", "", aliases) == {1}
    assert tag_article("HDFC Life reports premium growth", "", aliases) == {2}


def test_hyphenated_ticker_uses_reviewed_readable_alias() -> None:
    aliases = build_aliases("BAJAJ-AUTO.NS", "BAJAJ AUTO LIMITED")
    assert "BAJAJ AUTO" in aliases
    assert tag_article("Bajaj Auto motorcycle exports rise", "", {1: aliases}) == {1}
