"""Evidence used by stockroom staff to distinguish data gaps from low use."""

from collections import Counter
from math import fsum
from statistics import median


WEEKDAY_HISTORY_DAYS = 35
WEEKDAY_MINIMUM_MATCHES = 2


def weekday_points(series, target):
    return [
        (day, units)
        for day, units in series
        if target - WEEKDAY_HISTORY_DAYS <= day < target and (target - day) % 7 == 0
    ]


def missing_ranges(series, today):
    """Show unobserved dates as spans, without expanding long gaps into lists."""
    if not series:
        return []
    gaps = []
    prior_day = series[0][0]
    for day, _ in series[1:]:
        if day > prior_day + 1:
            gaps.append({'first_day': prior_day + 1, 'last_day': day - 1, 'days': day - prior_day - 1})
        prior_day = day
    if today > prior_day + 1:
        gaps.append({'first_day': prior_day + 1, 'last_day': today - 1, 'days': today - prior_day - 1})
    return gaps


def history_profile(series, today):
    gaps = missing_ranges(series, today)
    unobserved = sum(gap['days'] for gap in gaps)
    observed = len(series)
    quantities = [units for _, units in series]
    by_weekday = Counter(day % 7 for day, _ in series)
    recent = [units for day, units in series if day >= today - 14]
    return {
        'first_day': series[0][0] if series else None,
        'last_day': series[-1][0] if series else None,
        'observed_days': observed,
        'missing_days': unobserved,
        'missing_spans': gaps,
        'zero_use_days': quantities.count(0),
        'observed_use_units': fsum(quantities),
        'recent_observed_days': len(recent),
        'recent_median_units': median(recent) if recent else None,
        'weekday_counts': [by_weekday.get(index, 0) for index in range(7)],
        'completion_rate': observed / (observed + unobserved) if observed else None,
    }


def cycle_support(series, today, daily_forecast):
    evidence = []
    observed_days = [day for day, usage in series if usage > 0]
    last_use = observed_days[-1] if observed_days else None
    for offset, prediction in enumerate(daily_forecast):
        target = today + offset
        points = weekday_points(series, target)
        weekly = len(points) >= WEEKDAY_MINIMUM_MATCHES
        evidence.append({
            'day': target,
            'forecast_units': prediction,
            'basis': 'WEEKDAY_MEDIAN' if weekly else 'SPARSE_DEMAND',
            'weekday_observations': [{'day': day, 'units': units} for day, units in points],
            'last_positive_day': last_use,
            'days_since_positive_use': None if last_use is None else target - last_use,
        })
    return evidence


def directional_loss(rows, field):
    deficits = []
    surpluses = []
    zero_use_overstock = []
    positive_days = 0
    missed_days = 0
    for row in rows:
        actual = row['actual']
        estimate = row[field]
        difference = actual - estimate
        deficits.append(max(0, difference))
        surpluses.append(max(0, -difference))
        if actual > 0:
            positive_days += 1
            missed_days += estimate == 0
        else:
            zero_use_overstock.append(estimate)
    actual_units = fsum(row['actual'] for row in rows)
    shortage = fsum(deficits)
    excess = fsum(surpluses)
    return {
        'days': len(rows),
        'actual_units': actual_units,
        'shortage_units': shortage,
        'excess_units': excess,
        'missed_use_days': missed_days,
        'positive_use_days': positive_days,
        'worst_shortage_units': max(deficits, default=None),
        'zero_use_overforecast_units': fsum(zero_use_overstock),
        'signed_bias_units_per_day': (excess - shortage) / len(rows) if rows else None,
        'shortage_share': shortage / actual_units if actual_units else None,
    }


def forecast_evidence(series, today, forecasts, backtest):
    paired = [row for row in backtest if row['naive'] is not None]
    return {
        'history': history_profile(series, today),
        'cycle': cycle_support(series, today, forecasts),
        'backtest': {
            'all_model_days': directional_loss(backtest, 'predicted'),
            'paired_model_days': directional_loss(paired, 'predicted'),
            'paired_prior_week_days': directional_loss(paired, 'naive'),
        },
    }
