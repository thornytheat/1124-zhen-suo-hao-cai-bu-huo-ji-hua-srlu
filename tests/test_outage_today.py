from dataclasses import replace
import math

import pytest

from clinicstock.outage_today.contracts import DailyShelf, InvalidRow, parse
from clinicstock.outage_today.service import evaluate, validate
from clinicstock.outage_today import algorithm

def day(n=13, **changes):
    return dict(sku='W20',store='门诊',day=n,observed=n,open_minutes=480,unavailable_minutes=0,
                closing_units=5,net_units=8) | changes


def test_later_day_never_corrects_earlier_censored_demand():  # TRAP-42
    earlier = [day(n) for n in (1,2,3)] + [day(n=5,unavailable_minutes=160,net_units=4)]
    future = day(n=9,net_units=200)
    one = evaluate(earlier,today=15)['records'][3]
    both = evaluate([future]+earlier,today=15)['records'][3]
    assert one == both and one['adjusted_units'] == pytest.approx(6)


def test_complete_zero_demand_is_observed_not_censored():
    row = evaluate([day(net_units=0)],today=20)['records'][0]
    assert row['eligible'] and row['adjusted_units'] == 0


def test_offline_entire_shift_has_no_imputed_zero():
    row = evaluate([day(unavailable_minutes=480)],today=20)['records'][0]
    assert row['adjusted_units'] is None
    assert row['reason'] == 'SEVERE_CENSORING'


def test_isolated_stockout_cannot_borrow_other_clinic_history():
    rows = [day(n) for n in (1,2,3)] + [day(store='病房', unavailable_minutes=120)]
    assert next(row for row in evaluate(rows,today=20)['records'] if row['store']=='病房')['reason'] == 'INSUFFICIENT_UNCENSORED_HISTORY'


def test_half_day_exposure_is_allowed_and_bounded():
    rows = [day(n,net_units=5) for n in (1,2,3)] + [day(unavailable_minutes=240,net_units=10)]
    assert evaluate(rows,today=20)['records'][-1]['adjusted_units'] == 12


def test_negative_units_are_correction_evidence_not_training_target():
    row = evaluate([day(net_units=-2)],today=20)['records'][0]
    assert row['reason'] == 'RETURN_HEAVY_DAY'


def test_missing_closing_snapshot_stays_excluded():
    assert evaluate([day(observed=25)],today=20)['records'] == []


def test_conflicting_shelf_snapshots_are_kept_out():
    assert evaluate([day(),day(closing_units=70)],today=20)['records'] == []
