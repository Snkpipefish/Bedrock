"""Tester for cache-skip i `bedrock signals-all` (session 146).

Intra-day-timer fyrer hvert 5. min. ~95 % av kjøringene produserer
identiske decision-relevante entries (kun timestamps `first_seen` /
`last_updated` bumpes). `_write_if_changed` strippes timestamps og
sammenligner — hopper over disk-IO + bot-poll-trigger ved no-op.
"""

from __future__ import annotations

import json
from pathlib import Path

from bedrock.cli.signals_all import _strip_volatile, _write_if_changed


def test_strip_volatile_removes_setup_timestamps() -> None:
    entries = [
        {
            "instrument": "Gold",
            "score": 7.5,
            "setup": {
                "setup_id": "abc123",
                "first_seen": "2026-05-02T15:58:45Z",
                "last_updated": "2026-05-02T15:58:45Z",
                "setup": {"entry": 2050.0, "sl": 2040.0},
            },
        }
    ]
    stripped = _strip_volatile(entries)
    assert "first_seen" not in stripped[0]["setup"]
    assert "last_updated" not in stripped[0]["setup"]
    # Ikke-volatile felter bevart
    assert stripped[0]["setup"]["setup_id"] == "abc123"
    assert stripped[0]["setup"]["setup"]["entry"] == 2050.0
    assert stripped[0]["score"] == 7.5


def test_strip_volatile_handles_no_setup() -> None:
    entries = [{"instrument": "Gold", "score": 7.5, "setup": None}]
    stripped = _strip_volatile(entries)
    assert stripped[0]["setup"] is None


def test_strip_volatile_handles_missing_setup_key() -> None:
    entries = [{"instrument": "Gold", "score": 7.5}]
    stripped = _strip_volatile(entries)
    assert "setup" not in stripped[0]


def test_write_if_changed_writes_when_file_does_not_exist(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    entries = [{"instrument": "Gold", "score": 7.5}]
    written = _write_if_changed(path, entries)
    assert written is True
    assert path.exists()
    assert json.loads(path.read_text()) == entries


def test_write_if_changed_skips_when_decision_state_identical(tmp_path: Path) -> None:
    """Samme entries med BARE forskjellige timestamps → skip."""
    path = tmp_path / "out.json"
    e1 = [
        {
            "instrument": "Gold",
            "score": 7.5,
            "setup": {
                "setup_id": "abc",
                "first_seen": "2026-05-02T15:00:00Z",
                "last_updated": "2026-05-02T15:00:00Z",
                "setup": {"entry": 2050.0},
            },
        }
    ]
    _write_if_changed(path, e1)
    mtime_before = path.stat().st_mtime_ns
    # Samme entries men bumpede timestamps (som intraday-regen ville produsert)
    e2 = [
        {
            "instrument": "Gold",
            "score": 7.5,
            "setup": {
                "setup_id": "abc",
                "first_seen": "2026-05-02T15:05:00Z",  # 5 min senere
                "last_updated": "2026-05-02T15:05:00Z",
                "setup": {"entry": 2050.0},
            },
        }
    ]
    written = _write_if_changed(path, e2)
    assert written is False, "Identisk decision-state → skal hoppe over skriving"
    assert path.stat().st_mtime_ns == mtime_before, "mtime skal bevares ved skip"


def test_write_if_changed_writes_when_score_changes(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    e1 = [{"instrument": "Gold", "score": 7.5, "setup": None}]
    _write_if_changed(path, e1)
    e2 = [{"instrument": "Gold", "score": 8.0, "setup": None}]  # score endret
    written = _write_if_changed(path, e2)
    assert written is True
    assert json.loads(path.read_text())[0]["score"] == 8.0


def test_write_if_changed_writes_when_entry_count_changes(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    e1 = [{"instrument": "Gold", "score": 7.5, "setup": None}]
    _write_if_changed(path, e1)
    e2 = [
        {"instrument": "Gold", "score": 7.5, "setup": None},
        {"instrument": "Silver", "score": 6.0, "setup": None},
    ]
    written = _write_if_changed(path, e2)
    assert written is True


def test_write_if_changed_writes_when_existing_file_corrupt(tmp_path: Path) -> None:
    """Korrupt JSON i existing-fil skal ikke krasje — bare skrive på nytt."""
    path = tmp_path / "out.json"
    path.write_text("{ not valid json")
    entries = [{"instrument": "Gold", "score": 7.5}]
    written = _write_if_changed(path, entries)
    assert written is True
    assert json.loads(path.read_text()) == entries
