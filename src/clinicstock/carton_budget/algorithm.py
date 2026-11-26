from __future__ import annotations

from .contracts import PurchaseRequest

from collections import defaultdict
from dataclasses import asdict
from math import ceil, floor


def demand_inventory(row):
    if not row.validated:
        return 0,None,'MANUAL_BASELINE_REVIEW'
    remaining = max(0, ceil(row.forecast) + row.buffer - row.on_hand - row.inbound)
    shelf = max(0,row.cold_capacity-row.on_hand-row.inbound)
    requested = ceil(remaining/row.pack)
    shelf_limit = floor(shelf/row.pack)
    if row.forecast > 0:
        turnover_limit = max(0,floor((row.forecast*row.min_term_days-row.on_hand-row.inbound)/row.pack))
    else:
        turnover_limit = 0
    actual = min(requested,shelf_limit,turnover_limit)
    if not requested:
        code = 'NO_REPLENISHMENT'
    elif actual != requested:
        code = 'COLD_OR_TURNOVER_LIMIT'
    else:
        code = 'REQUESTED'
    return actual, remaining, code


def next_case(row, allocated, remaining):
    deliverable = min(row.pack,max(0,remaining-allocated*row.pack))
    criticality = 3 if row.critical else 1
    return criticality*deliverable/row.case_cost


def allocate(options, budget):
    remaining = budget
    counts = defaultdict(int)
    while True:
        eligible = [(row,goal,need) for row,goal,need,_ in options if counts[row.sku,row.store]<goal and row.case_cost<=remaining]
        if not eligible:
            return counts, remaining
        awarded, goal, need = min(eligible,key=lambda item:(-next_case(item[0],counts[item[0].sku,item[0].store],item[2]),
                                           not item[0].critical,item[0].sku,item[0].store))
        counts[awarded.sku,awarded.store] += 1
        remaining -= awarded.case_cost


def calculate(records, *, money=75000):
    if type(money) is not int or money < 0:
        raise ValueError('INVALID_SUPPLY_BUDGET')
    indexed = {}
    for row in records:
        key = row.sku,row.store
        if key in indexed and indexed[key] != row:
            raise ValueError(f'STOCK_POSITION_CONFLICT:{key}')
        indexed[key] = row
    options = [(row,*demand_inventory(row)) for key,row in sorted(indexed.items())]
    counts,remaining = allocate(options,money)
    return [
        asdict(row) | {'requested_cases':offered,'allocated_cases':counts[row.sku,row.store],
                       'spent':counts[row.sku,row.store]*row.case_cost,'budget_remaining':remaining,'shortage':need,
                       'state':'已建议' if counts[row.sku,row.store] else ('待人工' if not row.validated else '未采购'),
                       'reason':'BUDGET_LIMIT' if offered>counts[row.sku,row.store] else flag}
        for row,offered,need,flag in options
    ]
