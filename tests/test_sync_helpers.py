from datetime import date

import pytest

import garmy_sync


def test_gaps_to_ranges_groups_contiguous_days():
    gaps = [
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 4),
        date(2026, 6, 7),
        date(2026, 6, 8),
    ]

    assert garmy_sync.gaps_to_ranges(gaps) == [
        (date(2026, 6, 1), date(2026, 6, 2)),
        (date(2026, 6, 4), date(2026, 6, 4)),
        (date(2026, 6, 7), date(2026, 6, 8)),
    ]


@pytest.mark.parametrize("value", ["0", "-1"])
def test_sync_parser_rejects_non_positive_days(value):
    with pytest.raises(SystemExit):
        garmy_sync.build_parser().parse_args([value])
