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
class ValidationDemand:
    sku: str
    store: str
    day: int
    actual: float
    predicted: float
    available: bool


def parse(values: Mapping[str, Any]) -> ValidationDemand:
    if not isinstance(values, Mapping):
        raise InvalidRow('reorder_bands', 'EXPECTED_OBJECT')
    sku = text(values, 'sku', 'reorder_bands.sku')
    store = text(values, 'store', 'reorder_bands.store')
    day = integer(values, 'day', 0, 10000000, 'reorder_bands.day')
    actual = number(values, 'actual', 0, 100000, 'reorder_bands.actual')
    predicted = number(values, 'predicted', 0, 100000, 'reorder_bands.predicted')
    available = flag(values, 'available', 'reorder_bands.available')
    return ValidationDemand(
        sku=sku,
        store=store,
        day=day,
        actual=actual,
        predicted=predicted,
        available=available,
    )
