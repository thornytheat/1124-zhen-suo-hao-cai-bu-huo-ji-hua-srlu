from dataclasses import replace
import math

import pytest

from clinicstock.demand_smoothing.contracts import DemandDay, InvalidRow, parse
from clinicstock.demand_smoothing.service import evaluate, validate
from clinicstock.demand_smoothing import algorithm

def observations(n=30, **changes):
    return [dict(sku='W1',store='注射室',day=day,adjusted_units=(day%7+1)*3)|changes for day in range(n)]


def test_croston_known_sparse_impulses_match_reference():
    assert algorithm.bias_adjusted_croston([(0,0),(1,8),(2,0),(3,0),(4,4)],.5) == pytest.approx(1.8)


def test_weekly_forecast_matches_reference_pattern():
    row = evaluate(observations(), today=30)['records'][0]
    assert row['daily_forecast'] == [9,12,15,18,21,3,6]
    assert row['forecast_total'] == 84


def test_different_store_does_not_change_forecast():  # TRAP-53
    one = evaluate(observations(), today=30)['records'][0]
    both = evaluate(observations()+observations(store='门诊',adjusted_units=789), today=30)['records'][0]
    assert one == both


def test_different_smoothing_parameter_invalidates_fingerprint():  # TRAP-54
    one = evaluate(observations(), today=30, alpha=.1)['records'][0]
    two = evaluate(observations(), today=30, alpha=.2)['records'][0]
    assert one['fit_id'] != two['fit_id']


def test_future_rows_at_training_watermark_are_not_consumed():
    reference = evaluate(observations(),today=30)['records']
    tampered = evaluate(observations()+[observations(31,adjusted_units=123)[-1]],today=30)['records']
    assert reference == tampered


def test_empty_sales_for_all_days_is_valid_zero_forecast():
    row = evaluate(observations(adjusted_units=0),today=30)['records'][0]
    assert row['forecast_total'] == 0
    assert row['reason'] == 'FORECAST_READY'


def test_small_history_is_separate_from_zero_sales():
    row = evaluate(observations(3),today=3)['records'][0]
    assert row['forecast_total'] is None and row['daily_forecast'] == []


def test_repeated_day_with_disagreement_is_removed_from_training():
    rows = observations(21)
    row = evaluate(rows+[rows[0]|{'adjusted_units':980}],today=21)['records'][0]
    assert row['history_days'] == 20
