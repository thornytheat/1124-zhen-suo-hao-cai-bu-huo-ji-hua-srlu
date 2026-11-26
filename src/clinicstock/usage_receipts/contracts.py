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
class UsageTicket:
    sku: str
    store: str
    ticket: str
    movement: str
    day: int
    posted: int
    units: int
    unit: str
    pack: int
    revision: int


def parse(values: Mapping[str, Any]) -> UsageTicket:
    if not isinstance(values, Mapping):
        raise InvalidRow('usage_receipts', 'EXPECTED_OBJECT')
    sku = text(values, 'sku', 'usage_receipts.sku')
    store = text(values, 'store', 'usage_receipts.store')
    ticket = text(values, 'ticket', 'usage_receipts.ticket')
    movement = text(values, 'movement', 'usage_receipts.movement')
    day = integer(values, 'day', 0, 10000000, 'usage_receipts.day')
    posted = integer(values, 'posted', 0, 10000000, 'usage_receipts.posted')
    units = integer(values, 'units', 1, 50000, 'usage_receipts.units')
    unit = text(values, 'unit', 'usage_receipts.unit')
    pack = integer(values, 'pack', 1, 1000, 'usage_receipts.pack')
    revision = integer(values, 'revision', 1, 99, 'usage_receipts.revision')
    return UsageTicket(
        sku=sku,
        store=store,
        ticket=ticket,
        movement=movement,
        day=day,
        posted=posted,
        units=units,
        unit=unit,
        pack=pack,
        revision=revision,
    )
