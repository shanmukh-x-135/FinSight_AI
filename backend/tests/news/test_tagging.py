"""Unit tests for company tagging (aliases + matching, false-positive guards)."""

from __future__ import annotations

from app.news.tagging import build_aliases, tag_article


def test_aliases_drop_generic_and_short_tokens() -> None:
    assert build_aliases("RELIANCE.NS", "RELIANCE INDUSTRIES LTD") == {"RELIANCE"}
    # "HDFC" survives (BANK/LTD are stopwords); the ticker base is kept too.
    assert build_aliases("HDFCBANK.NS", "HDFC BANK LTD") == {"HDFCBANK", "HDFC"}


def test_aliases_all_filtered_out_is_empty() -> None:
    # Short ticker + only stopwords → no aliases → this stock can never be tagged.
    assert build_aliases("IT.NS", "IT LTD") == set()


def test_tag_matches_by_name_token() -> None:
    aliases = {1: {"RELIANCE"}, 2: {"HDFCBANK", "HDFC"}}
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
    assert {"TCS", "CONSULTANCY"} <= aliases
    assert tag_article("Tata Power signs a new deal", "", {2: aliases}) == set()
    assert tag_article("TCS wins a large contract", "", {2: aliases}) == {2}
