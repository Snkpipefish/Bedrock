"""Tester for EventBroker + FileWatcher (Mål 2 SSE-grunnlag)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from bedrock.signal_server.file_watcher import (
    EventBroker,
    FileEvent,
    FileWatcher,
    WatchTarget,
)

# ---------------------------------------------------------------------------
# EventBroker
# ---------------------------------------------------------------------------


def test_event_broker_publish_to_single_subscriber() -> None:
    broker = EventBroker()
    with broker.subscribe() as q:
        event = FileEvent(event_type="test", path="/x", mtime=1.0)
        broker.publish(event)
        received = q.get(timeout=0.1)
    assert received == event


def test_event_broker_publish_to_multiple_subscribers() -> None:
    broker = EventBroker()
    with broker.subscribe() as q1, broker.subscribe() as q2:
        broker.publish(FileEvent(event_type="t", path="/p", mtime=1.0))
        e1 = q1.get(timeout=0.1)
        e2 = q2.get(timeout=0.1)
    assert e1.path == "/p"
    assert e2.path == "/p"


def test_event_broker_unregisters_on_context_exit() -> None:
    broker = EventBroker()
    assert broker.subscriber_count() == 0
    with broker.subscribe():
        assert broker.subscriber_count() == 1
    assert broker.subscriber_count() == 0


def test_event_broker_no_subscribers_publish_is_noop() -> None:
    broker = EventBroker()
    # Skal ikke kaste — bare være en no-op
    broker.publish(FileEvent(event_type="t", path="/p", mtime=1.0))
    assert broker.subscriber_count() == 0


def test_event_broker_full_queue_drops_event() -> None:
    """Slow subscriber får ikke ta ned watcher-tråden — full kø skal droppe."""
    broker = EventBroker(max_queue_size=2)
    with broker.subscribe() as q:
        for i in range(5):
            broker.publish(FileEvent(event_type="t", path=f"/p{i}", mtime=float(i)))
        # Bare de første 2 nådde fram (max_queue_size=2)
        assert q.qsize() == 2


# ---------------------------------------------------------------------------
# FileWatcher
# ---------------------------------------------------------------------------


def test_file_watcher_publishes_event_on_mtime_change(tmp_path: Path) -> None:
    target_file = tmp_path / "signals.json"
    target_file.write_text("{}")

    broker = EventBroker()
    watcher = FileWatcher(
        broker,
        targets=[WatchTarget(path=target_file, event_type="signals_changed")],
        poll_interval_sec=0.05,
    )

    # Kall poll_once en gang for å snappe initial mtime — ingen events
    # publiseres første gang siden ctor allerede har snapshot.
    initial = watcher.poll_once()
    assert initial == []

    # Endre fila
    time.sleep(0.05)  # garanterer mtime-tick på tregge filsystemer
    target_file.write_text('{"x": 1}')

    published = watcher.poll_once()
    assert len(published) == 1
    assert published[0].event_type == "signals_changed"
    assert published[0].path == str(target_file)
    assert published[0].mtime > 0.0


def test_file_watcher_no_event_when_unchanged(tmp_path: Path) -> None:
    target_file = tmp_path / "signals.json"
    target_file.write_text("{}")

    broker = EventBroker()
    watcher = FileWatcher(
        broker,
        targets=[WatchTarget(path=target_file, event_type="signals_changed")],
    )

    assert watcher.poll_once() == []
    assert watcher.poll_once() == []  # andre poll uten endring → ingen events


def test_file_watcher_handles_missing_file(tmp_path: Path) -> None:
    """Manglende fil skal ikke kaste — bare ingen events."""
    missing = tmp_path / "does_not_exist.json"

    broker = EventBroker()
    watcher = FileWatcher(
        broker,
        targets=[WatchTarget(path=missing, event_type="x")],
    )

    assert watcher.poll_once() == []


def test_file_watcher_publishes_when_missing_file_appears(tmp_path: Path) -> None:
    """Når en fil dukker opp etter watcher-start, skal første sighting trigge event."""
    target = tmp_path / "appears_later.json"

    broker = EventBroker()
    watcher = FileWatcher(
        broker,
        targets=[WatchTarget(path=target, event_type="appeared")],
    )

    assert watcher.poll_once() == []

    target.write_text("{}")
    published = watcher.poll_once()
    assert len(published) == 1
    assert published[0].event_type == "appeared"


def test_file_watcher_start_stop_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "f.json"
    target.write_text("{}")

    broker = EventBroker()
    watcher = FileWatcher(
        broker,
        targets=[WatchTarget(path=target, event_type="t")],
        poll_interval_sec=0.05,
    )

    watcher.start()
    assert watcher.is_alive()
    watcher.start()  # andre kall — no-op
    assert watcher.is_alive()

    watcher.stop()
    assert not watcher.is_alive()
    watcher.stop()  # andre stop — no-op
    assert not watcher.is_alive()


def test_file_watcher_thread_publishes_to_subscriber(tmp_path: Path) -> None:
    """End-to-end: tråd kjører, fil endres, subscriber får event innen ~0.5s."""
    target = tmp_path / "f.json"
    target.write_text("{}")

    broker = EventBroker()
    watcher = FileWatcher(
        broker,
        targets=[WatchTarget(path=target, event_type="changed")],
        poll_interval_sec=0.05,
    )
    watcher.start()
    try:
        with broker.subscribe() as q:
            time.sleep(0.1)  # la tråden ta initial-snapshot
            target.write_text('{"y": 2}')
            event = q.get(timeout=1.0)
        assert event.event_type == "changed"
        assert event.path == str(target)
    finally:
        watcher.stop()


def test_file_event_is_immutable() -> None:
    """FileEvent er frozen dataclass — sikrer trygg deling mellom tråder."""
    event = FileEvent(event_type="t", path="/p", mtime=1.0)
    with pytest.raises(Exception):
        event.event_type = "other"  # type: ignore[misc]
