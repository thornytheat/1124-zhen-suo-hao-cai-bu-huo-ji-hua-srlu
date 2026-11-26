"""规则4：安全库存周不足留人工，但关键耗材给应急整箱；规则5：预算分层优先级。"""

import pytest

from clinicstock.carton_budget.service import evaluate
from clinicstock.carton_budget.algorithm import (
    case_tier,
    emergency_case_goal,
    forecast_gap_units,
    TIER_EMERGENCY_CRITICAL,
    TIER_FORECAST_GAP,
    TIER_VALIDATED_BUFFER,
)
from clinicstock.carton_budget.contracts import parse


def request(sku='W1', **changes):
    return dict(sku=sku, store='门诊', pack=10, case_cost=500, on_hand=5, inbound=0,
                forecast=100, buffer=0, validated=False, critical=True,
                cold_capacity=1000, min_term_days=30) | changes


def test_critical_unvalidated_item_gets_emergency_cases_for_forecast_gap():
    row = evaluate([request()], money=100000)['records'][0]
    assert row['state'] == '应急建议'
    assert row['reason'] == 'CRITICAL_EMERGENCY_GAP'
    assert row['requested_cases'] == row['allocated_cases'] == 10
    assert row['shortage'] == 95
    assert row['emergency_cases'] == 10


def test_non_critical_unvalidated_item_stays_manual_without_spend():
    row = evaluate([request(sku='N', critical=False)], money=100000)['records'][0]
    assert row['state'] == '待人工'
    assert row['allocated_cases'] == 0 and row['shortage'] is None
    assert row['emergency_cases'] == 0


def test_critical_item_with_enough_stock_needs_no_emergency_case():
    row = evaluate([request(sku='OK', on_hand=200)], money=100000)['records'][0]
    assert row['allocated_cases'] == 0
    assert row['state'] == '待人工'
    assert emergency_case_goal(parse(request(sku='OK2', on_hand=200))) == 0


def test_emergency_cases_respect_cold_capacity_and_shelf_life_limits():
    # 冷位只允许再放 25 件 -> 最多 2 箱，即使缺口更大。
    limited = request(cold_capacity=30)  # on_hand=5，空余冷位 25
    row = evaluate([limited], money=100000)['records'][0]
    assert row['allocated_cases'] == 2
    assert row['reason'] == 'CRITICAL_EMERGENCY_GAP'


def test_tight_budget_partially_funds_emergency_and_keeps_manual_review_flag():
    row = evaluate([request(case_cost=500)], money=1500)['records'][0]
    assert row['allocated_cases'] == 3
    assert row['reason'] == 'BUDGET_LIMIT'
    assert row['state'] == '应急建议'


def test_budget_funds_critical_gap_before_standard_gap():
    standard = request(sku='G', critical=False, validated=True, buffer=0)
    critical = request(sku='K', critical=True, validated=True, buffer=0)
    rows = evaluate([standard, critical], money=500)['records']
    allocation = {row['sku']: row['allocated_cases'] for row in rows}
    assert allocation == {'G': 0, 'K': 1}


def test_forecast_gap_is_funded_before_validated_buffer():
    gap_item = request(sku='A', critical=False, validated=True, forecast=10, buffer=0)
    buffer_item = request(sku='B', critical=False, validated=True, forecast=0, buffer=50)
    rows = evaluate([gap_item, buffer_item], money=500)['records']
    allocation = {row['sku']: row['allocated_cases'] for row in rows}
    assert allocation == {'A': 1, 'B': 0}


def test_critical_gap_outranks_another_items_validated_buffer():
    buffered = request(sku='G', critical=False, validated=True, forecast=0, buffer=100)
    critical = request(sku='K', critical=True, validated=True, forecast=10, buffer=0)
    rows = evaluate([buffered, critical], money=500)['records']
    allocation = {row['sku']: row['allocated_cases'] for row in rows}
    assert allocation == {'G': 0, 'K': 1}


def test_case_tier_moves_from_gap_layer_to_buffer_layer_after_gap_covered():
    row = parse(request(validated=True, critical=False, forecast=25, buffer=100))
    gap = forecast_gap_units(row)  # ceil(25) - on_hand(5) = 20
    assert gap == 20
    assert case_tier(row, 0, gap) == TIER_FORECAST_GAP
    assert case_tier(row, 1, gap) == TIER_FORECAST_GAP      # 10 件仍未补齐 20 件缺口
    assert case_tier(row, 2, gap) == TIER_VALIDATED_BUFFER  # 20 件已补齐缺口
    critical = parse(request(validated=True, critical=True, forecast=25))
    assert case_tier(critical, 0, gap) == TIER_EMERGENCY_CRITICAL


def test_unvalidated_critical_emergency_sits_on_top_tier():
    row = parse(request(validated=False, critical=True))
    assert case_tier(row, 0, 95) == TIER_EMERGENCY_CRITICAL


def test_tier_priority_is_stable_under_input_reversal():
    standard = request(sku='G', critical=False, validated=True)
    critical = request(sku='K', critical=True, validated=True)
    one = evaluate([standard, critical], money=500)['records']
    flipped = evaluate([critical, standard], money=500)['records']
    assert [row['allocated_cases'] for row in one] == [row['allocated_cases'] for row in flipped]
