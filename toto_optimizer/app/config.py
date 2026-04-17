"""Configuration for the Toto optimizer.

Central place for tunable parameters. All settings can be overridden via
environment variables prefixed with TOTO_ (e.g. TOTO_DEFAULT_TAKEOUT=0.15).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Global configuration settings."""

    model_config = SettingsConfigDict(env_prefix="TOTO_", env_file=".env", extra="ignore")

    # --- Pool / payout model ----------------------------------------------
    default_takeout: float = Field(
        0.25,
        description=(
            "Default takeout (house edge) for Toto games. Veikkaus' takeout "
            "on Toto products historically sits in the 12-30 % range depending "
            "on product. Adjust per-product if known."
        ),
    )
    shin_max_iter: int = 200
    shin_tol: float = 1e-9

    # --- Probability model ------------------------------------------------
    pl_ridge: float = Field(1e-3, description="L2 ridge penalty for Plackett-Luce fit.")
    pl_max_iter: int = 300
    pl_tol: float = 1e-8

    calibration_method: str = Field(
        "isotonic",
        description="'isotonic' or 'platt' (sigmoid). Isotonic needs >=50 samples.",
    )
    ensemble_weights: dict[str, float] = Field(
        default_factory=lambda: {"plackett_luce": 0.6, "market_anchor": 0.4},
        description=(
            "Default ensemble weights between a purely model-based prob and "
            "the market (pool-implied, debiased) prob. Market anchor is a "
            "strong regulariser when form data is sparse."
        ),
    )

    # --- Optimizer --------------------------------------------------------
    default_budget: float = 20.0
    default_stake_unit: float = 0.10
    jackpot_weight_gamma: float = Field(
        0.5,
        description="Exponent on the uniqueness factor in the jackpot objective.",
    )
    beam_width: int = 64
    monte_carlo_pool_size: int = 10_000

    # --- Simulation -------------------------------------------------------
    default_n_simulations: int = 5_000
    random_seed: int = 42

    # --- Paths ------------------------------------------------------------
    sample_dir: Path = ROOT / "data" / "sample"


SETTINGS = Settings()
