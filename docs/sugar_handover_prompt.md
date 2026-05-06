# Handover-prompt for nytt kontekst-vindu — Sukker analytiker-tiltak

Kopier alt under `---` og lim inn som første melding i nytt vindu.

---

Vi har jobbet med sukker-instrumentet og en analytiker-peer-review. **Les disse 3 filene først**, i denne rekkefølgen:

1. `STATE.md` — sub-fase 12.11+ blokken (linje ~102) for kontekst
2. `docs/sugar_analyst_response_2026-05.md` — analytikerens 13 punkter (D1-D8 + C.1-C.5)
3. `docs/sugar_handover_prompt.md` — denne fila for status-tabell

## Hva er allerede gjort (11 av 13 punkter)

| Punkt | Status | Commit/Doc |
|-------|--------|------------|
| D.1 Driver-attribution A SELL | ✅ ENSO-bug funnet | `40b4c8b`, `docs/sugar_attribution_a_sell_2026-05.md` |
| D.2 ANP etanol-paritet driver | ✅ implementert | `c3b2b0c` |
| D.3 Forward-syklus seasonal | ✅ validert (+4.06 Sharpe) | `63e22ca`, `docs/sugar_seasonal_ab_2026-05.md` |
| D.4 DSR + Bonferroni | ✅ A+ BUY PSR=1.0 | `fcd36e1`, `docs/sugar_dsr_correlations_2026-05.md` |
| D.5 ISMA + USDA PSD India | ✅ 16 års historikk | `b58c4e5`, `c94dd55` |
| D.6 Familie-vekt-ablation | ✅ alle 7 kritiske, ingen drop | `docs/sugar_ablation_2026-05.md` |
| D.7 Multi-region weather | ✅ India + Thailand | `b15810d` |
| D.8 Rullerende publish-floor | ✅ analyse ferdig | `b8a7675`, `docs/sugar_rolling_floor_2026-05.md` |
| C.1 Anti-driver positioning | ✅ extreme_flag_soft | `076153a` |
| C.2 Familie-korrelasjon | ✅ ingen \|ρ\|>0.6 | `docs/sugar_dsr_correlations_2026-05.md` |
| C.3 Multiple-testing DSR | ✅ | (samme som D.4) |
| C.5 h=180 outcomes | ✅ backfilled | (DB) |

## Hva GJENSTÅR (4 punkter)

### 1. C.4 grade_thresholds-justering — KRITISK
- Backtest v6 viser A+ BUY n=10 (h=180d) — fortsatt under analytikerens n≥30-krav
- **Oppgave:** Senke A+-cutoff i `config/instruments/sugar.yaml::grade_thresholds.A_plus.min_score` fra 11 til ~9-10. Beregn riktig threshold ved å se på score-distribusjonen i `docs/backtest_sugar_v6_full_2026-05.md` slik at A+ får n≥30 men beholder hit-rate ≥ 65%.
- **Kjør så ny backtest 7** for å verifisere at A+ BUY 180d/270d holder på sweet spot etter cutoff-senkning.

### 2. ANP-formel re-kalibrering
- Validering ga ρ=-0.143 (svak; analytiker krever \|ρ\|≥0.5).
- **Oppgave:** I `src/bedrock/engine/drivers/agronomy.py::ethanol_parity_brl`, eksperimenter med:
  - `anhydrous_factor` 1.05 → 1.10 eller 1.15 (skattetransformasjon)
  - `sugar_kg_per_liter` 1.852 → 1.900 (industri-spread)
  - Eller bytt til wholesale anhydrous via CEPEA/ESALQ hvis API finnes
- **Kjør validering** via `scripts/sugar_anp_validation.py` til ρ < -0.30. Hvis ikke mulig, **dropp driveren** og fjern fra cross-familien.

### 3. OOS 2023 India-forbud-validering
- **Oppgave:** Lag nytt script `scripts/sugar_oos_2023_validation.py` som:
  - Filtrerer SELL-signaler kun i Q1-Q3 2023 (India-eksportforbud-perioden)
  - Sjekker om `usda_psd_yoy(USDA_PSD_INDIA_SUGAR_PROD_KMT)` ga BUY-bias-signal i den perioden
  - Sjekker om multi-region `weather_stress` med India 0.30-vekt gjorde A SELL → svakere
- **Suksess-kriterium:** India-driver må ha gitt mindre A SELL-signaler i 2023 enn baseline.

### 4. Rullerende floor i prod-config
- Analyse ferdig (`docs/sugar_rolling_floor_2026-05.md`) viser at statisk floor=5 er upassende i 2022-2024-regimet.
- **Oppgave:**
  - Bygg en `compute_rolling_floor.py`-rutine som kjører kvartalsvis og oppdaterer `min_score_publish` per direction.
  - Eller: implementer `dynamic_min_score_publish: rolling_5y` i sugar.yaml (krever schema-endring).
  - Test mot 2023 OOS — sjekk at dynamisk floor blokkerte SELL-publisering i den perioden.

## Pågående / klart

- **Bot kjører som user-service** (PID i `systemctl --user status bedrock-bot.service`).
- **Server kjører på port 5100** som user `pc`. UI viser alle 4 nye fetchere riktig.
- **Codespace** `stunning-sniffle-pv459prj4wgh664p` shutdown — start hvis du trenger backtest-CPU.
- **Auto-rebase i post-commit** håndterer worktree/main-konflikter (commit `b8b5dd5`).

## Worktree-info

- **Worktree:** `/home/pc/bedrock/.claude/worktrees/naughty-mendeleev-aa4da0`
- **Branch:** `claude/naughty-mendeleev-aa4da0` (synket med `main`)
- **HEAD:** se `git log -1 --oneline` ved oppstart

## Min anbefalte rekkefølge

1. **Punkt 1 (grade_thresholds)** — raskest, gir umiddelbar n≥30-validering.
2. **Punkt 4 (rullerende floor i prod)** — analyse ferdig, bare implementering.
3. **Punkt 3 (OOS 2023)** — krever ny analyse-skript men ingen ny backtest hvis du bruker eksisterende data.
4. **Punkt 2 (ANP-rekalibrering)** — vurder å droppe hvis 2-3 forsøk gir ρ < -0.30.

Når alle 4 er ferdig: oppdater `STATE.md` og marker sub-fase 12.11+ som **LUKKET**.
