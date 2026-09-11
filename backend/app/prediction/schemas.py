from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.market.schemas import MarketInterval


class Forecast(BaseModel):
    symbol: str
    interval: MarketInterval
    quote_asset: str
    model_version: str
    as_of: datetime
    forecast_for: datetime
    generated_at: datetime
    current_price: float = Field(gt=0, allow_inf_nan=False)
    predicted_price: float = Field(gt=0, allow_inf_nan=False)
    direction: Literal["up", "down"]
    up_probability: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0.5, le=1)
    confidence_kind: str = "uncalibrated_random_forest_probability"
    expected_return: float = Field(gt=-1, allow_inf_nan=False)
    estimated_risk: float = Field(ge=0, allow_inf_nan=False)
    validation_error_p95: float = Field(ge=0, allow_inf_nan=False)
    risk_kind: str = "recent_candle_return_standard_deviation"


class RankingRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=20)
    interval: MarketInterval = "1d"


class RankedForecast(BaseModel):
    forecast: Forecast
    score: float


class RankingResponse(BaseModel):
    items: list[RankedForecast]
    unavailable: dict[str, str]
    score_method: str = "expected_return_times_up_probability_divided_by_risk"
