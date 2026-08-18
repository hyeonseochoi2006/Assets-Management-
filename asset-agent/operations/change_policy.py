import os

from pydantic import BaseModel, Field, model_validator


POLICY_ENV_NAMES = (
    "ASSET_CHANGE_PRICE_WATCH_PCT",
    "ASSET_CHANGE_PRICE_MATERIAL_PCT",
    "ASSET_CHANGE_WEIGHT_WATCH_POINTS",
    "ASSET_CHANGE_WEIGHT_MATERIAL_POINTS",
    "ASSET_CHANGE_QUANTITY_MATERIAL_PCT",
    "ASSET_CHANGE_VALUE_WATCH_PCT",
    "ASSET_CHANGE_VALUE_MATERIAL_PCT",
)


class PortfolioChangePolicy(BaseModel):
    """Operational attention thresholds, not buy/sell or portfolio risk limits."""

    version: str = "portfolio-change-v1"
    price_watch_pct: float = Field(default=3.0, gt=0)
    price_material_pct: float = Field(default=7.0, gt=0)
    weight_watch_points: float = Field(default=2.0, gt=0)
    weight_material_points: float = Field(default=5.0, gt=0)
    quantity_material_pct: float = Field(default=25.0, gt=0)
    position_value_watch_pct: float = Field(default=5.0, gt=0)
    position_value_material_pct: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "PortfolioChangePolicy":
        if self.price_material_pct < self.price_watch_pct:
            raise ValueError("price material threshold must be >= watch threshold")
        if self.weight_material_points < self.weight_watch_points:
            raise ValueError("weight material threshold must be >= watch threshold")
        if self.position_value_material_pct < self.position_value_watch_pct:
            raise ValueError("position value material threshold must be >= watch threshold")
        return self

    @classmethod
    def from_env(cls) -> "PortfolioChangePolicy":
        mapping = {
            "ASSET_CHANGE_PRICE_WATCH_PCT": "price_watch_pct",
            "ASSET_CHANGE_PRICE_MATERIAL_PCT": "price_material_pct",
            "ASSET_CHANGE_WEIGHT_WATCH_POINTS": "weight_watch_points",
            "ASSET_CHANGE_WEIGHT_MATERIAL_POINTS": "weight_material_points",
            "ASSET_CHANGE_QUANTITY_MATERIAL_PCT": "quantity_material_pct",
            "ASSET_CHANGE_VALUE_WATCH_PCT": "position_value_watch_pct",
            "ASSET_CHANGE_VALUE_MATERIAL_PCT": "position_value_material_pct",
        }
        values: dict[str, float] = {}
        for env_name, field_name in mapping.items():
            raw = os.getenv(env_name)
            if raw is None or not raw.strip():
                continue
            try:
                values[field_name] = float(raw)
            except ValueError as exc:
                raise RuntimeError(f"{env_name} must be a positive number") from exc

        try:
            return cls(**values)
        except ValueError as exc:
            raise RuntimeError(f"Invalid portfolio change policy: {exc}") from exc
