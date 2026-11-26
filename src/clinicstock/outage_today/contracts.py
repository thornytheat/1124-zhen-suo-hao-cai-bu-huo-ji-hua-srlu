from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class InvalidRow(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}: {code}')
        self.field = field
        self.code = code


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
class DailyShelf:
    sku: str
    store: str
    day: int
    observed: int
    open_minutes: int
    unavailable_minutes: int
    closing_units: int
    net_units: int


def parse(values: Mapping[str, Any]) -> DailyShelf:
    if not isinstance(values, Mapping):
        raise InvalidRow('outage_today', 'EXPECTED_OBJECT')
    sku = text(values, 'sku', 'outage_today.sku')
    store = text(values, 'store', 'outage_today.store')
    day = integer(values, 'day', 0, 10000000, 'outage_today.day')
    observed = integer(values, 'observed', 0, 10000000, 'outage_today.observed')
    open_minutes = integer(values, 'open_minutes', 0, 1440, 'outage_today.open_minutes')
    unavailable_minutes = integer(values, 'unavailable_minutes', 0, 1440, 'outage_today.unavailable_minutes')
    closing_units = integer(values, 'closing_units', 0, 100000, 'outage_today.closing_units')
    net_units = integer(values, 'net_units', -100000, 100000, 'outage_today.net_units')
    return DailyShelf(
        sku=sku,
        store=store,
        day=day,
        observed=observed,
        open_minutes=open_minutes,
        unavailable_minutes=unavailable_minutes,
        closing_units=closing_units,
        net_units=net_units,
    )
