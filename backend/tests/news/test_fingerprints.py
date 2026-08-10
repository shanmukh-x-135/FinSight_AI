"""News fingerprint normalization regressions."""

from datetime import datetime, timezone

from app.news.fingerprints import article_fingerprint


def test_fingerprint_normalizes_case_unicode_spacing_and_punctuation() -> None:
    published = datetime(2026, 8, 10, tzinfo=timezone.utc)
    first = article_fingerprint("ＲＥＬＩＡＮＣＥ: Profit   Surges!", published)
    second = article_fingerprint("reliance profit surges", published)

    assert first == second
    assert len(first) == 64


def test_fingerprint_is_scoped_to_publication_day() -> None:
    first = datetime(2026, 8, 10, tzinfo=timezone.utc)
    second = datetime(2026, 8, 11, tzinfo=timezone.utc)

    assert article_fingerprint("Same headline", first) != article_fingerprint(
        "Same headline", second
    )
