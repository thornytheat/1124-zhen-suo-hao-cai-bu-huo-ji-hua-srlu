from __future__ import annotations

from .contracts import PurchaseRequest

from collections import defaultdict
from dataclasses import asdict
from enum import IntEnum
from math import ceil, floor


# 预算分层：先补关键耗材的预计缺口（仅覆盖预测七天），再补一般耗材的预计缺口，
# 经验证的安全库存放在最后。同层内按每元边际短缺减少量排序。
class AllocationTier(IntEnum):
    EMERGENCY_CRITICAL = 1
    FORECAST_GAP = 2
    VALIDATED_BUFFER = 3


TIER_EMERGENCY_CRITICAL = AllocationTier.EMERGENCY_CRITICAL
TIER_FORECAST_GAP = AllocationTier.FORECAST_GAP
TIER_VALIDATED_BUFFER = AllocationTier.VALIDATED_BUFFER


def forecast_gap_units(row):
    """预计缺口：预测七天用量减去现货与在途（不包含安全库存）。"""
    if row.forecast is None or row.forecast <= 0:
        return 0
    return max(0, ceil(row.forecast) - row.on_hand - row.inbound)


def emergency_case_goal(row):
    """未通过安全库存核量的关键耗材，现货加在途撑不过预测七天时的应急整箱数。"""
    if row.validated or not row.critical:
        return 0
    gap = forecast_gap_units(row)
    if gap <= 0:
        return 0
    shelf = max(0, row.cold_capacity - row.on_hand - row.inbound)
    shelf_limit = floor(shelf / row.pack)
    if row.forecast > 0:
        turnover_limit = max(0, floor((row.forecast * row.min_term_days
                                       - row.on_hand - row.inbound) / row.pack))
    else:
        turnover_limit = 0
    return min(ceil(gap / row.pack), shelf_limit, turnover_limit)


def demand_inventory(row):
    if not row.validated:
        emergency = emergency_case_goal(row)
        if emergency:
            return emergency, forecast_gap_units(row), 'CRITICAL_EMERGENCY_GAP'
        return 0, None, 'MANUAL_BASELINE_REVIEW'
    remaining = max(0, ceil(row.forecast) + row.buffer - row.on_hand - row.inbound)
    shelf = max(0, row.cold_capacity-row.on_hand-row.inbound)
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


def case_tier(row, allocated, need):
    """下一箱落在哪个预算层。应急整箱与预计缺口优先于经验证的安全库存。"""
    if not row.validated:
        # 未核量品项目标为 0（见 demand_inventory），只有关键耗材的应急整箱会进入分配。
        return TIER_EMERGENCY_CRITICAL if row.critical else TIER_VALIDATED_BUFFER
    gap = forecast_gap_units(row)
    # 已到货件数覆盖满预计缺口后，再买的整箱（含取整超盖）进入安全库存层。
    if allocated * row.pack < gap:
        return TIER_EMERGENCY_CRITICAL if row.critical else TIER_FORECAST_GAP
    return TIER_VALIDATED_BUFFER


def next_case(row, allocated, remaining):
    deliverable = min(row.pack,max(0,remaining-allocated*row.pack))
    return deliverable/row.case_cost


def allocate(options, budget):
    remaining = budget
    counts = defaultdict(int)
    while True:
        eligible = [(row,goal,need) for row,goal,need,_ in options if counts[row.sku,row.store]<goal and row.case_cost<=remaining]
        if not eligible:
            return counts, remaining
        awarded, goal, need = min(
            eligible,
            key=lambda item: (
                case_tier(item[0], counts[item[0].sku, item[0].store], item[2]),
                -next_case(item[0], counts[item[0].sku, item[0].store], item[2]),
                not item[0].critical, item[0].sku, item[0].store,
            ),
        )
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
        asdict(row) | {
            'requested_cases':offered,
            'allocated_cases':counts[row.sku,row.store],
            'spent':counts[row.sku,row.store]*row.case_cost,
            'budget_remaining':remaining,
            'shortage':need,
            'forecast_gap_units':forecast_gap_units(row),
            'emergency_cases':emergency_case_goal(row),
            'state': (
                '应急建议' if flag == 'CRITICAL_EMERGENCY_GAP' and counts[row.sku,row.store]
                else '待人工' if not row.validated and not counts[row.sku,row.store]
                else '已建议' if counts[row.sku,row.store]
                else '未采购'
            ),
            'reason':('BUDGET_LIMIT' if offered>counts[row.sku,row.store] else flag),
        }
        for row,offered,need,flag in options
    ]
