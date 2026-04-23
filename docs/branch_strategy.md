# Branch-strategi

## Oversikt

- `main` = produksjon. Beskyttet, kun PR + squash-merge.
- Feature-branches = alt arbeid. Push daglig til GitHub.
- Branch-navnekonvensjon håndheves via PR-tittel-review (ikke automatisert).

## Branch-typer og navnekonvensjon

```
feat/<scope>-<kort-beskrivelse>      Ny funksjonalitet
fix/<scope>-<kort-beskrivelse>       Bug-fix
refactor/<scope>-<kort-beskrivelse>  Refaktor uten atferds-endring
perf/<scope>-<kort-beskrivelse>      Ytelses-forbedring
docs/<kort-beskrivelse>              Bare dokumentasjon
chore/<kort-beskrivelse>             CI, deps, build
config/<instrument-eller-system>     YAML-endringer

Scope = samme som commit-scope (engine, bot, fetch-cot, ...)
Bruk bindestrek, ikke understrek. Små bokstaver.
```

Eksempler:

```
feat/engine-core
feat/drivers-sma200-momentum
feat/setups-level-detector
fix/bot-agri-tp-override
refactor/bot-split-into-modules
docs/rule-authoring-examples
config/gold-swing-tune
chore/bump-ruff-to-0.7
```

## Flyt for en oppgave

```bash
# 1. Start fra oppdatert main
git checkout main
git pull

# 2. Opprett branch
git checkout -b feat/engine-core

# 3. Arbeid. Commit logisk atomisk.
git add src/bedrock/engine/engine.py tests/logical/test_engine.py
git commit -m "feat(engine): implement score() entry-point with registry dispatch"

# 4. Push daglig (selv om WIP)
git push -u origin feat/engine-core

# 5. Når oppgaven er ferdig — opprett PR
gh pr create --base main \
  --title "feat(engine): implement score() entry-point with registry dispatch" \
  --body-file .github/pull_request_template.md

# 6. Vent på CI grønn, review
# 7. Squash-merge via GitHub UI eller:
gh pr merge --squash --delete-branch

# 8. Lokal cleanup
git checkout main
git pull
git branch -d feat/engine-core
```

## Regler

- **Push minimum én gang per dag.** Gammel laptop kan feile — lokal-bare arbeid er risiko.
- **Branch-levetid < 1 uke.** Lange branches drifter. Hvis en oppgave tar > 1 uke, bryt den ned.
- **Rebase mot main før PR** hvis main har beveget seg:
  ```bash
  git fetch origin
  git rebase origin/main
  # løs konflikter hvis det kommer
  git push --force-with-lease origin feat/engine-core
  ```
- **Aldri force-push til main.** Kun egne feature-branches.
- **Slett branch etter merge.** `gh pr merge --delete-branch` gjør det automatisk.

## Main-beskyttelse (GitHub-settings)

Sett opp én gang i GitHub UI (`Settings → Branches → Add rule` for `main`):

- ✅ Require pull request before merging
- ✅ Require approvals: 0 (single developer, men fortsatt PR-flyt)
- ✅ Require status checks to pass: `lint-and-test`
- ✅ Require linear history (forbyr merge-commits, tvinger squash eller rebase)
- ✅ Require conversation resolution before merging
- ❌ Do not allow bypassing the above settings

Dette gjør det fysisk umulig å ødelegge main ved et uhell.

## Fase-tagger

Ved fase-slutt, før neste fase starter:

```bash
git checkout main
git pull
git tag -a v0.1.0-fase-1 -m "Engine core + 10 drivere + aggregators ferdig"
git push origin v0.1.0-fase-1
```

Gir rollback-punkt: `git checkout v0.1.0-fase-1` hvis noe feiler senere.

## PR-merge-strategi: squash

Vi bruker **squash-merge** på alle PR-er til main. Grunn:

- Én commit per PR på main = ren historikk
- WIP-commits på branch fjernes i merge
- Lett å revertere: `git revert <squash-commit-hash>` fjerner hele funksjonen

Merge-melding bruker PR-tittelen (som følger commit-konvensjon).

Alternativ (rebase-merge) gir flere commits per PR men samme linearitet. Vi velger
squash for enkelhet. Kan revurderes senere.

## Når du havner i feil tilstand

```bash
# Glemt hvilken branch du er på
git branch --show-current

# Glemt hva som er committed
git log --oneline -10

# Jobbet på feil branch — flytt commits
git log --oneline                     # finn SHA av siste commit
git checkout -b rett/branch           # opprett rett branch
git checkout gammel-branch
git reset --hard HEAD~1               # fjern commit fra gammel (BARE hvis ikke pushet!)

# Commitet noe du ikke skulle — fjern fra branch lokalt (ikke pushet)
git reset --soft HEAD~1               # angre siste commit, behold endringer staged
git reset HEAD~1                      # angre siste commit, behold endringer unstaged

# Commitet hemmelighet — stopp, ikke push, ring inn
# git-filter-repo er svaret; ikke prøv på egen hånd
```

## Når samme fil endres på main og branch (merge-konflikt)

1. `git fetch origin`
2. `git rebase origin/main`
3. Git stopper ved konflikt, viser filer
4. Rediger filene, fjern `<<<< === >>>>`-markører, velg hva som skal bli
5. `git add <fil>`
6. `git rebase --continue`
7. Gjenta til rebase er ferdig
8. `git push --force-with-lease origin <branch>`

`--force-with-lease` er tryggere enn `--force` — feiler hvis noen andre har pushet.
