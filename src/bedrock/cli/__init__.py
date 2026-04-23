"""Command-line interface for Bedrock.

Entry-point: `bedrock`-kommandoen (se `pyproject.toml [project.scripts]`).
Implementert som en click-gruppe i `__main__.py` med subkommandoer i
separate moduler (`backfill.py`, etc.).

Kan også kjøres via `python -m bedrock.cli` under utvikling.
"""
