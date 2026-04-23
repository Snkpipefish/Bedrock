# Git-hooks for Bedrock

Hooks som aktiveres automatisk i denne repoet. Versjoneres i git slik at de
følger med ved klone.

## Aktivering

Ved ny klone, kjør én gang:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/*
```

(Er allerede gjort på utviklings-maskinen.)

## Aktive hooks

### `post-commit` — auto-push etter hver commit

Formål: ingen commits blir kun-lokale. Bruker slipper å huske `git push` før
laptop stenges. Claude Code slipper å håndtere push-disiplin manuelt.

Atferd:
- Etter hver vellykkede commit pushes branch til `origin`
- Hvis branch er ny (ingen upstream): settes upstream automatisk (`push -u`)
- Hvis push feiler (nettverk, GitHub nede, branch-beskyttelse): commit
  BLOKKERES IKKE. Feilmelding vises, detaljer i `/tmp/bedrock-push.log`.
- Hvis detached HEAD eller ingen remote: hopper stille over.

Sikkerhet:
- Main-branch er beskyttet på GitHub — auto-push til main vil bli avvist
  hvis noen ved uhell committer direkte
- Commit er alltid lagret lokalt, aldri tapt pga. auto-push-feil

## Skrive nye hooks

Legg script i denne mappa med samme navn som git-hook (`pre-commit`,
`post-merge`, etc.) og gjør det executable. Ingen ekstra config nødvendig
fordi `core.hooksPath` peker hit.

## Notat om forholdet til `pre-commit`-rammeverket

Vi bruker også [`pre-commit`](https://pre-commit.com) for lint/format/type-check
før commit (se `.pre-commit-config.yaml`). Det er en annen tool enn git-hooks.
De fungerer sammen — pre-commit-rammeverket håndterer *pre*-commit-sjekker,
hooks her håndterer *post*-commit-aksjoner.
