"""Pydantic schemas describing Toto races, horses, pools and tickets.

These types define the contract between the ingestion layer and the rest of
the system. They deliberately mix required (``...``) fields with optional
ones so that the system remains usable with incomplete data, the common case
in practice.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StartType(str, Enum):
    VOLT = "volt"
    AUTO = "auto"
    FLYING = "flying"
    OTHER = "other"


class Horse(BaseModel):
    """A single runner in a race."""

    model_config = ConfigDict(populate_by_name=True)

    program_number: int = Field(..., description="Ohjelmanumero in the race.")
    name: str
    driver: Optional[str] = None
    trainer: Optional[str] = None
    post_position: Optional[int] = None

    # Recent form (most recent first)
    recent_finishes: list[int] = Field(default_factory=list)
    recent_kilometer_times: list[float] = Field(
        default_factory=list,
        description="Recent km times in seconds (e.g. 77.8 for 1:17.8).",
    )
    recent_earnings: list[float] = Field(default_factory=list)

    # Rated metrics (optional, typically supplied by ingestion layer)
    speed_rating: Optional[float] = None
    class_rating: Optional[float] = None
    stamina_rating: Optional[float] = None
    gallop_risk: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Probability of breaking stride."
    )
    days_since_last_start: Optional[int] = None
    equipment_change: Optional[bool] = None
    shoeing_change: Optional[bool] = None

    # Market information (if available)
    pool_percentage: Optional[float] = Field(
        None,
        ge=0.0,
        le=100.0,
        description="Veikkaus Voittaja-pool share in percent (0-100).",
    )
    published_odds: Optional[float] = Field(None, gt=1.0)

    # Ground truth (only set for historical data used in training)
    finished_position: Optional[int] = None
    did_not_finish: bool = False

    @field_validator("recent_kilometer_times", "recent_earnings", mode="before")
    @classmethod
    def _filter_none(cls, v):  # noqa: D401
        if v is None:
            return []
        return [x for x in v if x is not None]


class Race(BaseModel):
    """A single Toto race (lähtö)."""

    race_id: str
    race_number: int
    track: str
    distance_m: int
    start_type: StartType = StartType.VOLT
    race_class: Optional[str] = None
    surface: Optional[str] = None
    weather: Optional[str] = None
    track_condition: Optional[str] = None
    horses: list[Horse]

    def n_runners(self) -> int:
        return len([h for h in self.horses if not h.did_not_finish])


class RaceCard(BaseModel):
    """A collection of races belonging to one Toto-product evening."""

    product: str = Field(..., description="E.g. 'toto75', 'toto76', 'toto4', 'toto5'.")
    date: str
    venue: str
    races: list[Race]
    jackpot: float = Field(
        0.0,
        ge=0.0,
        description="Carry-over jackpot in EUR (0 if none).",
    )
    total_pool: float = Field(
        0.0,
        ge=0.0,
        description="Expected total EUR stakes in the combination pool.",
    )
    takeout: Optional[float] = Field(
        None,
        ge=0.0,
        le=0.5,
        description="Product takeout (house edge). Falls back to config default.",
    )

    def legs(self) -> list[Race]:
        """The races that form the Toto combination (in order)."""
        return list(self.races)


class PoolShare(BaseModel):
    """Observed or estimated pool share for a single horse in a single leg."""

    race_id: str
    program_number: int
    share: float = Field(..., ge=0.0, le=1.0)


class Ticket(BaseModel):
    """A generated Toto ticket."""

    selections: list[list[int]] = Field(
        ..., description="For each leg, the set of program numbers chosen."
    )
    stake: float = Field(..., gt=0.0)
    expected_value: float = 0.0
    hit_probability: float = 0.0
    uniqueness: float = 0.0
    rationale: str = ""

    def n_combinations(self) -> int:
        n = 1
        for sel in self.selections:
            n *= max(len(sel), 1)
        return n
