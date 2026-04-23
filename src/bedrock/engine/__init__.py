"""Engine — scoring-motor for Bedrock.

Én `Engine`-klasse (se `engine.py`) orkestrerer scoring for begge asset-klasser.
Aggregator-valg (`weighted_horizon` for financial, `additive_sum` for agri)
styres via YAML-reglene. Se `docs/decisions/001-one-engine-two-aggregators.md`.
"""
