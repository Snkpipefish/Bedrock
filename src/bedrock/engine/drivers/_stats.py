"""Rene statistikk-helpers for COT-baserte drivere.

Port av cot-explorers `cot_analytics.py` (rank_percentile + rolling_z),
verifisert i produksjon gjennom flere års bruk. Modulen er privat
(`_`-prefix) — kun konsumert av drivere i `positioning.py`.

Begge funksjonene returnerer ``None`` ved utilstrekkelig historikk
(mindre enn ``MIN_OBS_FOR_PCTILE``) slik at caller kan rapportere
graceful 0.0 + log.
"""

from __future__ import annotations

from collections.abc import Sequence

# Minimumshistorikk for at percentile/z-score skal være pålitelig.
# Tilsvarer ~6 måneder ukentlige COT-rapporter.
MIN_OBS_FOR_PCTILE = 26


def rank_percentile(current: float, history: Sequence[float]) -> float | None:
    """Rank-basert percentile 0-100 av ``current`` blant ``history``.

    Returnerer andelen historiske observasjoner som er ≤ ``current``,
    skalert til 0-100.

    Returnerer ``None`` hvis:
    - ``current`` er ``None``
    - ``history`` er ``None`` eller har færre enn ``MIN_OBS_FOR_PCTILE``
      ikke-None observasjoner

    Eksempel:
        ``rank_percentile(75, [10, 20, 30, ..., 100])`` → 75.0
    """
    if current is None or history is None:
        return None
    clean = [v for v in history if v is not None]
    if len(clean) < MIN_OBS_FOR_PCTILE:
        return None
    below_or_equal = sum(1 for v in clean if v <= current)
    return round(100 * below_or_equal / len(clean), 1)


def rolling_z(current: float, history: Sequence[float]) -> float | None:
    """Robust z-score basert på median + MAD (ikke mean/std).

    MAD (median absolute deviation) tåler fat-tails og outliers bedre
    enn standardavvik. Skaleringen 1.4826 gjør MAD ekvivalent med
    standardavvik under normalfordeling.

    Returnerer ``None`` hvis:
    - ``current`` er ``None``
    - ``history`` har færre enn ``MIN_OBS_FOR_PCTILE`` observasjoner
    - MAD er 0 (alle historiske verdier identiske)

    Eksempel:
        ``rolling_z(2.5, [normal-fordelt rundt 0])`` → ~2.5
    """
    if current is None or history is None:
        return None
    clean = [v for v in history if v is not None]
    if len(clean) < MIN_OBS_FOR_PCTILE:
        return None
    s = sorted(clean)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    devs = sorted(abs(v - median) for v in clean)
    mad = devs[n // 2] if n % 2 else (devs[n // 2 - 1] + devs[n // 2]) / 2
    if mad == 0:
        return None
    return round((current - median) / (1.4826 * mad), 2)


__all__ = ["MIN_OBS_FOR_PCTILE", "rank_percentile", "rolling_z"]
