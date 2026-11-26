from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any


class InvalidRow(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}: {code}')
        self.field = field
        self.code = code


def number(row: Mapping, key: str, low: float, high: float, field: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise InvalidRow(field, 'EXPECTED_NUMBER')
    if not low <= value <= high or not math.isfinite(value):
        raise InvalidRow(field, 'OUT_OF_RANGE')
    return float(value)


def integer(row: Mapping, key: str, low: int, high: int, field: str) -> int:
    value = row.get(key)
    if type(value) is not int:
        raise InvalidRow(field, 'EXPECTED_INTEGER')
    if not low <= value <= high:
        raise InvalidRow(field, 'OUT_OF_RANGE')
    return value


def text(row: Mapping, key: str, field: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidRow(field, 'EXPECTED_NONEMPTY_TEXT')
    if len(value.strip()) > 80:
        raise InvalidRow(field, 'TEXT_TOO_LONG')
    return value.strip()


def flag(row: Mapping, key: str, field: str) -> bool:
    value = row.get(key)
    if type(value) is not bool:
        raise InvalidRow(field, 'EXPECTED_FLAG')
    return value


@dataclass(frozen=True, slots=True)
class PurchaseRequest:
    sku: str
    store: str
    pack: int
    case_cost: int
    on_hand: int
    inbound: int
    forecast: float
    buffer: int
    validated: bool
    critical: bool
    cold_capacity: int
    min_term_days: int


def parse(values: Mapping[str, Any]) -> PurchaseRequest:
    if not isinstance(values, Mapping):
        raise InvalidRow('carton_budget', 'EXPECTED_OBJECT')
    sku = text(values, 'sku', 'carton_budget.sku')
    store = text(values, 'store', 'carton_budget.store')
    pack = integer(values, 'pack', 1, 500, 'carton_budget.pack')
    case_cost = integer(values, 'case_cost', 1, 100000, 'carton_budget.case_cost')
    on_hand = integer(values, 'on_hand', 0, 100000, 'carton_budget.on_hand')
    inbound = integer(values, 'inbound', 0, 100000, 'carton_budget.inbound')
    forecast = number(values, 'forecast', 0, 100000, 'carton_budget.forecast')
    buffer = integer(values, 'buffer', 0, 100000, 'carton_budget.buffer')
    validated = flag(values, 'validated', 'carton_budget.validated')
    critical = flag(values, 'critical', 'carton_budget.critical')
    cold_capacity = integer(values, 'cold_capacity', 0, 100000, 'carton_budget.cold_capacity')
    min_term_days = integer(values, 'min_term_days', 1, 360, 'carton_budget.min_term_days')
    return PurchaseRequest(
        sku=sku,
        store=store,
        pack=pack,
        case_cost=case_cost,
        on_hand=on_hand,
        inbound=inbound,
        forecast=forecast,
        buffer=buffer,
        validated=validated,
        critical=critical,
        cold_capacity=cold_capacity,
        min_term_days=min_term_days,
    )
