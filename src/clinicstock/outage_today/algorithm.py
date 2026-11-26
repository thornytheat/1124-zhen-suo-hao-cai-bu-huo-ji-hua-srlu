from __future__ import annotations

from .contracts import DailyShelf

from collections import defaultdict
from dataclasses import asdict
from statistics import median


def physical_divergence(row):
    if row.open_minutes == 0:
        return 'CLOSED_SESSION'
    if row.unavailable_minutes > row.open_minutes:
        return 'OUTAGE_LONGER_THAN_SESSION'
    if row.net_units < 0:
        return 'RETURN_HEAVY_DAY'
    return None


def identifiable_buckets(records, today):
    groups = defaultdict(set)
    for row in records:
        if row.day < today and row.day <= row.observed <= today:
            groups[row.sku,row.store,row.day].add(row)
    usable = []
    for key, material in sorted(groups.items()):
        if len(material) == 1:
            usable.extend(material)
    return usable


def censored_targets(row, history, minimum_fraction):
    fault = physical_divergence(row)
    if fault:
        return asdict(row) | {'eligible': False, 'adjusted_units': None, 'reason': fault, 'availability':None}
    availability = (row.open_minutes-row.unavailable_minutes)/row.open_minutes
    if availability == 1:
        adjusted, explanation = row.net_units, 'COMPLETE_DAY'
    elif availability < minimum_fraction:
        adjusted, explanation = None, 'SEVERE_CENSORING'
    elif len(history) < 3:
        adjusted, explanation = None, 'INSUFFICIENT_UNCENSORED_HISTORY'
    else:
        center = median(history)
        scaled = row.net_units / availability
        # Winsorize only the extrapolated increment. Observed consumption is a hard lower bound.
        adjusted = max(row.net_units, min(scaled, center*2+2))
        explanation = 'EXPOSURE_ADJUSTED'
    return asdict(row) | {'eligible': adjusted is not None, 'adjusted_units': adjusted,
                          'reason': explanation, 'availability': availability}


def calculate(records, *, today, minimum_fraction=.5, lookback=35):
    if not 0 < minimum_fraction < 1 or lookback < 1:
        raise ValueError('INVALID_EXPOSURE_PARAMS')
    retained = identifiable_buckets(records, today)
    histories = defaultdict(list)
    report = []
    for row in retained:
        history = histories[row.sku,row.store]
        visible = [val for day,val in history if row.day-lookback <= day < row.day]
        report.append(censored_targets(row, visible, minimum_fraction))
        if not physical_divergence(row) and row.unavailable_minutes == 0:
            history.append((row.day,row.net_units))
    return report
