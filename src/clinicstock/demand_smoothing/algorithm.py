from __future__ import annotations

from .contracts import DemandDay
from .forecast_evidence import WEEKDAY_MINIMUM_MATCHES, forecast_evidence, weekday_points

from collections import defaultdict
from hashlib import sha256
from math import fsum
from statistics import median


def one_week_repeat(values, target):
    return values.get(target - 7)


def bias_adjusted_croston(points, alpha):
    estimated_interval = None
    estimated_size = None
    last_demand_day = None
    outcomes = []
    for day, value in points:
        if value <= 0:
            continue
        if estimated_size is None:
            estimated_size = value
            estimated_interval = max(1, day + 1 - points[0][0])
        else:
            elapsed = day-last_demand_day
            estimated_interval += alpha * (elapsed-estimated_interval)
            estimated_size += alpha * (value-estimated_size)
        last_demand_day = day
        outcomes.append((day, (1-alpha/2) * estimated_size/estimated_interval))
    return outcomes[-1][1] if outcomes else 0.0


def rolling_forecast(rows, target, alpha):
    weekly = [units for _, units in weekday_points(rows, target)]
    if len(weekly) >= WEEKDAY_MINIMUM_MATCHES:
        return median(weekly)
    return bias_adjusted_croston(rows, alpha)


def training_backtest(series, alpha):
    results = []
    for current in range(7, len(series)):
        target, actual = series[current]
        train = series[:current]
        model = rolling_forecast(train, target, alpha)
        naive = one_week_repeat(dict(train), target)
        results.append({'day':target,'actual':actual,'predicted':model,'residual':actual-model,'naive':naive})
    return results


def score_competing_models(scores):
    comparison = [row for row in scores if row['naive'] is not None]
    if not comparison:
        return None, None
    numerator = fsum(abs(row['actual']-row['predicted']) for row in comparison)
    denominator = fsum(abs(row['actual']-row['naive']) for row in comparison)
    return numerator/len(comparison), denominator/len(comparison)


def calculate(records, *, today, alpha=.28, horizon=7, min_days=14):
    if not 0 < alpha < 1 or not 1 <= horizon <= 45 or min_days < 7:
        raise ValueError('INVALID_DEMAND_MODEL_PARAMS')
    groups = defaultdict(set)
    for row in records:
        if row.day < today:
            groups[row.store,row.sku].add((row.day,row.adjusted_units))
    result = []
    for (store,sku), points in sorted(groups.items()):
        dates = defaultdict(set)
        for day, pieces in points:
            dates[day].add(pieces)
        series = [(day,next(iter(values))) for day,values in sorted(dates.items()) if len(values)==1]
        enough = len(series) >= min_days
        errors = training_backtest(series,alpha)
        model_mae, naive_mae = score_competing_models(errors)
        forecast = [rolling_forecast(series, day, alpha) for day in range(today,today+horizon)] if enough else []
        result.append({'store':store,'sku':sku,'history_days':len(series),'training_errors':errors,
                        'model_mae':model_mae,'naive_mae':naive_mae,'daily_forecast':forecast,
                        'forecast_total':fsum(forecast) if enough else None,
                        'reason':'FORECAST_READY' if enough else 'SOURCE_HISTORY_TOO_SPARSE',
                        'demand_evidence':forecast_evidence(series,today,forecast,errors),
                        'fit_id':sha256(repr((series,today,alpha,horizon,min_days,'sba-w7')).encode()).hexdigest()[:16]})
    return result
