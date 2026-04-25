"""Tester for ``bedrock.engine.drivers.seasonal``.

Verifiserer at seasonal_stage returnerer riktig score basert på
gjeldende måned. Bruker ``as_of``-param for testbarhet (i stedet for
date.today()).
"""

from __future__ import annotations

from datetime import date

from bedrock.engine.drivers import get

# ---------------------------------------------------------------------------
# seasonal_stage
# ---------------------------------------------------------------------------


def test_seasonal_stage_default_january_low() -> None:
    """Januar skal ha lav score (0.3 i default-NH-grain-kalender)."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {"as_of": "2026-01-15"})
    assert score == 0.3


def test_seasonal_stage_default_july_high() -> None:
    """Juli skal være topp (1.0 — silking/yield-determinerende)."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {"as_of": "2026-07-15"})
    assert score == 1.0


def test_seasonal_stage_default_april_planting() -> None:
    """April skal være planting-start (0.6)."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {"as_of": "2026-04-15"})
    assert score == 0.6


def test_seasonal_stage_custom_calendar() -> None:
    """Brukerstyrt monthly_scores skal overstyre default."""
    fn = get("seasonal_stage")
    custom = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    score = fn(None, "Cotton", {"as_of": "2026-12-15", "monthly_scores": custom})
    assert score == 1.0


def test_seasonal_stage_custom_calendar_summer_zero() -> None:
    """Custom-kalender med juli=0.0 skal returnere 0.0."""
    fn = get("seasonal_stage")
    custom = [0.0] * 12
    score = fn(None, "Cotton", {"as_of": "2026-07-15", "monthly_scores": custom})
    assert score == 0.0


def test_seasonal_stage_invalid_monthly_scores_returns_zero() -> None:
    """Liste med != 12 elementer → 0.0 (graceful)."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {"as_of": "2026-04-15", "monthly_scores": [0.5, 0.5]})
    assert score == 0.0


def test_seasonal_stage_invalid_as_of_returns_zero() -> None:
    """Ugyldig as_of-streng → 0.0 (graceful)."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {"as_of": "ikke-en-dato"})
    assert score == 0.0


def test_seasonal_stage_clips_scores_above_one() -> None:
    """Verdier i monthly_scores > 1.0 skal klippes til 1.0."""
    fn = get("seasonal_stage")
    custom = [99.0] * 12
    score = fn(None, "Corn", {"as_of": "2026-04-15", "monthly_scores": custom})
    assert score == 1.0


def test_seasonal_stage_clips_scores_below_zero() -> None:
    """Negative verdier skal klippes til 0.0."""
    fn = get("seasonal_stage")
    custom = [-5.0] * 12
    score = fn(None, "Corn", {"as_of": "2026-04-15", "monthly_scores": custom})
    assert score == 0.0


def test_seasonal_stage_accepts_date_object() -> None:
    """``as_of`` som ``date``-objekt skal også fungere."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {"as_of": date(2026, 7, 15)})
    assert score == 1.0


def test_seasonal_stage_uses_today_when_no_as_of() -> None:
    """Uten ``as_of`` skal default være date.today() — score skal være gyldig."""
    fn = get("seasonal_stage")
    score = fn(None, "Corn", {})
    assert 0.0 <= score <= 1.0


def test_seasonal_stage_registered() -> None:
    fn = get("seasonal_stage")
    assert fn is not None
