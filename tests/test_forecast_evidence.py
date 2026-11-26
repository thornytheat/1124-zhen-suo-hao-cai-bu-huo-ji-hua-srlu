import pytest

from clinicstock.demand_smoothing.service import evaluate
from clinicstock.demand_smoothing.forecast_evidence import directional_loss, history_profile, missing_ranges


def stock_day(day, adjusted_units, sku='SYR-5'):
    return {'sku': sku, 'store': '采血室', 'day': day, 'adjusted_units': adjusted_units}


def test_absent_dates_remain_separate_from_zero_use():
    records = [stock_day(day, 0 if day == 2 else 3) for day in range(24) if day not in {4, 5, 11, 23}]
    evidence = evaluate(records, today=24)['records'][0]['demand_evidence']['history']
    assert evidence['observed_days'] == 20
    assert evidence['zero_use_days'] == 1
    assert evidence['missing_days'] == 4
    assert [(row['first_day'], row['last_day']) for row in evidence['missing_spans']] == [(4, 5), (11, 11), (23, 23)]
    assert evidence['recent_observed_days'] == 12
    assert evidence['completion_rate'] == pytest.approx(20 / 24)
    assert sum(evidence['weekday_counts']) == 20


def test_conflicting_day_has_no_hidden_training_usage():
    receipts = [stock_day(day, 3) for day in range(21)] + [stock_day(9, 99)]
    initial = evaluate(receipts, today=21)['records'][0]
    reordered = evaluate(list(reversed(receipts)), today=21)['records'][0]
    assert initial == reordered
    history = initial['demand_evidence']['history']
    assert history['observed_use_units'] == 60
    assert history['missing_spans'] == [{'first_day': 9, 'last_day': 9, 'days': 1}]
    assert all(row['day'] != 9 for row in initial['training_errors'])


def test_weekday_forecast_displays_each_actual_training_day():
    records = [stock_day(day, day % 7 + 1) for day in range(35)]
    output = evaluate(records, today=35)['records'][0]
    cycle = output['demand_evidence']['cycle']
    first = cycle[0]
    assert first['day'] == 35
    assert first['basis'] == 'WEEKDAY_MEDIAN'
    assert first['weekday_observations'] == [{'day': day, 'units': 1} for day in [0, 7, 14, 21, 28]]
    assert [row['forecast_units'] for row in cycle] == list(range(1, 8))
    assert first['last_positive_day'] == 34
    assert cycle[-1]['days_since_positive_use'] == 7


def test_sparse_forecast_evidence_never_consumes_cutoff_observations():
    days = [13, 15, 17, 20, 24, 28, 31, 33, 36, 38, 39, 41, 44, 46]
    receipts = [stock_day(day, 12 if day == 38 else 0) for day in days]
    before = evaluate(receipts, today=47)['records'][0]
    after = evaluate(receipts + [stock_day(47, 1000), stock_day(60, 900)], today=47)['records'][0]
    assert after == before
    first = before['demand_evidence']['cycle'][0]
    assert first['basis'] == 'SPARSE_DEMAND'
    assert first['weekday_observations'] == [{'day': 33, 'units': 0}]
    assert first['days_since_positive_use'] == 9
    assert first['forecast_units'] > 0


def test_untrained_product_keeps_history_and_empty_prediction():
    result = evaluate([stock_day(3, 10), stock_day(5, 0)], today=6)['records'][0]
    evidence = result['demand_evidence']
    assert result['forecast_total'] is None
    assert evidence['cycle'] == []
    assert evidence['history']['observed_days'] == 2
    assert evidence['history']['zero_use_days'] == 1
    assert evidence['backtest']['paired_model_days']['signed_bias_units_per_day'] is None


def test_empty_history_does_not_report_a_zero_completion_rate():
    assert history_profile([], 100)['completion_rate'] is None
    assert missing_ranges([(3, 0)], 10_000_000) == [{'first_day': 4, 'last_day': 9_999_999, 'days': 9_999_996}]


def test_asymmetric_error_shows_service_gap_and_excess_separately():
    rows = [{'actual': 7, 'forecast': 0}, {'actual': 2, 'forecast': 8}, {'actual': 0, 'forecast': 4}]
    result = directional_loss(rows, 'forecast')
    assert result['actual_units'] == 9
    assert result['shortage_units'] == 7 and result['excess_units'] == 10
    assert result['shortage_share'] == pytest.approx(7 / 9)
    assert result['missed_use_days'] == 1 and result['positive_use_days'] == 2
    assert result['zero_use_overforecast_units'] == 4
    assert result['signed_bias_units_per_day'] == 1


def test_prior_week_comparison_uses_only_paired_dates():
    receipts = [stock_day(day, 4) for day in range(32) if day not in {6, 8, 21}]
    output = evaluate(receipts, today=32)['records'][0]
    losses = output['demand_evidence']['backtest']
    paired = [row for row in output['training_errors'] if row['naive'] is not None]
    assert len(paired) < losses['all_model_days']['days']
    assert len(paired) == losses['paired_model_days']['days'] == losses['paired_prior_week_days']['days']
    assert losses['paired_model_days']['actual_units'] == losses['paired_prior_week_days']['actual_units']
