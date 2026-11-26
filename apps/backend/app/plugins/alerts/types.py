from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypedDict


Direction = Literal["above", "below"]


class NewRule(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    symbol: str = Field(pattern=r"^[0-9]{6}$")
    direction: Direction
    target: float = Field(gt=0, le=999999.99, allow_inf_nan=False)

    @field_validator("target")
    @classmethod
    def whole_cents(cls, value: float) -> float:
        if Decimal(str(value)).as_tuple().exponent < -2:
            raise ValueError("目标价最多保留两位小数")
        return value


class RuleState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    enabled: bool


class Rule(TypedDict):
    id: int
    symbol: str
    direction: Direction
    target: float
    enabled: bool


class AlertEvent(TypedDict):
    id: int
    ruleId: int | None
    symbol: str
    direction: Direction
    target: float
    price: float
    quotedAt: str


class AlertsPage(TypedDict):
    rules: list[Rule]
    events: list[AlertEvent]


class CheckSummary(TypedDict):
    rules: int
    evaluated: int


class CheckedPage(AlertsPage):
    check: CheckSummary
