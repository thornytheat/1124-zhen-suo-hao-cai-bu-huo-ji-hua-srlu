from collections import Counter, defaultdict
from math import fsum, isfinite

from .algorithm import calculate
from .contracts import parse


def one_period(derived, exposure):
    row_counts = Counter()
    observed_pieces = []
    full_pieces = []
    censored_days = []
    for day in derived:
        row_counts[day['reason']] += 1
        if day['eligible']:
            observed_pieces.append(day['net_units'])
            full_pieces.append(day['adjusted_units'])
        if day['unavailable_minutes'] and day['adjusted_units'] is None:
            censored_days.append(day['day'])
    made = fsum(full_pieces)
    visible = sum(observed_pieces)
    return {'minimum_exposure':exposure,'effective_days':len(full_pieces),'observed_claimed_units':visible,'adjusted_total':made,
            'estimated_extra_units':made-visible,'censored_day_keys':sorted(censored_days),'reasons':dict(row_counts)}


def compare_exposure_policies(rows, *, today, exposures=(.4,.5,.65,.8), lookback=35):
    levels=sorted(set(exposures))
    if not 1<=len(levels)<=9 or not all(isfinite(v) and 0<v<1 for v in levels):
        raise ValueError('INVALID_EXPOSURE_COMPARISON')
    input_rows=[parse(row) for row in rows]
    outputs=defaultdict(list)
    primary_states={}
    for threshold in levels:
        alternative=calculate(input_rows,today=today,minimum_fraction=threshold,lookback=lookback)
        grouped=defaultdict(list)
        for record in alternative:
            key=record['store'],record['sku']
            grouped[key].append(record)
            if threshold==levels[0]:
                primary_states[key]=len(grouped[key])
        for key,observations in grouped.items():
            outputs[key].append(one_period(observations,threshold))
    results=[]
    for (store,sku), variants in sorted(outputs.items()):
        first,last=variants[0],variants[-1]
        results.append({'store':store,'sku':sku,'visible_days':primary_states[store,sku],
                        'severe_censoring':len(last['censored_day_keys']),'window_sensitivity':first['effective_days']-last['effective_days'],
                        'imputed_units_difference':first['estimated_extra_units']-last['estimated_extra_units'],'options':variants})
    return results
