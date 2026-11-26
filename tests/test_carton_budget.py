from dataclasses import replace
import math

import pytest

from clinicstock.carton_budget.contracts import PurchaseRequest, InvalidRow, parse
from clinicstock.carton_budget.service import evaluate, validate
from clinicstock.carton_budget import algorithm

def request(sku='W1',**changes):
    return dict(sku=sku,store='门诊',pack=10,case_cost=850,on_hand=14,inbound=0,forecast=65,buffer=9,
                validated=True,critical=False,cold_capacity=100,min_term_days=4)|changes


def test_reorder_rounds_exact_shortage_without_overbuy():
    row=evaluate([request()],money=10000)['records'][0]
    assert row['shortage']==60 and row['allocated_cases']==6


def test_inbound_stock_removes_shortage_before_case_rounding():
    row=evaluate([request(inbound=18)],money=10000)['records'][0]
    assert row['shortage']==42 and row['allocated_cases']==5


def test_hard_cold_space_limit_cannot_round_up():
    row=evaluate([request(cold_capacity=30)],money=10000)['records'][0]
    assert row['allocated_cases']==1 and row['reason']=='COLD_OR_TURNOVER_LIMIT'


def test_critical_supply_receives_tie_break_even_if_later_identifier():  # TRAP-19
    items=[request(),request('W9',critical=True)]
    one=evaluate(items,money=850)['records']
    assert [row['allocated_cases'] for row in one]==[0,1]
    assert evaluate(reversed(items),money=850)['records']==one


def test_integer_budget_conservation_for_mixed_costs():
    rows=evaluate([request(),request('W2',case_cost=2200),request('W3',case_cost=1320)],money=6850)['records']
    assert sum(row['spent'] for row in rows)+rows[0]['budget_remaining']==6850
    assert all(row['budget_remaining']==rows[0]['budget_remaining'] for row in rows)


def test_untrusted_forecast_is_not_assigned_spend():
    row=evaluate([request(validated=False)],money=75000)['records'][0]
    assert row['spent']==0 and row['shortage'] is None
    assert row['state']=='待人工'


def test_separate_stockrooms_can_buy_the_same_sku():
    rows=evaluate([request(),request(store='化验')],money=10200)['records']
    assert [row['allocated_cases'] for row in rows]==[6,6]


def test_conflicting_warehouse_snapshot_cannot_be_resolved_by_processing_order():
    with pytest.raises(ValueError,match='STOCK_POSITION_CONFLICT'):
        evaluate([request(),request(on_hand=2)])
