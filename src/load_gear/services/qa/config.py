"""Global QA configuration (admin-tunable thresholds)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class QAConfig:
    """QA threshold parameters. Mutable at runtime via admin API."""

    min_kw: float = 0.0
    max_kw: float = 10000.0
    max_jump_kw: float = 5000.0
    top_n_peaks: int = 10
    min_completeness_pct: float = 95.0
    max_gap_duration_min: int = 180

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> QAConfig:
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# Singleton config instance
_config = QAConfig()


def get_qa_config() -> QAConfig:
    """Get the current QA config."""
    return _config


def update_qa_config(updates: dict) -> QAConfig:
    """Update QA config with new values. Returns updated config."""
    global _config
    current = _config.to_dict()
    current.update({k: v for k, v in updates.items() if k in current})
    _config = QAConfig.from_dict(current)
    return _config


def reset_qa_config() -> QAConfig:
    """Reset to defaults."""
    global _config
    _config = QAConfig()
    return _config
