from __future__ import annotations

from .contracts import ValidationDemand
from .window_replay import coverage_evidence, finite_sample_bound, split_cycles

from collections import defaultdict
from hashlib import sha256
from math import ceil
from statistics import median


def error_rows(records, as_of):
    groups = defaultdict(set)
    for record in records:
        if record.available and record.day < as_of:
            groups[record.store,record.sku,record.day].add(record)
    output = defaultdict(list)
    for (store,sku,day), candidates in sorted(groups.items()):
        if len(candidates) != 1:
            continue
        row = next(iter(candidates))
        output[store,sku].append((day,row.actual-row.predicted))
    return output


def nonoverlap_windows(points, horizon):
    windows, _, _ = split_cycles(points, horizon)
    return [window.residual for window in windows]


def calculate(records, *, as_of, level=.8, horizon=7, minimum_windows=4):
    if not 0 < level < 1 or minimum_windows < 2 or not 1 <= horizon <= 45:
        raise ValueError('INVALID_REORDER_BAND_SETTINGS')
    result = []
    for (store,sku), errors in sorted(error_rows(records,as_of).items()):
        windows, breaks, excluded_days = split_cycles(errors, horizon)
        totals = [window.residual for window in windows]
        ready = len(totals) >= minimum_windows
        buffer = finite_sample_bound(totals,level) if ready else None
        risk_delta = median(totals) if totals else None
        result.append({'store':store,'sku':sku,'effective_windows':len(totals),'horizon':horizon,
                       'cycle_buffer':ceil(buffer) if buffer is not None else None,
                       'median_residual':risk_delta,'past_windows':totals,
                       'known_coverage':sum(value<=buffer for value in totals)/len(totals) if buffer is not None else None,
                       'state':'BAND_READY' if buffer is not None else 'INSUFFICIENT_VERIFICATION_WINDOWS',
                       'coverage_replay':coverage_evidence(windows,breaks,excluded_days,level,minimum_windows,as_of,horizon),
                       'signature':sha256(repr((errors,as_of,level,horizon,minimum_windows)).encode()).hexdigest()[:16]})
    return result
