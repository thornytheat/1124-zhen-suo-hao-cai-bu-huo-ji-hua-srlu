from itertools import chain

import pytest

from clinicstock.consumption_review import compare_weekly_holdout
from clinicstock.pipeline import run


def observed_day(day,**updates):
    return {'store':'三院库房','sku':'G-10','day':day,'closed':day+1,'realized':15,'model':16,
            'baseline':18,'observed':True}|updates


def test_complete_nonoverlapping_windows_compare_against_naive_reference():
    current=compare_weekly_holdout([observed_day(day) for day in range(2,24)],as_of=26)
    entry,=current['buckets']
    assert current['matched_daily_rows']==21
    assert entry['retained_days']==21 and entry['unpaired_days']==1
    assert entry['decision']=='MODEL_LOWER_ERROR'
    assert entry['error_reduction_interval']==[14,14]
    assert entry['average_weekly_reduction']==14
    for position,week in enumerate(entry['blocks']):
        assert (week['start'],week['end'])==(2+7*position,9+7*position)
        assert week['model_absolute_error']==7
        assert week['baseline_absolute_error']==21
        assert week['total_units_realized']==105
        assert week['forecast_volume_bias']==7


def test_randomized_sign_is_inconclusive_with_small_sample_uncertainty():
    rows=list(chain([observed_day(day) for day in range(1,8)],
                    [observed_day(day,model=18,baseline=16) for day in range(8,15)],
                    [observed_day(day,model=16,baseline=16) for day in range(15,22)]))
    item=compare_weekly_holdout(rows,as_of=25)['buckets'][0]
    assert item['decision']=='INCONCLUSIVE'
    assert item['average_weekly_reduction']==0
    left,right=item['error_reduction_interval']
    assert left<0<right and left == -right
    assert [week['absolute_error_reduction'] for week in item['blocks']]==[14,-14,0]


def test_one_gap_prevents_partial_tail_being_counted_as_seven_days():
    days=[day for day in range(1,24) if day!=6]
    report=compare_weekly_holdout([observed_day(day) for day in days],as_of=25)
    item=report['buckets'][0]
    assert report['matched_daily_rows']==14
    assert item['unpaired_days']==8
    assert item['decision']=='INSUFFICIENT_BLOCKS'
    assert item['error_reduction_interval'] is None
    assert [span['start'] for span in item['blocks']]==[7,14]


def test_replay_excludes_unobserved_and_conflicting_counts_and_keeps_site_scope():
    first=[observed_day(day) for day in range(1,9)]
    conflict=observed_day(2,model=55)
    another=[observed_day(day,store='二站',model=18,baseline=15) for day in range(1,9)]
    records=first+[conflict]+another+[observed_day(15,closed=27),observed_day(16,observed=False)]
    options=compare_weekly_holdout(records,as_of=26,block_days=3,minimum=2)
    by_site={row['store']:row for row in options['buckets']}
    assert by_site['三院库房']['visible_days']==7
    assert by_site['三院库房']['retained_days']==6
    assert by_site['三院库房']['decision']=='MODEL_LOWER_ERROR'
    assert by_site['二站']['visible_days']==8
    assert by_site['二站']['decision']=='BASELINE_LOWER_ERROR'
    assert by_site['二站']['error_reduction_interval']==[-9,-9]


def test_calibration_and_observed_metrics_exclude_stockout_imputed_targets():
    evidence=run()
    known={(point['store'],point['sku'],point['day']):point for point in evidence['stages'][1]['records']}
    replay=evidence['reconciliation']['observed_weekly_holdout']
    assert replay['matched_daily_rows']>0
    for item in replay['buckets']:
        for interval in item['blocks']:
            cells=[known[item['store'],item['sku'],day] for day in range(interval['start'],interval['end'])]
            assert {row['reason'] for row in cells}=={'COMPLETE_DAY'}
            assert interval['total_units_realized']==sum(row['net_units'] for row in cells)
        assert item['retained_days']+item['unpaired_days']==item['visible_days']
    assert any(row['reason']=='EXPOSURE_ADJUSTED' for row in known.values())


@pytest.mark.parametrize('changes',[{'block_days':0},{'block_days':1.5},{'block_days':40},{'lookback':5},{'minimum':1}])
def test_holdout_rejects_nonsensical_block_parameters(changes):
    with pytest.raises(ValueError,match='INVALID_HOLDOUT_WINDOW'):
        compare_weekly_holdout([],as_of=100,**changes)
