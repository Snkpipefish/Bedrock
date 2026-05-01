# Kickoff-prompt for sub-fase 12.10 (ny session-kontekst)

Lim inn følgende i ny Claude Code-session. Forutsetter at sub-fase
12.9 D6 er lukket først.

---

## START

Vi åpner **sub-fase 12.10 — driver-rebalansering**.

Følg session-start-protokollen i CLAUDE.md:
1. Les CLAUDE.md (auto-lastet)
2. Les STATE.md fra topp til første `---`
3. Les PLAN.md § 22 (sub-fase 12.10) — hele seksjonen for spec
4. Helse-sjekk: `bash scripts/session_health.sh`
5. Bekreft til meg: "Fortsetter på sub-fase 12.10 Bunke 1 (bug-fixer). Helse: [grønn|rød — X]. Blockers: [...]. Jeg starter med [handling]."
6. Vent på godkjenning før koding starter.

## Kontekst

Sub-fase 12.10 er driver-rebalansering på allerede live demo-bot.
Hele 12.10 kjører mot **cTrader demo-konto kun** — ingen live-cutover
før jeg sier OK etter empirisk demo-resultat.

Beslutninger som er låst (ikke diskuter på nytt):
- **Ingen familie-restrukturering.** Beholde flat YAML.
- **Backtest droppet.** All validering mot live-demo.
- **GIE-key** (`BEDROCK_AGSI_API_KEY` i secrets.env) dekker AGSI+/ALSI/IIP.
- **Ingen ADR.** Ingen arkitektoniske skifter.
- **Alle ~67 nye drivere + 13 endringer skal leveres** i 9 bunker per
  PLAN § 22.2.
- **Separat commit per driver/endring** for enkel revert/bisect.
- **Snapshot-baseline regen + grade-distribusjons-rapport etter hver
  bunke**, ikke per commit.
- **Stop-criterion** per § 22.3.

## Bunke 1 — start her

Per § 22.2 Bunke 1 er bug-fixer. Lever i denne rekkefølgen:

1. **Bug-1: COT `released_at`-fix.** Schema-utvidelse på cot_disaggregated/legacy/ice/euronext-tabellene + filter-logikk på 7 drivere (cot_z_score, positioning_mm_pct, cot_ice_mm_pct, cot_euronext_mm_pct, positioning_asset_mgr_pct, positioning_lev_funds_pct, aaii_extreme). Skill mellom `report_date` (data-tidspunkt) og `released_at` (fri 15:30 ET). Driver-filter må bruke released_at.

2. **Bug-2: min_samples-guards.** Drivere som leser fra <100-rader-tabeller skal returnere neutral (0.5) hvis n < min_samples. Berørte: unica_export_change, disease_pressure, export_event_active, comex_stress.

3. **Bug-3: event_distance future-actual verifisering.** Sjekk i kode + i tester at driveren kun leser `forecast`/`previous`-felt før event_ts, ikke `actual`.

Etter Bunke 1: regen snapshot-baseline + sammenlign mot pre-12.10-baseline. Ingen WARN/eskalering hvis ≤5 grade-flips per asset-class. Commit per bug separat. Tag etter Bunke 1: `v0.12.10-bunke1`.

## Arbeids-stil

- Forklar kort hva du gjør før hvert steg, men ikke før-godkjenn lange planer
- Auto-mode er aktivt — utfør, men spør hvis arkitektonisk valg dukker opp som ikke står i PLAN § 22
- Bruk TodoWrite for å spore framgang innen hver bunke
- Snapshot-baseline diff-rapport limes inn i commit-meldingen for hver bunke-tag

## Når du er ferdig med Bunke 1

Stop og rapporter til meg:
- Antall drivere/tabeller berørt
- Grade-flip-distribusjon per asset-class
- Eventuelle anomalier funnet under bug-fix
- Klar-meld for Bunke 2

Ikke gå til Bunke 2 uten min godkjenning.

## SLUTT

---

**Tips:** Hvis du vil bryte midt i en bunke, si "pause Bunke X
ved <commit-hash>" så Claude logger framgang og venter.
