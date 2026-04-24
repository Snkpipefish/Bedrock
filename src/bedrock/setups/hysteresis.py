"""Hysterese + stabilitets-filtre for setup-generator.

Per PLAN § 5.4: generatoren er allerede deterministisk per input
(session 17). Denne modulen legger på konsistens på tvers av
kjøringer — slik at et setup ikke blinker mellom marginale SL/TP-
verdier hver 4. time.

**Mekanismer (PLAN § 5.4):**

1. **Stabilitets-filtre på nivå-valg** (implementert her):
   - Ny SL innenfor `k × ATR` av forrige SL → behold forrige
   - Ny TP innenfor `k × ATR` av forrige TP → behold forrige
   - R:R beregnes på nytt med de stabiliserte verdiene

2. **Hysterese på horisont-tildeling** (utsatt til session 19 siden
   horisont-klassifisering mangler fortsatt)

3. **Determinisme** (allerede oppnådd i session 17 — pure function,
   ingen tilfeldighet, ingen rekkefølge-avhengighet)

**Setup-ID:** stabilt på tvers av kjøringer via deterministisk hash av
`(instrument, direction, horizon)`. Samme "slot" → samme ID, uavhengig
av om entry/SL/TP endrer seg. Gir UI-kontinuitet: kortet for
"Gold BUY SWING" beholder samme ID mens innholdet oppdateres.

**Snapshot-lagring:** helpers i `bedrock.setups.snapshot`. Snapshot er
**kun referanse til forrige tilstand** — ingen lifecycle-state
(watchlist/triggered/active/closed). Bot har sin egen state-maskin per
åpne trade.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from bedrock.setups.generator import Direction, Horizon, Setup


# ---------------------------------------------------------------------------
# Konfigurasjon
# ---------------------------------------------------------------------------


class HysteresisConfig(BaseModel):
    """Parametre for stabilitets-filtre. Defaults matcher PLAN § 5.4.

    - `sl_atr_multiplier=0.3`: behold forrige SL hvis ny SL ligger
      innenfor 0.3×ATR av den
    - `tp_atr_multiplier=0.5`: behold forrige TP hvis ny TP er
      innenfor 0.5×ATR (mer tolerant enn SL fordi TP er lenger unna
      nåpris)
    - `enabled=True`: kan slås av for debugging
    """

    sl_atr_multiplier: float = Field(default=0.3, ge=0.0)
    tp_atr_multiplier: float = Field(default=0.5, ge=0.0)
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Setup-ID
# ---------------------------------------------------------------------------


def compute_setup_id(instrument: str, direction: Direction, horizon: Horizon) -> str:
    """Deterministisk ID fra (instrument, direction, horizon)-slot.

    SHA1-hash truncert til 12 hex-tegn. Samme slot → samme ID, på tvers
    av kjøringer og prosesser. Forskjellige slots → praktisk talt alltid
    forskjellige IDer (kollisjon-sannsynlighet for 12 hex = 2^48 er
    neglisjerbar for vår bruk).

    Entry/SL/TP inngår *ikke* i ID-en — de kan bevege seg innenfor slot
    uten at ID endres, som PLAN § 5.4 krever for UI-kontinuitet.
    """
    key = f"{instrument}:{direction.value}:{horizon.value}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Stabilt setup (Setup + ID + tidsstempel)
# ---------------------------------------------------------------------------


class StableSetup(BaseModel):
    """Et `Setup` med persistable metadata for snapshot-lagring."""

    setup_id: str
    first_seen: datetime
    last_updated: datetime
    setup: Setup

    model_config = ConfigDict(extra="forbid")


class SetupSnapshot(BaseModel):
    """Kjøringstilstand som skrives/leses fra `data/setups/last_run.json`.

    Kun referanse til forrige kjøring — ingen lifecycle-state.
    """

    run_ts: datetime
    setups: list[StableSetup]

    model_config = ConfigDict(extra="forbid")

    def find(
        self,
        instrument: str,
        direction: Direction,
        horizon: Horizon,
    ) -> StableSetup | None:
        """Slå opp forrige tilstand for en gitt slot."""
        target_id = compute_setup_id(instrument, direction, horizon)
        for s in self.setups:
            if s.setup_id == target_id:
                return s
        return None


# ---------------------------------------------------------------------------
# Stabiliserings-funksjon
# ---------------------------------------------------------------------------


def stabilize_setup(
    new_setup: Setup,
    previous: StableSetup | None,
    now: datetime,
    config: HysteresisConfig | None = None,
) -> StableSetup:
    """Bruk hysterese på `new_setup` mot `previous`.

    - Hvis `previous` er `None`: ingen historikk; returnerer nytt
      `StableSetup` med `first_seen = last_updated = now`.
    - Hvis `previous` finnes og ny SL er innenfor `sl_atr_multiplier ×
      atr`: behold forrige SL.
    - Hvis `previous` finnes og ny TP er innenfor `tp_atr_multiplier ×
      atr`: behold forrige TP. (Kun hvis begge TP-er er ikke-None —
      MAKRO-setups har `tp=None` og går rett gjennom.)
    - R:R regnes ut på nytt hvis SL eller TP ble substituert.
    - `first_seen` bevares fra `previous` når slot matcher; `last_updated`
      settes til `now`.

    `config.enabled=False` slår av alle filtre og returnerer `new_setup`
    uendret (nyttig for debugging).
    """
    cfg = config if config is not None else HysteresisConfig()
    setup_id = compute_setup_id(
        new_setup.instrument, new_setup.direction, new_setup.horizon
    )

    if previous is None or not cfg.enabled:
        return StableSetup(
            setup_id=setup_id,
            first_seen=now,
            last_updated=now,
            setup=new_setup,
        )

    # Sanity: forrige slot må matche — ellers har caller gjort en feil
    if previous.setup_id != setup_id:
        raise ValueError(
            f"stabilize_setup: previous.setup_id ({previous.setup_id}) does not "
            f"match new setup's slot ({setup_id}). Did you pass the wrong previous?"
        )

    stable_sl = _stabilize_value(
        new_value=new_setup.sl,
        previous_value=previous.setup.sl,
        buffer=cfg.sl_atr_multiplier * new_setup.atr,
    )

    stable_tp = new_setup.tp
    if new_setup.tp is not None and previous.setup.tp is not None:
        stable_tp = _stabilize_value(
            new_value=new_setup.tp,
            previous_value=previous.setup.tp,
            buffer=cfg.tp_atr_multiplier * new_setup.atr,
        )

    # Bygg stabilisert Setup. Bruker model_copy for å bevare traceability-felter.
    rr_recomputed = _recompute_rr(
        entry=new_setup.entry,
        sl=stable_sl,
        tp=stable_tp,
        direction=new_setup.direction,
    )
    stabilized_setup = new_setup.model_copy(
        update={
            "sl": stable_sl,
            "tp": stable_tp,
            "rr": rr_recomputed,
        }
    )

    return StableSetup(
        setup_id=setup_id,
        first_seen=previous.first_seen,
        last_updated=now,
        setup=stabilized_setup,
    )


def apply_hysteresis_batch(
    new_setups: list[Setup],
    previous_snapshot: SetupSnapshot | None,
    now: datetime,
    config: HysteresisConfig | None = None,
) -> list[StableSetup]:
    """Kjør `stabilize_setup` for en hel batch mot forrige snapshot.

    Oppslag skjer per-slot (instrument, direction, horizon) via
    `SetupSnapshot.find`. Setups som ikke fantes forrige gang får
    `previous=None` og behandles som nye.
    """
    stabilized: list[StableSetup] = []
    for new_setup in new_setups:
        previous: StableSetup | None = None
        if previous_snapshot is not None:
            previous = previous_snapshot.find(
                new_setup.instrument, new_setup.direction, new_setup.horizon
            )
        stabilized.append(stabilize_setup(new_setup, previous, now, config))
    return stabilized


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _stabilize_value(new_value: float, previous_value: float, buffer: float) -> float:
    """Returner `previous_value` hvis `|new - previous| ≤ buffer`, ellers
    `new_value`. `buffer=0` gir alltid ny verdi (ingen hysterese).
    """
    if abs(new_value - previous_value) <= buffer:
        return previous_value
    return new_value


def _recompute_rr(
    entry: float,
    sl: float,
    tp: float | None,
    direction: Direction,
) -> float | None:
    """Reward/Risk-ratio etter substitusjon. None hvis TP er None
    (MAKRO) eller hvis risiko ≤ 0 (defensivt)."""
    if tp is None:
        return None
    if direction == Direction.BUY:
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


__all__ = [
    "HysteresisConfig",
    "StableSetup",
    "SetupSnapshot",
    "compute_setup_id",
    "stabilize_setup",
    "apply_hysteresis_batch",
]
