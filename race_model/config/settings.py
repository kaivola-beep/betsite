"""Central configuration. Override with env vars prefixed ``RACE_``.

The defaults target demo data out of the box. For production, adjust the
rolling-window and bootstrap parameters to match data volume.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RACE_", env_file=".env", extra="ignore")

    # --- Modelling --------------------------------------------------------
    pl_ridge: float = 1e-3
    pl_max_iter: int = 300
    pl_tol: float = 1e-8

    boosted_backend: str = Field(
        "auto",
        description="'lightgbm' | 'sklearn' | 'auto' (prefer lightgbm).",
    )
    boosted_max_iter: int = 300
    boosted_learning_rate: float = 0.05
    boosted_max_depth: int | None = 6

    # --- Ensemble ---------------------------------------------------------
    ensemble_weights_no_market: dict[str, float] = Field(
        default_factory=lambda: {"baseline": 0.35, "boosted": 0.65},
    )
    ensemble_weights_with_market: dict[str, float] = Field(
        default_factory=lambda: {"baseline": 0.25, "boosted": 0.45, "market": 0.30},
    )

    # --- Calibration ------------------------------------------------------
    calibration_method: str = Field(
        "temperature",
        description="'temperature', 'isotonic', 'temperature+isotonic', or 'none'.",
    )
    temperature_bounds: tuple[float, float] = (0.25, 4.0)

    # --- Validation -------------------------------------------------------
    walk_forward_folds: int = 5
    walk_forward_min_train: int = 50           # races
    walk_forward_val_size: int = 20            # races
    walk_forward_test_size: int = 20           # races

    # --- Uncertainty ------------------------------------------------------
    bootstrap_n: int = 25
    bootstrap_seed: int = 7

    # --- Paths ------------------------------------------------------------
    sample_dir: Path = ROOT / "data" / "sample"


SETTINGS = Settings()
