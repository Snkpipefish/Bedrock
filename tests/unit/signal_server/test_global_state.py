"""Tester for `bedrock.signal_server.global_state` (session 2026-09-05).

Bruker en fake store med `get_econ_events` som returnerer en liten
DataFrame — ingen SQLite. Verifiserer vindus-logikk (før/etter),
land-relevans (USD → alle, EUR → kun EURUSD), nærmeste-event-valg,
USDA-blackout for grains, og fail-open ved feil.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from bedrock.fetch.usda_calendar import clear_usda_calendar_cache
from bedrock.signal_server.config import ServerConfig
from bedrock.signal_server.global_state import (
    INSTRUMENT_EVENT_COUNTRIES,
    USDA_INSTRUMENTS,
    build_global_state,
    event_countries_for,
    fail_open_global_state,
    load_bot_instruments,
)

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


class FakeStore:
    """Returnerer gitte events uansett filter; husker siste kall."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[dict] = []

    def get_econ_events(
        self,
        countries=None,
        impact_levels=None,
        from_ts=None,
        to_ts=None,
        title_pattern=None,
    ) -> pd.DataFrame:
        self.calls.append(
            {
                "countries": countries,
                "impact_levels": impact_levels,
                "from_ts": from_ts,
                "to_ts": to_ts,
            }
        )
        if not self.rows:
            return pd.DataFrame(
                columns=["event_ts", "country", "title", "impact", "forecast", "previous", "actual"]
            )
        df = pd.DataFrame(self.rows)
        df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
        return df


class RaisingStore:
    def get_econ_events(self, *args, **kwargs):
        raise RuntimeError("db exploded")


