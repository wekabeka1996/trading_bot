from pydantic import BaseModel

class GlobalSettings(BaseModel):
    max_notional_per_trade: float = 25.0
    margin_limit_pct: float = 0.40
