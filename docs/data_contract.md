# Data-kontrakt — signal-schema

Stub. Utfylles i Fase 1 når `src/bedrock/signals/schema.py` implementeres som
Pydantic v2-modell.

## Prinsipp

**Signal-schema v1 er låst.** Eksisterende bot leser v1-felter og skal ikke brekkes.
Nye felter legges i `extras: dict[str, Any]`.

## v1-felter (påkrevd, låst)

```
id: str                              # sig_abc123
instrument: str                      # "Gold"
direction: Literal["bull", "bear"]
horizon: Literal["SCALP", "SWING", "MAKRO"]
grade: Literal["A+", "A", "B", "C", "WATCHLIST"]
score: float
max_score: float                     # 4.2/5.0/5.2 financial, 18 agri
score_pct: float                     # score / max_score
source: Literal["technical", "agri_fundamental"]
created_at: datetime
ttl_minutes: int

setup:
  entry_zone: tuple[float, float]
  alert_level: float                 # preferred entry
  stop: float
  t1: float | None                   # None for MAKRO (trailing only)
  t2: float | None
  rr_t1: float | None
  atr_est: float

driver_groups: dict[str, DriverGroup]  # full explain
data_quality: Literal["fresh", "degraded", "stale", "missing"]
quality_notes: list[str]

correlation_group: str
horizon_config: dict[str, Any]       # bot-spesifikke parametre per horisont

extras: dict[str, Any]               # åpent for eksperimenter
```

Full struktur og validering: kommer i Fase 1.
