# Pull Request

## Hva endrer denne PR-en?

<!-- Én setning — hvilken konkret atferd eller modul endres? -->

## Hvorfor?

<!-- Kontekst/motivasjon. Lenk til PLAN.md-fase hvis relevant. -->

## Fase og scope

- [ ] PR tilhører en konkret fase (angi nummer: _____ )
- [ ] Scope matcher det som er planlagt i `PLAN.md`
- [ ] Ingen scope-creep utover branch-navnet

## Review-sjekkliste

- [ ] CI er grønn (ruff, pyright, pytest)
- [ ] Logiske tester dekker den nye atferden (ikke bare unit-tester)
- [ ] `STATE.md` er oppdatert (nyeste session-entry + current state)
- [ ] Eventuelle nye drivere er dokumentert i `docs/driver_authoring.md`
- [ ] Eventuelle nye YAML-konvensjoner er dokumentert i `docs/rule_authoring.md`
- [ ] Ingen hemmeligheter i diff (gitleaks grønn)
- [ ] Ingen hardkodede terskler — bruk `config/*.yaml` + Pydantic-validering
- [ ] `PLAN.md` er oppdatert hvis arkitektur er endret

## Test-evidens

<!-- Lim inn: pytest-output, benchmark-resultat, eller før/etter signal-diff -->

## Open questions / follow-ups

<!-- Ting som ikke ble gjort i denne PR-en men som er notert for senere -->

---

🤖 PR generated/assisted by Claude Code. Review before merging.
