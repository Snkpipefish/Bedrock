#!/bin/bash
# Installer pre-commit-hooks i en gitt Bedrock-worktree.
#
# Bakgrunn: når Claude jobber i en isolert worktree (git worktree add)
# arver ikke .git/hooks fra hoved-repoet. Pre-commit må re-installeres
# i worktreen før første commit, ellers slipper formattering/lint-feil
# gjennom (jf. session 132 hvor manglende worktree-hooks førte til en
# format-fix-commit).
#
# Bruk:
#   bash scripts/install_precommit_in_worktree.sh /path/to/worktree
#
# Krever: pre-commit installert globalt eller i .venv inne i worktreen.
set -euo pipefail

WORKTREE="${1:?Usage: $0 <worktree-path>}"

if [ ! -d "$WORKTREE" ]; then
  echo "ERROR: worktree-path eksisterer ikke: $WORKTREE" >&2
  exit 1
fi

if [ ! -f "$WORKTREE/.pre-commit-config.yaml" ]; then
  echo "ERROR: .pre-commit-config.yaml mangler i $WORKTREE" >&2
  exit 1
fi

cd "$WORKTREE"

if [ -x ".venv/bin/pre-commit" ]; then
  echo "Bruker .venv/bin/pre-commit i $WORKTREE"
  .venv/bin/pre-commit install
elif command -v pre-commit >/dev/null 2>&1; then
  echo "Bruker globalt pre-commit i PATH"
  pre-commit install
else
  echo "ERROR: pre-commit ikke funnet (verken .venv/bin/pre-commit eller i PATH)" >&2
  echo "Installer med: uv pip install pre-commit (i worktree-venv) eller pipx install pre-commit" >&2
  exit 1
fi

echo "Pre-commit-hooks installert i $WORKTREE/.git/hooks/pre-commit"