def _event(minutes: int, country: str = "USD", title: str = "NFP", impact: str = "High") -> dict:
    return {
        "event_ts": (NOW + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S"),
        "country": country,
        "title": title,
        "impact": impact,
        "forecast": None,
        "previous": None,
        "actual": None,
    }


def _whitelist(tmp_path: Path, names: list[str] | None = None) -> Path:
    names = names or ["GOLD", "EURUSD", "GBPUSD", "Corn", "SPX500"]
    wl = tmp_path / "bot_whitelist.yaml"
    wl.write_text(yaml.safe_dump({"mapping": {f"id{i}": n for i, n in enumerate(names)}}))
    return wl


def _usda_calendar(tmp_path: Path, times: list[datetime] | None = None) -> Path:
    cal = tmp_path / "usda.yaml"
    entries = [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in (times or [])]
    cal.write_text(yaml.safe_dump({"prospective_plantings": entries}))
    clear_usda_calendar_cache()
    return cal


def _cfg(tmp_path: Path, **overrides) -> ServerConfig:
    """ServerConfig med tmp-whitelist + tom tmp-USDA-kalender som default.
    Defaults lages kun når de ikke er overstyrt — ellers ville de
    overskrevet filen testen nettopp skrev til samme sti."""
    base: dict[str, object] = {}
    if "bot_whitelist_path" not in overrides:
        base["bot_whitelist_path"] = _whitelist(tmp_path)
    if "usda_calendar_path" not in overrides:
        base["usda_calendar_path"] = _usda_calendar(tmp_path)
    base.update(overrides)
    return ServerConfig(**base)  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------------------
# event_blackout
# ---------------------------------------------------------------------------


def test_usd_event_30min_ahead_blackouts_all_instruments(tmp_path: Path) -> None:
    store = FakeStore([_event(30)])
    gs = build_global_state(store, NOW, _cfg(tmp_path))
    bo = gs["event_blackout"]
    assert set(bo) == {"GOLD", "EURUSD", "GBPUSD", "Corn", "SPX500"}
    for inst, info in bo.items():
        assert info["minutes_away"] == 30, inst
        assert info["event"] == "NFP"
        assert info["country"] == "USD"
        assert info["impact"] == "High"
    assert "event_blackout_error" not in gs


def test_event_20min_ago_excluded_with_after_15(tmp_path: Path) -> None:
    store = FakeStore([_event(-20)])
    gs = build_global_state(store, NOW, _cfg(tmp_path, event_blackout_after_min=15))
    assert gs["event_blackout"] == {}


def test_event_10min_ago_included_with_after_15(tmp_path: Path) -> None:
    store = FakeStore([_event(-10)])
    gs = build_global_state(store, NOW, _cfg(tmp_path, event_blackout_after_min=15))
    bo = gs["event_blackout"]
    assert set(bo) == {"GOLD", "EURUSD", "GBPUSD", "Corn", "SPX500"}
    assert all(v["minutes_away"] == -10 for v in bo.values())


def test_event_beyond_before_window_excluded(tmp_path: Path) -> None:
    store = FakeStore([_event(61)])
    gs = build_global_state(store, NOW, _cfg(tmp_path, event_blackout_before_min=60))
    assert gs["event_blackout"] == {}


def test_eur_only_event_blackouts_only_eurusd(tmp_path: Path) -> None:
    store = FakeStore([_event(15, country="EUR", title="ECB Rate")])
    gs = build_global_state(store, NOW, _cfg(tmp_path))
    assert set(gs["event_blackout"]) == {"EURUSD"}
    assert gs["event_blackout"]["EURUSD"]["country"] == "EUR"
    assert gs["event_blackout"]["EURUSD"]["event"] == "ECB Rate"


def test_nearest_event_chosen_per_instrument(tmp_path: Path) -> None:
    store = FakeStore(
        [
            _event(45, title="Far"),
            _event(-5, title="JustHappened"),
            _event(20, title="Mid"),
        ]
    )
    gs = build_global_state(store, NOW, _cfg(tmp_path))
    assert gs["event_blackout"]["GOLD"]["event"] == "JustHappened"
    assert gs["event_blackout"]["GOLD"]["minutes_away"] == -5


def test_empty_frame_gives_empty_blackout(tmp_path: Path) -> None:
    store = FakeStore([])
    gs = build_global_state(store, NOW, _cfg(tmp_path))
    assert gs["event_blackout"] == {}
    assert gs["usda_blackout"] == {}
    assert "event_blackout_error" not in gs


def test_store_raising_is_fail_open(tmp_path: Path) -> None:
    gs = build_global_state(RaisingStore(), NOW, _cfg(tmp_path))
    assert gs["event_blackout"] == {}
    assert "db exploded" in gs["event_blackout_error"]
    # Basis-feltene er fortsatt der
    assert gs["geo_active"] is False
    assert gs["vix_regime"] == "normal"


def test_store_queried_with_window_and_impact(tmp_path: Path) -> None:
    store = FakeStore([])
    cfg = _cfg(
        tmp_path,
        event_blackout_before_min=60,
        event_blackout_after_min=15,
        event_blackout_impact_levels=("High", "Medium"),
    )
    build_global_state(store, NOW, cfg)
    call = store.calls[0]
    assert call["impact_levels"] == ["High", "Medium"]
    assert call["from_ts"] == "2026-09-05T11:45:00"
    assert call["to_ts"] == "2026-09-05T13:00:00"
    # Union av relevante land for whitelisten (USD + EUR + GBP)
    assert call["countries"] == ["ALL", "All", "EUR", "GBP", "USD"]  # + globale events


def test_disabled_skips_lookups(tmp_path: Path) -> None:
    store = FakeStore([_event(10)])
    gs = build_global_state(store, NOW, _cfg(tmp_path, event_blackout_enabled=False))
    assert gs["event_blackout"] == {}
    assert gs["usda_blackout"] == {}
    assert store.calls == []


# ---------------------------------------------------------------------------
# Basis-felt (kontrakt mot boten)
# ---------------------------------------------------------------------------


def test_base_fields_match_adapter_defaults(tmp_path: Path) -> None:
    gs = build_global_state(FakeStore([]), NOW, _cfg(tmp_path))
    assert gs["geo_risk_active"] is False
    assert gs["geo_active"] is gs["geo_risk_active"]
    assert gs["vix_regime"] == "normal"
    assert gs["correlation_config"] == {"max_per_group": 2, "max_total": 20}


def test_fail_open_global_state_has_error_and_empty_blackouts() -> None:
    gs = fail_open_global_state("db missing")
    assert gs["event_blackout"] == {}
    assert gs["usda_blackout"] == {}
    assert gs["event_blackout_error"] == "db missing"
    assert gs["geo_active"] is False


# ---------------------------------------------------------------------------
# usda_blackout
# ---------------------------------------------------------------------------


def test_usda_report_ahead_blackouts_grains_only(tmp_path: Path) -> None:
    cal = _usda_calendar(tmp_path, [NOW + timedelta(hours=1, minutes=30)])
    cfg = _cfg(
        tmp_path,
        bot_whitelist_path=_whitelist(tmp_path, ["GOLD", "Corn", "Wheat", "Soybean", "Coffee"]),
        usda_calendar_path=cal,
    )
    gs = build_global_state(FakeStore([]), NOW, cfg)
    assert set(gs["usda_blackout"]) == {"Corn", "Wheat", "Soybean"}
    for info in gs["usda_blackout"].values():
        assert info["report"] == "prospective_plantings"
        assert info["hours_away"] == 1.5


def test_usda_report_after_window_excluded(tmp_path: Path) -> None:
    cal = _usda_calendar(tmp_path, [NOW - timedelta(hours=2)])
    cfg = _cfg(
        tmp_path,
        bot_whitelist_path=_whitelist(tmp_path, ["Corn"]),
        usda_calendar_path=cal,
        usda_blackout_hours_after=1.0,
    )
    gs = build_global_state(FakeStore([]), NOW, cfg)
    assert gs["usda_blackout"] == {}


def test_usda_report_recently_published_negative_hours(tmp_path: Path) -> None:
    cal = _usda_calendar(tmp_path, [NOW - timedelta(minutes=30)])
    cfg = _cfg(
        tmp_path,
        bot_whitelist_path=_whitelist(tmp_path, ["Corn"]),
        usda_calendar_path=cal,
        usda_blackout_hours_after=1.0,
    )
    gs = build_global_state(FakeStore([]), NOW, cfg)
    assert gs["usda_blackout"]["Corn"]["hours_away"] == -0.5


def test_usda_missing_calendar_is_fail_open(tmp_path: Path) -> None:
    cfg = _cfg(
        tmp_path,
        bot_whitelist_path=_whitelist(tmp_path, ["Corn"]),
        usda_calendar_path=tmp_path / "does-not-exist.yaml",
    )
    clear_usda_calendar_cache()
    gs = build_global_state(FakeStore([]), NOW, cfg)
    assert gs["usda_blackout"] == {}
    assert "usda_blackout" in gs["event_blackout_error"]
    assert gs["event_blackout"] == {}


# ---------------------------------------------------------------------------
# Whitelist + land-mapping
# ---------------------------------------------------------------------------


def test_load_bot_instruments_reads_mapping_values(tmp_path: Path) -> None:
    wl = _whitelist(tmp_path, ["GOLD", "OIL WTI", "Corn"])
    assert load_bot_instruments(wl) == ["GOLD", "OIL WTI", "Corn"]


def test_load_bot_instruments_falls_back_when_unreadable(tmp_path: Path) -> None:
    assert load_bot_instruments(tmp_path / "missing.yaml") == list(INSTRUMENT_EVENT_COUNTRIES)
    bad = tmp_path / "bad.yaml"
    bad.write_text("nope: [unclosed")
    assert load_bot_instruments(bad) == list(INSTRUMENT_EVENT_COUNTRIES)
    no_mapping = tmp_path / "nomap.yaml"
    no_mapping.write_text(yaml.safe_dump({"gates": {}}))
    assert load_bot_instruments(no_mapping) == list(INSTRUMENT_EVENT_COUNTRIES)


def test_repo_whitelist_instruments_all_have_country_mapping() -> None:
    """Alle instrumenter i den faktiske whitelisten skal ha eksplisitt
    land-mapping (ikke bare default) — fanger nye instrumenter."""
    repo_wl = Path("config/bot_whitelist.yaml")
    if not repo_wl.exists():
        import pytest

        pytest.skip("config/bot_whitelist.yaml mangler")
    for inst in load_bot_instruments(repo_wl):
        assert inst in INSTRUMENT_EVENT_COUNTRIES, f"{inst} mangler i INSTRUMENT_EVENT_COUNTRIES"


def test_event_countries_fx_pairs_add_non_usd_leg() -> None:
    assert event_countries_for("EURUSD") == ["USD", "EUR"]
    assert event_countries_for("GBPUSD") == ["USD", "GBP"]
    assert event_countries_for("USDJPY") == ["USD", "JPY"]
    assert event_countries_for("AUDUSD") == ["USD", "AUD"]
    assert event_countries_for("GOLD") == ["USD"]
    assert event_countries_for("UNKNOWN_INSTRUMENT") == ["USD"]


def test_usda_instruments_are_grains() -> None:
    assert set(USDA_INSTRUMENTS) == {"Corn", "Wheat", "Soybean"}


def test_sidecar_suffix_matches_between_writer_and_reader() -> None:
    """CLI (skriver) og endpoint (leser) må være enige om sidecar-navnet."""
    from bedrock.cli.signals_all import LAST_RUN_SIDECAR_SUFFIX as writer_suffix
    from bedrock.signal_server.endpoints.bot import LAST_RUN_SIDECAR_SUFFIX as reader_suffix

    assert writer_suffix == reader_suffix == ".last_run.json"


# ---------------------------------------------------------------------------
# Review-funn 2026-09-05: globale events, tie-break, kalender-cache
# ---------------------------------------------------------------------------


def test_global_country_event_blackouts_every_instrument(tmp_path: Path) -> None:
    """Jackson Hole/OPEC lagres med country 'ALL'/'All' — gjelder alle."""
    store = FakeStore([_event(20, country="All", title="Jackson Hole Symposium")])
    gs = build_global_state(store, NOW, _cfg(tmp_path))
    assert set(gs["event_blackout"]) == {"GOLD", "EURUSD", "GBPUSD", "Corn", "SPX500"}
    assert gs["event_blackout"]["GOLD"]["event"] == "Jackson Hole Symposium"
    # Spørringen ba om de globale landene også
    assert {"ALL", "All"} <= set(store.calls[0]["countries"])


def test_co_timed_events_report_headline_first(tmp_path: Path) -> None:
    store = FakeStore(
        [
            _event(30, title="Average Hourly Earnings m/m"),
            _event(30, title="Non-Farm Employment Change"),
            _event(30, title="Unemployment Rate"),
            _event(45, title="ISM Services PMI"),
        ]
    )
    gs = build_global_state(
        store, NOW, _cfg(tmp_path, bot_whitelist_path=_whitelist(tmp_path, ["GOLD"]))
    )
    info = gs["event_blackout"]["GOLD"]
    assert info["minutes_away"] == 30
    assert info["event"].startswith("Non-Farm Employment Change + ")
    assert "ISM Services PMI" not in info["event"]


def test_usda_calendar_reloaded_when_file_changes(tmp_path: Path) -> None:
    """load_usda_calendar cacher per prosess; serveren lever i uker, så
    fil-endringer må plukkes opp uten restart (mtime-sjekk)."""
    import os

    cal = _usda_calendar(tmp_path, [])
    cfg = _cfg(tmp_path, bot_whitelist_path=_whitelist(tmp_path, ["Corn"]), usda_calendar_path=cal)
    assert build_global_state(FakeStore([]), NOW, cfg)["usda_blackout"] == {}
    # Skriv ny kalender med rapport om 1 t, sett mtime tydelig fremover
    cal.write_text(
        yaml.safe_dump({"wasde": [(NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")]})
    )
    st = cal.stat()
    os.utime(cal, (st.st_atime + 10, st.st_mtime + 10))
    gs = build_global_state(FakeStore([]), NOW, cfg)
    assert gs["usda_blackout"]["Corn"]["report"] == "wasde"


def test_negative_window_rejected_by_config() -> None:
    import pytest

    with pytest.raises(ValueError):
        ServerConfig(event_blackout_after_min=-1)
    with pytest.raises(ValueError):
        ServerConfig(usda_blackout_hours_before=-0.5)
