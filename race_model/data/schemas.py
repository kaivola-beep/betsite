"""Pydantic schemas for historical race records and live race cards.

A ``Start`` is a single (horse, race) pair — the natural unit for both
training data and feature engineering. ``race_id`` groups starts into
races; ``race_date`` drives time-respecting validation.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Start(BaseModel):
    """One horse in one race (historical or upcoming)."""

    model_config = ConfigDict(populate_by_name=True)

    race_id: str
    race_date: date
    track: Optional[str] = None
    distance_m: Optional[int] = None
    start_type: Optional[str] = None
    race_class: Optional[str] = None
    track_condition: Optional[str] = None

    program_number: int
    horse_id: str
    driver_id: Optional[str] = None
    trainer_id: Optional[str] = None
    post_position: Optional[int] = None
    carried_weight_kg: Optional[float] = None

    # Recent form (arrays indexed most-recent-first)
    prior_finishes: list[int] = Field(default_factory=list)
    prior_km_times: list[float] = Field(default_factory=list)
    prior_earnings: list[float] = Field(default_factory=list)
    prior_opponent_strengths: list[float] = Field(default_factory=list)

    days_since_last_start: Optional[int] = None
    gallop_risk: Optional[float] = None          # 0-1 prior probability of breaking stride
    speed_rating: Optional[float] = None
    class_rating: Optional[float] = None
    stamina_rating: Optional[float] = None
    equipment_change: Optional[bool] = None
    shoeing_change: Optional[bool] = None

    # Market information (optional, used by the 'with_market' pipeline)
    market_share: Optional[float] = Field(None, ge=0.0, le=1.0)
    published_odds: Optional[float] = Field(None, gt=1.0)

    # Ground truth — present for historical data only
    finished_position: Optional[int] = None
    did_not_finish: bool = False

    def is_winner(self) -> bool:
        return self.finished_position == 1


class RaceSummary(BaseModel):
    race_id: str
    race_date: date
    track: Optional[str] = None
    distance_m: Optional[int] = None
    start_type: Optional[str] = None
    n_starters: int
