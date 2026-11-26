from collections import defaultdict
from math import fsum, sqrt

from .algorithm import deduplicate, forecast_scores
from .contracts import parse


def block_intervals(series, length):
    chronological=sorted(series,key=lambda row:row.day)
    complete=[]
    block=[]
    for row in chronological:
        if block and row.day!=block[-1].day+1:
            block=[]
        block.append(row)
        if len(block)==length:
            complete.append(block)
            block=[]
    return complete


def assess_block(block):
    model_error=fsum(abs(row.model-row.realized) for row in block)
    comparison_error=fsum(abs(row.baseline-row.realized) for row in block)
    forecast_mass=fsum(row.model for row in block)
    actual_mass=fsum(row.realized for row in block)
    return {'start':block[0].day,'end':block[-1].day+1,'model_absolute_error':model_error,
            'baseline_absolute_error':comparison_error,'absolute_error_reduction':comparison_error-model_error,
            'total_units_realized':actual_mass,'forecast_volume_bias':forecast_mass-actual_mass}


def error_interval(weeks, minimum):
    n=len(weeks)
    if n<minimum:
        return None
    points=[row['absolute_error_reduction'] for row in weeks]
    average=fsum(points)/n
    standard_error=sqrt(fsum((point-average)**2 for point in points)/(n*(n-1)))
    return [average-1.96*standard_error,average+1.96*standard_error]


def compare_weekly_holdout(records, *, as_of, block_days=7, minimum=3, lookback=70):
    if type(block_days) is not int or not 1<=block_days<=28 or minimum<2 or lookback<block_days:
        raise ValueError('INVALID_HOLDOUT_WINDOW')
    usable=deduplicate([parse(item) for item in records],as_of)
    groups=defaultdict(list)
    for row in usable:
        if as_of-lookback<=row.day<as_of:
            groups[row.store,row.sku].append(row)
    summary=[]
    for (store,sku),rows in sorted(groups.items()):
        outcomes=[assess_block(block) for block in block_intervals(rows,block_days)]
        observed_count=block_days*len(outcomes)
        interval=error_interval(outcomes,minimum)
        decision='INSUFFICIENT_BLOCKS' if interval is None else (
            'MODEL_LOWER_ERROR' if interval[0]>0 else 'BASELINE_LOWER_ERROR' if interval[1]<0 else 'INCONCLUSIVE')
        total_gain=fsum(row['absolute_error_reduction'] for row in outcomes)
        summary.append({'store':store,'sku':sku,'visible_days':len(rows),'retained_days':observed_count,
                        'unpaired_days':len(rows)-observed_count,'decision':decision,'error_reduction_interval':interval,
                        'average_weekly_reduction':total_gain/len(outcomes) if outcomes else None,
                        'day_scores':forecast_scores(rows),'blocks':outcomes})
    return {'as_of':as_of,'days_per_block':block_days,'buckets':summary,'matched_daily_rows':sum(row['retained_days'] for row in summary)}
