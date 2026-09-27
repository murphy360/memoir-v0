from datetime import date

from app.services.date_normalization import (
    parse_text_date_range,
    resolve_start_end_dates,
)


def test_iso_date_is_a_single_day():
    assert parse_text_date_range("2007-07-16") == (date(2007, 7, 16), date(2007, 7, 16))


def test_year_alone_spans_the_year():
    assert parse_text_date_range("1998") == (date(1998, 1, 1), date(1998, 12, 31))


def test_year_range_and_decade():
    assert parse_text_date_range("1998 to 2002") == (
        date(1998, 1, 1),
        date(2002, 12, 31),
    )
    assert parse_text_date_range("the 1980s") == (date(1980, 1, 1), date(1989, 12, 31))


def test_season_winter_crosses_the_year():
    assert parse_text_date_range("winter 1999") == (
        date(1999, 12, 1),
        date(2000, 2, 29),
    )


def test_blank_and_nonsense_give_nothing():
    assert parse_text_date_range(None) == (None, None)
    assert parse_text_date_range("sometime") == (None, None)


def test_resolve_swaps_reversed_dates_and_fills_missing_end():
    start, end = resolve_start_end_dates("2002", "1998")
    assert (start, end) == (date(1998, 12, 31), date(2002, 1, 1))
    assert start <= end
    assert resolve_start_end_dates("2007-07-16", None) == (
        date(2007, 7, 16),
        date(2007, 7, 16),
    )
