import pytest
from clinicstock.outage_today import compare_exposure_policies
from clinicstock.pipeline import run


def shelf(day, **extra):
    return {'sku':'GLV','store':'西站','day':day,'observed':day+1,'open_minutes':480,
            'unavailable_minutes':0,'closing_units':20,'net_units':10}|extra


def history():
    return [shelf(day) for day in (5,6,7)]


def test_sensitivity_changes_only_imputed_tail_of_censored_days():
    adjusted=shelf(9,unavailable_minutes=240,net_units=7)
    shorter=shelf(10,unavailable_minutes=300,net_units=3)
    result=compare_exposure_policies(history()+[adjusted,shorter],today=16,exposures=[.3,.5,.6])[0]
    assert result['visible_days']==5 and result['window_sensitivity']==2
    first,second,third=result['options']
    assert [alt['effective_days'] for alt in result['options']]==[5,4,3]
    assert first['adjusted_total']==52
    assert second['adjusted_total']==44
    assert third['adjusted_total']==30
    assert second['censored_day_keys']==[10]
    assert third['censored_day_keys']==[9,10]
    assert result['imputed_units_difference']==12
    assert result['severe_censoring']==2


def test_ordinary_zero_days_stay_in_history_for_all_thresholds():
    result=compare_exposure_policies([shelf(day,net_units=0) for day in range(1,10)],today=16)[0]
    assert result['window_sensitivity']==0 and result['visible_days']==9
    assert result['imputed_units_difference']==0
    assert all(case['effective_days']==9 and case['adjusted_total']==0 for case in result['options'])
    assert all(case['reasons']=={'COMPLETE_DAY':9} for case in result['options'])


def test_future_or_unavailable_counts_do_not_change_earlier_exposure_diagnosis():
    data=history()+[shelf(9,unavailable_minutes=160,net_units=4)]
    amended=data+[shelf(13,net_units=95,observed=21),shelf(22,net_units=92)]
    current=compare_exposure_policies(data,today=16)
    assert current==compare_exposure_policies(amended,today=16)
    assert current==compare_exposure_policies(reversed(data),today=16)
    assert all(row['estimated_extra_units']>=0 for row in current[0]['options'])


def test_scope_references_are_not_shared_between_inventory_points():
    samples=history()+[shelf(9,unavailable_minutes=200,net_units=5),shelf(9,store='病房',unavailable_minutes=200,net_units=5)]
    details=compare_exposure_policies(samples,today=16,exposures=[.4])[0:2]
    floor={row['store']:row['options'][0] for row in details}
    assert floor['西站']['effective_days']==4
    assert floor['病房']['effective_days']==0
    assert floor['病房']['censored_day_keys']==[9]
    assert floor['病房']['reasons']=={'INSUFFICIENT_UNCENSORED_HISTORY':1}


@pytest.mark.parametrize('exposures',[(),(0,.5),(.5,1),(float('nan'),),tuple(i/20 for i in range(1,11))])
def test_exposure_grid_rejected_if_percent_is_out_of_range(exposures):
    with pytest.raises(ValueError,match='INVALID_EXPOSURE_COMPARISON'):
        compare_exposure_policies([],today=16,exposures=exposures)


def test_default_comparison_includes_current_policy_for_each_stockroom_item():
    view=run()
    detail=view['reconciliation']['exposure_sensitivity']
    truth=view['stages'][1]['records']
    for line in detail:
        current=next(alt for alt in line['options'] if alt['minimum_exposure']==.5)
        matched=[row for row in truth if row['store']==line['store'] and row['sku']==line['sku']]
        assert line['visible_days']==len(matched)
        assert current['effective_days']==sum(row['eligible'] for row in matched)
        assert current['adjusted_total']==pytest.approx(sum(row['adjusted_units'] for row in matched if row['eligible']))
        assert current['observed_claimed_units']==sum(row['net_units'] for row in matched if row['eligible'])
