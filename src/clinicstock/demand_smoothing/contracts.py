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




@dataclass(frozen=True, slots=True)
class DemandDay:
    sku: str
    store: str
    day: int
    adjusted_units: float


def parse(values: Mapping[str, Any]) -> DemandDay:
    if not isinstance(values, Mapping):
        raise InvalidRow('demand_smoothing', 'EXPECTED_OBJECT')
    sku = text(values, 'sku', 'demand_smoothing.sku')
    store = text(values, 'store', 'demand_smoothing.store')
    day = integer(values, 'day', 0, 10000000, 'demand_smoothing.day')
    adjusted_units = number(values, 'adjusted_units', 0, 100000, 'demand_smoothing.adjusted_units')
    return DemandDay(
        sku=sku,
        store=store,
        day=day,
        adjusted_units=adjusted_units,
    )
