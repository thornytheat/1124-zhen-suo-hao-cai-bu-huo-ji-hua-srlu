import pytest

from clinicstock.reorder_bands.service import evaluate
from clinicstock.reorder_bands.window_replay import CycleWindow, evaluate_in_order, split_cycles


def history(cycle_totals, width=2):
    return [
        {'store': '耗材库', 'sku': 'B77', 'day': offset * width + day, 'predicted': 20,
         'actual': 20 + (residual if day == 0 else 0), 'available': True}
        for offset, residual in enumerate(cycle_totals)
        for day in range(width)
    ]


def run(rows, **settings):
    options = {'as_of': 30, 'horizon': 2, 'level': .6, 'minimum_windows': 2} | settings
    return evaluate(rows, **options)['records'][0]


def test_replay_does_not_fit_held_out_window_before_decision():
    result = run(history([1, 3, 17, 2, 4]))
    replay = result['coverage_replay']
    assert result['cycle_buffer'] == 4
    assert [(row['reserved_units'], row['uncovered_units']) for row in replay['decisions']] == [
        (None, None), (None, None), (3, 14), (17, 0), (3, 1),
    ]
    assert [row['prior_closed_cycles'] for row in replay['decisions']] == list(range(5))
    assert replay['result'] == {'evaluated_cycles': 3, 'covered_cycles': 1, 'warm_up_cycles': 2,
                                'coverage': pytest.approx(1 / 3), 'uncovered_units': 15, 'highest_cycle_shortage': 14}


def test_future_outcomes_excluded_from_early_cycle_capacity():
    first = run(history([1, 2, 4]), as_of=6)['coverage_replay']
    admitted_later = run(history([1, 2, 4, 9, 11]), as_of=10)['coverage_replay']
    same_snapshot = run(history([1, 2, 4, 9, 11]), as_of=6)['coverage_replay']
    assert admitted_later['decisions'][:3] == first['decisions']
    assert same_snapshot == first
    assert first['replay_id'] != admitted_later['replay_id']


def test_cutoff_keeps_open_window_out_of_calibration():
    rows = history([2, 5, 9, 6], width=3)
    result = run(rows, horizon=3, as_of=11)
    replay = result['coverage_replay']
    assert result['past_windows'] == [2, 5, 9]
    assert replay['excluded_partial_days'] == 2
    assert replay['decisions'][-1]['end_day'] == 8
    assert replay['decisions'][-1]['uncovered_units'] == 4


def test_calendar_gap_discards_only_partial_windows():
    points = [(1, 4), (2, 4), (3, 4), (5, 2), (7, 1), (8, 3), (9, 8), (10, 6)]
    cycles, breaks, excluded = split_cycles(points, 3)
    assert cycles == [CycleWindow(1, 3, 12), CycleWindow(7, 9, 12)]
    assert breaks == [{'last_observed_day': 5, 'next_observed_day': 7, 'excluded_partial_days': 1}]
    assert excluded == 2


def test_unavailable_return_and_conflicting_day_cannot_boost_support():
    rows = history([2, 2, 2, 2, 2])
    rows[4]['available'] = False
    rows.append(rows[6] | {'actual': 99})
    output = run(rows)
    replay = output['coverage_replay']
    assert output['effective_windows'] == 3
    assert replay['excluded_partial_days'] == 2
    assert [row['start_day'] for row in replay['decisions']] == [0, 2, 7]


def test_high_confidence_small_history_is_warm_up():
    replay = run(history([1, 3, 8]), level=.95)['coverage_replay']
    assert replay['result']['coverage'] is None
    assert replay['result']['uncovered_units'] is None
    assert replay['result']['evaluated_cycles'] == 0
    assert all(row['state'] == 'WARM_UP' for row in replay['decisions'])


def test_negative_and_fractional_residuals_obey_integer_stock_units():
    windows = [CycleWindow(0, 1, -2), CycleWindow(2, 3, .25), CycleWindow(4, 5, .9)]
    measured = evaluate_in_order(windows, .6, 2)[-1]
    assert measured['reserved_units'] == 1
    assert measured['uncovered_units'] == 0
    assert measured['covered']


def test_confidence_or_input_changes_change_replay_signature():
    rows = history([1, 2, 3, 4, 5])
    original = run(rows)['coverage_replay']['replay_id']
    changed = run(rows, level=.65)['coverage_replay']['replay_id']
    revised = run(rows[:-1] + [rows[-1] | {'actual': 50}])['coverage_replay']['replay_id']
    assert len({original, changed, revised}) == 3
