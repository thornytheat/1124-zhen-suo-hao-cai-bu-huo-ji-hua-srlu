from dataclasses import replace
import math

import pytest

from clinicstock.reorder_bands.contracts import ValidationDemand, InvalidRow, parse
from clinicstock.reorder_bands.service import evaluate, validate
from clinicstock.reorder_bands import algorithm

def record(day=1, **changes):
    return dict(sku='KIT9',store='门诊',day=day,actual=8,predicted=6,available=True)|changes


def test_rank_uses_finite_sample_upper_coverage():
    assert algorithm.finite_sample_bound([-1,1,3,4,5,6,7,8,9],.8) == 8


def test_high_coverage_with_too_few_points_is_unavailable():
    assert algorithm.finite_sample_bound([1,2], .9) is None


def test_negative_forecast_errors_cannot_reduce_reorder_buffer():
    assert algorithm.finite_sample_bound([-3,-2,-1], .7) == 0


def test_recent_unavailable_outcomes_cannot_help_or_hurt_coverage():
    baseline = [record(day) for day in range(12)]
    updated = baseline+[record(12, available=False, actual=300),record(13, actual=300)]
    assert evaluate(baseline,as_of=13,horizon=3)['records'] == evaluate(updated,as_of=13,horizon=3)['records']


def test_nonoverlap_validation_blocks_drop_incomplete_intervals():  # TRAP-33
    series = [(1,3),(2,3),(3,3),(4,9),(6,5),(7,5),(8,5),(9,99)]
    assert algorithm.nonoverlap_windows(series,3) == [9,15]


def test_group_without_enough_closed_windows_leaves_buffer_unknown():  # TRAP-43
    points = [record(day) for day in range(6)]
    sample = evaluate(points,as_of=8,horizon=3)['records'][0]
    assert sample['known_coverage'] is None
    assert sample['cycle_buffer'] is None
    assert sample['state']=='INSUFFICIENT_VERIFICATION_WINDOWS'


def test_conflicting_day_cannot_count_twice():
    points = [record(day) for day in range(12)]+[record(3,actual=20)]
    sample = evaluate(points,as_of=13,horizon=3)['records'][0]
    assert sample['effective_windows']==3


def test_unbounded_condition_rejects_invalid_coverage():
    with pytest.raises(ValueError,match='INVALID_REORDER_BAND_SETTINGS'):
        evaluate([record()],as_of=12,level=1)
