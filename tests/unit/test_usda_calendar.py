"""Tester for USDA-kalender-loader + `usda_blackout`-gate."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest

# Side-effekt-import for å registrere gate
import bedrock.fetch.usda_calendar  # noqa: F401
from bedrock.engine.gates import GateContext, get_gate
from bedrock.fetch.usda_calendar import (
    UsdaCalendarError,
    clear_usda_calendar_cache,
    load_usda_calendar,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_usda_calendar_cache()
    yield
    clear_usda_calendar_cache()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_returns_empty_dict_for_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text("")
    cal = load_usda_calendar(path)
    assert cal == {}


def test_load_parses_prospective_plantings(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text(
        dedent(
            """\
            prospective_plantings:
              - 2026-03-31T16:00:00Z
              - 2025-03-31T16:00:00Z
            """
        )
    )
    cal = load_usda_calendar(path)
    assert "prospective_plantings" in cal
    dates = cal["prospective_plantings"]
    assert len(dates) == 2
    # Sortert: 2025 før 2026
    assert dates[0] < dates[1]
    assert dates[1].year == 2026
    # Timezone-aware (UTC)
    assert dates[0].tzinfo is not None


def test_load_parses_multiple_report_types(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text(
        dedent(
            """\
            prospective_plantings:
              - 2026-03-31T16:00:00Z
            grain_stocks:
              - 2026-06-28T16:00:00Z
              - 2026-09-30T16:00:00Z
            """
        )
    )
    cal = load_usda_calendar(path)
    assert set(cal.keys()) == {"prospective_plantings", "grain_stocks"}


def test_load_accepts_naive_datetime_as_utc(tmp_path: Path) -> None:
    """YAML datetime uten tz skal tolkes som UTC."""
    path = tmp_path / "usda.yaml"
    path.write_text(
        dedent(
            """\
            prospective_plantings:
              - 2026-03-31 16:00:00
            """
        )
    )
    cal = load_usda_calendar(path)
    dt = cal["prospective_plantings"][0]
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt).total_seconds() == 0


def test_load_rejects_non_list_dates(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text("prospective_plantings: not-a-list\n")
    with pytest.raises(UsdaCalendarError, match="must be a list"):
        load_usda_calendar(path)


def test_load_rejects_non_datetime_item(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text(
        dedent(
            """\
            prospective_plantings:
              - 12345
            """
        )
    )
    with pytest.raises(UsdaCalendarError, match="ikke-dato"):
        load_usda_calendar(path)


def test_load_rejects_invalid_iso_string(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text(
        dedent(
            """\
            prospective_plantings:
              - "not-a-date"
            """
        )
    )
    with pytest.raises(UsdaCalendarError, match="ugyldig dato"):
        load_usda_calendar(path)


def test_load_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_usda_calendar(Path("/tmp/does-not-exist-usda.yaml"))


def test_load_caches_result(tmp_path: Path) -> None:
    path = tmp_path / "usda.yaml"
    path.write_text("prospective_plantings: [2026-03-31T16:00:00Z]\n")
    cal1 = load_usda_calendar(path)
    # Endre fila — cache skal IKKE reflektere endring uten clear
    path.write_text("prospective_plantings: [2027-03-30T16:00:00Z]\n")
    cal2 = load_usda_calendar(path)
    assert cal1 is cal2

    clear_usda_calendar_cache()
    cal3 = load_usda_calendar(path)
    assert cal3["prospective_plantings"][0].year == 2027


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def _ctx(now: datetime | None) -> GateContext:
    return GateContext(
        instrument="Corn",
        score=3.0,
        max_score=10.0,
        active_families=2,
        family_scores={"outlook": 3.0},
        now=now,
    )


def _calendar_path(tmp_path: Path) -> Path:
    p = tmp_path / "usda.yaml"
    p.write_text(
        dedent(
            """\
            prospective_plantings:
              - 2026-03-31T16:00:00Z
            """
        )
    )
    return p


def test_usda_blackout_returns_false_when_now_is_none(tmp_path: Path) -> None:
    fn = get_gate("usda_blackout")
    path = _calendar_path(tmp_path)
    assert fn(_ctx(None), {"calendar_path": str(path)}) is False


def test_usda_blackout_triggers_within_window(tmp_path: Path) -> None:
    fn = get_gate("usda_blackout")
    path = _calendar_path(tmp_path)
    # Rapport kl 16:00 UTC, 2 timer før → innenfor ±3h
    now = datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc)
    assert fn(_ctx(now), {"calendar_path": str(path), "hours": 3}) is True


def test_usda_blackout_no_trigger_outside_window(tmp_path: Path) -> None:
    fn = get_gate("usda_blackout")
    path = _calendar_path(tmp_path)
    # 4 timer før → utenfor ±3h
    now = datetime(2026, 3, 31, 12, 0, tzinfo=timezone.utc)
    assert fn(_ctx(now), {"calendar_path": str(path), "hours": 3}) is False


def test_usda_blackout_triggers_at_exact_boundary(tmp_path: Path) -> None:
    """±3h inkluderer grenseverdiene (≤, ikke <)."""
    fn = get_gate("usda_blackout")
    path = _calendar_path(tmp_path)
    now = datetime(2026, 3, 31, 13, 0, tzinfo=timezone.utc)  # exactly -3h
    assert fn(_ctx(now), {"calendar_path": str(path), "hours": 3}) is True


def test_usda_blackout_asymmetric_window(tmp_path: Path) -> None:
    fn = get_gate("usda_blackout")
    path = _calendar_path(tmp_path)
    # hours_before=1, hours_after=6
    # 2 timer før → utenfor (1h-vinduet)
    now_before = datetime(2026, 3, 31, 14, 0, tzinfo=timezone.utc)
    assert (
        fn(
            _ctx(now_before),
            {"calendar_path": str(path), "hours_before": 1, "hours_after": 6},
        )
        is False
    )
    # 5 timer etter → innenfor (6h-vinduet)
    now_after = datetime(2026, 3, 31, 21, 0, tzinfo=timezone.utc)
    assert (
        fn(
            _ctx(now_after),
            {"calendar_path": str(path), "hours_before": 1, "hours_after": 6},
        )
        is True
    )


def test_usda_blackout_filter_report_types(tmp_path: Path) -> None:
    """Kun angitte rapport-typer teller."""
    path = tmp_path / "usda.yaml"
    path.write_text(
        dedent(
            """\
            prospective_plantings:
              - 2026-03-31T16:00:00Z
            grain_stocks:
              - 2026-06-28T16:00:00Z
            """
        )
    )
    fn = get_gate("usda_blackout")
    now = datetime(2026, 6, 28, 16, 0, tzinfo=timezone.utc)
    # Uten filter → utløses (grain_stocks matcher)
    assert fn(_ctx(now), {"calendar_path": str(path)}) is True
    # Med filter til kun prospective_plantings → ikke utløses
    assert (
        fn(
            _ctx(now),
            {
                "calendar_path": str(path),
                "report_types": ["prospective_plantings"],
            },
        )
        is False
    )


def test_usda_blackout_uses_naive_now_as_utc(tmp_path: Path) -> None:
    """Hvis context.now er naiv datetime → tolk som UTC."""
    fn = get_gate("usda_blackout")
    path = _calendar_path(tmp_path)
    now = datetime(2026, 3, 31, 15, 0)  # naiv
    assert fn(_ctx(now), {"calendar_path": str(path), "hours": 3}) is True
