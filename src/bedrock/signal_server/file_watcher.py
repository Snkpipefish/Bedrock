"""File-watcher + event-broker for SSE-pushing til UI.

Mål 2 i `docs/plan_event_driven_signals_and_ui.md`. Erstatter UI-ens
30-sek-polling med push-events når relevante filer endrer seg.

Design (forenklet vs plan-doc):
- **Ingen `watchdog`-dep** — én bakgrunnstråd som stat'er N filer hver
  sekund og sammenligner mtime mot forrige iterasjon. ≤2-sek latency
  (planens success-criterion). Sparer en dep + er trivialt å teste.
- **Pub/sub-broker** — sentral set av per-client `queue.Queue`.
  Watcher-tråden pusher events til alle køer.
- **Daemon-tråd** — stopper automatisk med prosessen. Eksplisitt
  `stop()` for tester.

`EventBroker` er thread-safe og lever på `app.extensions[
"bedrock_event_broker"]`. SSE-endpoint i `endpoints/ui.py` registrerer
sin egen kø, lytter blocking, og sender meldinger.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileEvent:
    """Én file-changed-event. `event_type` styrer SSE-event-name."""

    event_type: str  # f.eks. "trade_log_changed", "signals_changed"
    path: str  # absolutt sti
    mtime: float


class EventBroker:
    """Thread-safe pub/sub for FileEvent.

    Bruksmønster:
        broker = EventBroker()
        broker.publish(FileEvent(...))  # fra watcher-tråd
        # I SSE-endpoint:
        with broker.subscribe() as q:
            while True:
                event = q.get(timeout=...)
                yield format_sse(event)

    `subscribe()` returnerer en context manager som registrerer en kø
    ved `__enter__` og av-registrerer ved `__exit__` — sikrer ingen
    lekkede køer ved client-disconnect.
    """

    def __init__(self, *, max_queue_size: int = 100) -> None:
        self._subscribers: set[queue.Queue[FileEvent]] = set()
        self._lock = threading.Lock()
        self._max_queue_size = max_queue_size

    def publish(self, event: FileEvent) -> None:
        """Send event til alle aktive subscribers. Drop på full kø.

        Full kø = klient har ikke konsumert raskt nok (ofte zombie-
        connection). Vi dropper heller enn å blokkere watcher-tråden.
        """
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                _log.warning("event-queue full, dropping event for slow subscriber")

    def subscribe(self) -> _Subscription:
        """Returner context manager som gir en dedikert kø."""
        return _Subscription(self)

    def _register(self, q: queue.Queue[FileEvent]) -> None:
        with self._lock:
            self._subscribers.add(q)

    def _unregister(self, q: queue.Queue[FileEvent]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def subscriber_count(self) -> int:
        """Antall aktive subscribers (for tests + observability)."""
        with self._lock:
            return len(self._subscribers)


class _Subscription:
    """Context manager som registrerer + av-registrerer en kø."""

    def __init__(self, broker: EventBroker) -> None:
        self._broker = broker
        self.queue: queue.Queue[FileEvent] = queue.Queue(maxsize=broker._max_queue_size)

    def __enter__(self) -> queue.Queue[FileEvent]:
        self._broker._register(self.queue)
        return self.queue

    def __exit__(self, *_exc: object) -> None:
        self._broker._unregister(self.queue)


@dataclass(frozen=True)
class WatchTarget:
    """Én fil + hvilken event-type den genererer ved mtime-endring."""

    path: Path
    event_type: str


class FileWatcher:
    """Bakgrunnstråd som overvåker N filer for mtime-endringer.

    Default poll-interval 1 sek. Endring → publiser FileEvent på broker.
    Manglende fil → `mtime=0.0` (ingen event publiseres før fila dukker
    opp og får mtime > 0).
    """

    def __init__(
        self,
        broker: EventBroker,
        targets: list[WatchTarget],
        *,
        poll_interval_sec: float = 1.0,
    ) -> None:
        self._broker = broker
        self._targets = targets
        self._poll_interval = poll_interval_sec
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Initial mtime-snapshot ved konstruksjon. Sikrer at hverken
        # poll_once() (tester) eller den første run-iterasjonen publiserer
        # spurious "endret fra 0.0 → faktisk mtime"-events for filer som
        # allerede eksisterer ved boot.
        self._last_mtimes: dict[str, float] = {
            str(t.path): self._safe_mtime(t.path) for t in self._targets
        }

    def start(self) -> None:
        """Start bakgrunnstråden. Idempotent — kall flere ganger er no-op."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="bedrock-file-watcher",
            daemon=True,
        )
        self._thread.start()
        _log.info("FileWatcher startet med %d targets", len(self._targets))

    def stop(self, timeout: float = 2.0) -> None:
        """Be tråden om å avslutte og vent inntil `timeout` sekunder."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def poll_once(self) -> list[FileEvent]:
        """Én iterasjon — returner events som ble publisert.

        Eksponert primært for tester (deterministisk: ingen sleep).
        """
        published: list[FileEvent] = []
        for target in self._targets:
            key = str(target.path)
            current = self._safe_mtime(target.path)
            previous = self._last_mtimes.get(key, 0.0)
            if current > 0.0 and current != previous:
                event = FileEvent(
                    event_type=target.event_type,
                    path=key,
                    mtime=current,
                )
                self._broker.publish(event)
                published.append(event)
                self._last_mtimes[key] = current
            elif current == 0.0 and previous > 0.0:
                # Fila forsvant — oppdater snapshot men publiser ikke
                # (UI-sider takler tom data via egne fallback).
                self._last_mtimes[key] = 0.0
        return published

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                _log.exception("FileWatcher iteration feilet")
            self._stop_event.wait(timeout=self._poll_interval)

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        """Returner mtime eller 0.0 hvis fila ikke finnes / ikke lesbar."""
        try:
            return path.stat().st_mtime
        except (FileNotFoundError, PermissionError, OSError):
            return 0.0


__all__ = [
    "EventBroker",
    "FileEvent",
    "FileWatcher",
    "WatchTarget",
]
