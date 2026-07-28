from datetime import datetime, timedelta, timezone

from neri_printer_manager.cups_filters import CupsFilterService


def _cups_timestamp(moment: datetime) -> str:
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return (
        f"[{moment.day:02d}/{months[moment.month - 1]}/{moment.year:04d}:"
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d} +0000]"
    )


def test_only_current_cups_log_errors_are_considered_recent() -> None:
    now = datetime.now(timezone.utc)
    current = f"E {_cups_timestamp(now - timedelta(minutes=2))} Filter failed"
    old = f"E {_cups_timestamp(now - timedelta(days=2))} Filter failed"
    assert CupsFilterService._line_is_recent(current, 30) is True
    assert CupsFilterService._line_is_recent(old, 30) is False


def test_log_line_without_timestamp_is_not_reported_as_current() -> None:
    assert CupsFilterService._line_is_recent("E Filter failed", 30) is False
