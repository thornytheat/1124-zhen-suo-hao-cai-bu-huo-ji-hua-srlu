from collections import Counter
from decimal import Decimal
from functools import lru_cache
from math import ceil

import pytest

from clinicstock.pipeline import read_warehouse, run


@lru_cache(maxsize=4)
def completed_case(capacity):
    return run(capacity)


@pytest.mark.parametrize('capacity', [1,9,48,100])
def test_stock_and_order_ledgers_conserve_cents_and_fulfillment(capacity):
    plan=completed_case(capacity)
    stage=plan['stages'][4]['records']
    root=read_warehouse()
    portfolio=plan['reconciliation']['purchase_comparison']
    receipts=plan['reconciliation']['receipt_balance']
    stockroom={(item['store'],item['sku']):item for item in root['stock']}
    expected_budget=capacity*1000
    assert portfolio['budget_cents']==expected_budget
    assert sum(row['spent'] for row in stage)==portfolio['baseline_spend_cents']
    assert all(row['budget_remaining']+portfolio['baseline_spend_cents']==expected_budget for row in stage)
    assert sum(Decimal(str(row['cost'])) for row in plan['rows'])==Decimal(portfolio['baseline_spend_cents'])/100
    assert sum(row['cases'] for row in plan['rows'])==plan['metrics']['建议整箱']
    assert receipts['raw_rows']==len(root['receipts'])
    assert receipts['balance_ok']
    for order in stage:
        item=stockroom[order['store'],order['sku']]
        assert order['pack']==item['pack'] and order['on_hand']==item['on_hand']
        assert order['allocated_cases']<=order['requested_cases']
        assert order['spent']==order['allocated_cases']*item['case_cost']
        if order['allocated_cases']:
            staged_units=order['on_hand']+order['inbound']+order['allocated_cases']*order['pack']
            assert staged_units<=item['cold_capacity']
            assert order['validated']
            assert order['shortage']==max(0,ceil(order['forecast'])+order['buffer']-order['on_hand']-order['inbound'])
        if not order['validated']:
            assert order['state']=='待人工'
            assert not order['allocated_cases'] and order['shortage'] is None


def test_forecasts_and_reorder_buffers_align_with_only_closed_clinic_sessions():
    batch=completed_case(48)
    by_item={(row['store'],row['sku']):row for row in batch['stages'][2]['records']}
    intervals={(row['store'],row['sku']):row for row in batch['stages'][3]['records']}
    sessions=Counter((row['store'],row['sku']) for row in batch['stages'][1]['records'] if row['eligible'])
    for stage in batch['stages'][4]['records']:
        location=stage['store'],stage['sku']
        model=by_item[location]
        interval=intervals.get(location,{})
        assert model['history_days']==sessions[location]
        horizon=model['daily_forecast']
        if model['forecast_total'] is None:
            assert horizon==[]
        else:
            assert len(horizon)==7
            assert model['forecast_total']==pytest.approx(sum(horizon))
            assert all(item>=0 for item in horizon)
        if stage['validated']:
            assert stage['forecast']==model['forecast_total']
            assert stage['buffer']==interval['cycle_buffer']
            assert interval['state']=='BAND_READY'
        else:
            assert model['forecast_total'] is None or interval.get('cycle_buffer') is None


def test_safety_stock_requires_enough_complete_weekly_replay_weeks():
    from clinicstock.pipeline import MINIMUM_VERIFICATION_WEEKS
    batch=completed_case(48)
    replay={(row['store'],row['sku']):row
            for row in batch['reconciliation']['weekly_safety_replay']['records']}
    for stage in batch['stages'][4]['records']:
        evidence=replay.get((stage['store'],stage['sku']))
        complete_weeks=0 if evidence is None else evidence['complete_weeks']
        # 含断供日的周被剔除，不能用来凑核量周数。
        if evidence is not None:
            assert evidence['complete_weeks']+evidence['excluded_outage_weeks']==evidence['replayed_weeks']
        if stage['validated']:
            assert complete_weeks>=MINIMUM_VERIFICATION_WEEKS
        else:
            # 未核量品项不得带安全库存；一般耗材不采购，关键耗材只允许应急整箱。
            assert stage['buffer']==0
            if stage['critical']:
                assert stage['allocated_cases']==stage['emergency_cases']
            else:
                assert stage['allocated_cases']==0


def test_emergency_metric_counts_only_unvalidated_critical_lines():
    batch=completed_case(48)
    lines=batch['stages'][4]['records']
    expected=sum(row['emergency_cases'] for row in lines)
    assert batch['metrics']['应急整箱建议']==expected
    assert all(row['emergency_cases']==0 for row in lines if row['validated'] or not row['critical'])


def test_independent_inventory_runs_share_data_but_never_reuse_budget_allocations():
    low=completed_case(1)
    high=completed_case(100)
    assert low['metrics']['建议整箱']<high['metrics']['建议整箱']
    assert low['metrics']['建议金额']<high['metrics']['建议金额']
    assert [item['records'] for item in low['stages'][:4]]==[item['records'] for item in high['stages'][:4]]
    unchanged=['receipt_balance','exposure_sensitivity','observed_weekly_holdout']
    assert all(low['reconciliation'][key]==high['reconciliation'][key] for key in unchanged)
    assert low['reconciliation']['purchase_comparison']['weighted_coverage']<=high['reconciliation']['purchase_comparison']['weighted_coverage']


def test_per_sku_error_chart_has_no_data_from_unsettled_synthetic_baseline():
    batch=completed_case(48)
    report=batch['stages'][5]['records']
    products={row['label']:row for row in report if row['scope']=='SKU' and row['model_mae'] is not None}
    outline={row['label']:row['value'] for row in batch['series']}
    assert set(outline)==set(products)
    for name,val in outline.items():
        assert val==round(products[name]['model_mae'],2)
        assert products[name]['rows']>0
        assert products[name]['model_mae']>=0
    assert batch['metrics']['待人工核量']>0
    ready={row['sku'] for row in batch['rows'] if row['status']=='待人工'}
    assert not ready.intersection(outline)


def test_adjustments_do_not_treat_clinic_closure_and_zero_demand_as_one_status():
    batch=completed_case(48)
    eligible=batch['stages'][1]['records']
    completely_missing=[row for row in eligible if row['reason'] in {'CLOSED_SESSION','SEVERE_CENSORING'}]
    observed_zero=[row for row in eligible if row['reason']=='COMPLETE_DAY' and row['net_units']==0]
    assert completely_missing and observed_zero
    for item in completely_missing:
        assert not item['eligible']
        assert item['adjusted_units'] is None
    for item in observed_zero:
        assert item['eligible']
        assert item['adjusted_units']==0
    assert {row['sku'] for row in observed_zero}<={row['sku'] for row in batch['rows']}


def test_cash_constrained_request_lines_keep_a_positive_physically_fillable_gap():
    plan=completed_case(1)
    capped=[item for item in plan['stages'][4]['records'] if item['reason']=='BUDGET_LIMIT']
    assert capped
    for line in capped:
        assert line['validated']
        assert 0<=line['allocated_cases']<line['requested_cases']
        assert line['shortage']>0
