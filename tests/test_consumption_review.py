from dataclasses import replace
import math

import pytest

from clinicstock.consumption_review.contracts import ConsumptionClose, InvalidRow, parse
from clinicstock.consumption_review.service import evaluate, validate
from clinicstock.consumption_review import algorithm

def close(**values):
    return dict(sku='W1',store='门诊',day=22,closed=24,model=7,baseline=8,realized=6,observed=True)|values


def test_no_observed_consumption_does_not_produce_infinite_percentage():
    row=evaluate([close(realized=0)],as_of=26)['records'][0]
    assert row['wape'] is None and row['model_mae']==7
    assert row['state']=='OBSERVED_ZERO_CONSUMPTION'


def test_expected_absolute_error_against_simple_reference():
    reports=evaluate([close(),close(sku='W9', model=3,realized=4)],as_of=26)['records']
    assert reports[0]['model_mae']==1
    assert reports[0]['baseline_mae']==3
    assert reports[0]['wape']==pytest.approx(.2)
    assert reports[0]['bias']==0


def test_inventory_revision_late_close_excluded():
    totals=evaluate([close(closed=27)],as_of=26)['records'][0]
    assert totals['rows']==0 and totals['model_mae'] is None


def test_duplicate_transactions_do_not_skew_replay():
    report=evaluate([close(),close()],as_of=26)['records'][0]
    assert report['rows']==1


def test_conflicting_closure_is_excluded_without_erasing_other_product():
    report=evaluate([close(),close(realized=7),close(sku='W5')],as_of=26)['records']
    assert report[0]['rows']==1
    assert report[-1]['label']=='W5'


def test_previous_review_boundary_excluded():
    assert evaluate([close(day=17),close(day=18)],as_of=26,recent=8)['records'][0]['rows']==1


def test_unknown_value_retains_empty_report():
    report=evaluate([close(observed=False)],as_of=26)['records'][0]
    assert report['state']=='NO_SETTLED_OUTCOMES'
    assert report['bias'] is None


def test_store_replay_does_not_mix_clinic_outcomes():
    result=evaluate([close(),close(store='注射室',model=9)],as_of=26)['records']
    assert {item['label']:item['model_mae'] for item in result if item['scope']=='STORE'}=={'门诊':1,'注射室':3}
