from itertools import product

import pytest

from clinicstock.carton_budget import optimize_cartons
from clinicstock.pipeline import run


def supplies(sku, **changes):
    return {'sku':sku,'store':'中心门诊','pack':10,'case_cost':690,'on_hand':0,'inbound':0,
            'forecast':12,'buffer':0,'validated':True,'critical':False,'cold_capacity':20,'min_term_days':3}|changes


def test_exact_option_beats_marginal_greedy_with_two_smaller_packs():
    a=supplies('A',pack=7,case_cost=5,forecast=7,cold_capacity=7)
    b=supplies('B',pack=6,case_cost=4,forecast=6,cold_capacity=6)
    c=supplies('C',pack=7,case_cost=5,forecast=7,cold_capacity=7)
    d=supplies('D',pack=6,case_cost=4,forecast=6,cold_capacity=6)
    chosen=optimize_cartons([a,b,c,d],money=10)
    assert chosen['weighted_coverage']==14
    assert chosen['baseline_weighted_coverage']==12
    assert chosen['spent_cents']==10 and chosen['remaining_cents']==0
    assert chosen['added_coverage']==2
    assert chosen['verified_cost']
    assert {line['sku'] for line in chosen['lines']}=={'A','C'}


@pytest.mark.parametrize('money', [0,5,11,30,50,100])
def test_exact_market_compares_against_exhaustive_reference(money):
    a=supplies('A',pack=9,case_cost=6,forecast=17,cold_capacity=18)
    b=supplies('B',pack=5,case_cost=5,forecast=6,cold_capacity=10,critical=True)
    c=supplies('C',pack=12,case_cost=11,forecast=16,cold_capacity=24)
    source=[a,b,c]
    def reference(counts):
        spend=sum(row['case_cost']*units for row,units in zip(source,counts))
        score=sum(min(row['forecast'],row['pack']*units)*(3 if row['critical'] else 1) for row,units in zip(source,counts))
        return spend,score
    expected=max(score for spend,score in map(reference,product(range(3),repeat=3)) if spend<=money)
    actual=optimize_cartons(source,money=money)
    assert actual['weighted_coverage']==expected
    assert actual['spent_cents']+actual['remaining_cents']==money
    assert actual['verified_cost'] and actual['added_coverage']>=0
    assert all(row['cases']<=row['maximum_cases'] and row['unfilled_units']>=0 for row in actual['lines'])


def test_cold_shelf_capacity_remains_a_hard_constraint_on_what_if():
    frozen=supplies('ice',pack=8,forecast=30,cold_capacity=19,on_hand=10)
    checked=optimize_cartons([frozen],money=50000)
    result,=checked['lines']
    assert result['cases']==result['maximum_cases']==1
    assert result['usable_coverage']==8 and result['unfilled_units']==12
    assert result['preview_reason']=='COLD_OR_TURNOVER_LIMIT'


def test_funding_report_explains_when_state_bound_requires_heuristic():
    rows=[supplies('A',case_cost=11),supplies('B',case_cost=13,critical=True)]
    report=optimize_cartons(rows,money=50,maximum_states=2)
    assert report['method']=='GREEDY_BUDGET_BOUND'
    assert report['added_coverage']==0
    assert report['spent_cents']==report['baseline_spend_cents']
    assert report['weighted_coverage']==report['baseline_weighted_coverage']
    assert report['verified_cost']


def test_contradictory_stock_position_never_creates_two_orders():
    item=supplies('A')
    same=optimize_cartons([item,item],money=9000)
    assert same==optimize_cartons([item],money=9000)
    with pytest.raises(ValueError,match='CONFLICTING_PURCHASE_SNAPSHOT'):
        optimize_cartons([item,item|{'on_hand':2}],money=9000)


def test_unknown_forecast_and_nonmoving_stock_dont_create_buying_opportunity():
    settings=[supplies('A',validated=False),supplies('B',forecast=0),supplies('C',on_hand=30)]
    summary=optimize_cartons(settings,money=10000)
    assert summary['lines']==[]
    assert summary['weighted_coverage']==0
    assert summary['remaining_cents']==10000
    assert summary['method']=='BOUNDED_INTEGER_OPTIMUM'


@pytest.mark.parametrize('capacity',[1,2,5,10,48,70])
def test_normal_feature_pipeline_reconciles_purchase_budget_with_exact_scenario(capacity):
    values=run(capacity)
    scenarios=values['reconciliation']['purchase_comparison']
    published=values['stages'][4]['records']
    assert scenarios['verified_cost']
    assert scenarios['baseline_spend_cents']==sum(row['spent'] for row in published)
    assert scenarios['baseline_spend_cents']==round(100*values['metrics']['建议金额'])
    assert scenarios['budget_cents']==capacity*1000
    assert scenarios['remaining_cents']+scenarios['spent_cents']==scenarios['budget_cents']
    assert scenarios['added_coverage']>=0
