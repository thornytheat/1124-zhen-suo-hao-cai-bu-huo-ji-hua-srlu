from __future__ import annotations

from .contracts import ConsumptionClose

from collections import defaultdict
from math import fsum


def deduplicate(records, as_of):
    checked = defaultdict(set)
    for row in records:
        if row.observed and row.day <= row.closed <= as_of:
            checked[row.store,row.sku,row.day].add(row)
    return [next(iter(group)) for key,group in sorted(checked.items()) if len(group)==1]


def forecast_scores(group):
    valid = len(group)
    if not valid:
        return {'rows':0,'model_mae':None,'baseline_mae':None,'wape':None,'bias':None,'state':'NO_SETTLED_OUTCOMES'}
    total = fsum(row.realized for row in group)
    err = fsum(abs(row.model-row.realized) for row in group)
    baseline = fsum(abs(row.baseline-row.realized) for row in group)
    bias = fsum(row.model-row.realized for row in group)
    return {'rows':valid,'model_mae':err/valid,'baseline_mae':baseline/valid,'wape':err/total if total else None,
            'bias':bias/valid,'state':'REPLAY_READY' if total else 'OBSERVED_ZERO_CONSUMPTION'}


def calculate(records, *, as_of, recent=14):
    if recent<1 or as_of<0:
        raise ValueError('INVALID_CONSUMPTION_REVIEW_PERIOD')
    source = deduplicate(records,as_of)
    qualified = [row for row in source if as_of-recent<=row.day<as_of]
    stores = defaultdict(list)
    products = defaultdict(list)
    for row in qualified:
        stores[row.store].append(row)
        products[row.sku].append(row)
    report = [{'scope':'ALL','label':'全部仓点','as_of':as_of,**forecast_scores(qualified)}]
    report.extend({'scope':'STORE','label':store,**forecast_scores(group)} for store,group in sorted(stores.items()))
    report.extend({'scope':'SKU','label':sku,**forecast_scores(group)} for sku,group in sorted(products.items()))
    return report
