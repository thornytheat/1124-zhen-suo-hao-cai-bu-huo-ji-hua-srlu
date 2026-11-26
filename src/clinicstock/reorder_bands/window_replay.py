"""Replay safety stock decisions on closed, nonoverlapping replenishment cycles."""

from dataclasses import dataclass
from hashlib import sha256
from math import ceil, fsum


@dataclass(frozen=True, slots=True)
class CycleWindow:
    start: int
    end: int
    residual: float


def split_cycles(points, horizon):
    complete = []
    buffer = []
    breaks = []
    excluded_days = 0
    for day, error in points:
        if buffer and day != buffer[-1][0] + 1:
            excluded_days += len(buffer)
            breaks.append({'last_observed_day': buffer[-1][0], 'next_observed_day': day,
                           'excluded_partial_days': len(buffer)})
            buffer.clear()
        buffer.append((day, error))
        if len(buffer) == horizon:
            complete.append(CycleWindow(buffer[0][0], day, fsum(value for _, value in buffer)))
            buffer.clear()
    return complete, breaks, excluded_days + len(buffer)


def finite_sample_bound(errors, level):
    if not errors:
        return None
    rank = ceil((len(errors) + 1) * level)
    if rank > len(errors):
        return None
    return max(0, sorted(errors)[rank - 1])


def evaluate_prior_cycle(prior, window, level, minimum_windows):
    estimate = finite_sample_bound(prior, level) if len(prior) >= minimum_windows else None
    reserved = None if estimate is None else ceil(estimate)
    shortage = None if reserved is None else max(0, window.residual - reserved)
    return {
        'start_day': window.start,
        'end_day': window.end,
        'prior_closed_cycles': len(prior),
        'net_residual_units': window.residual,
        'reserved_units': reserved,
        'uncovered_units': shortage,
        'covered': None if shortage is None else shortage == 0,
        'state': 'MEASURED' if reserved is not None else 'WARM_UP',
    }


def evaluate_in_order(windows, level, minimum_windows):
    history = []
    decisions = []
    for window in windows:
        decisions.append(evaluate_prior_cycle(history, window, level, minimum_windows))
        history.append(window.residual)
    return decisions


def replay_stats(decisions):
    evaluated = [decision for decision in decisions if decision['reserved_units'] is not None]
    hit_count = sum(decision['covered'] for decision in evaluated)
    residuals = [decision['uncovered_units'] for decision in evaluated]
    return {
        'evaluated_cycles': len(evaluated),
        'covered_cycles': hit_count,
        'warm_up_cycles': len(decisions) - len(evaluated),
        'coverage': hit_count / len(evaluated) if evaluated else None,
        'uncovered_units': fsum(residuals) if evaluated else None,
        'highest_cycle_shortage': max(residuals, default=None),
    }


def coverage_evidence(windows, breaks, excluded_days, level, minimum_windows, as_of, horizon):
    decisions = evaluate_in_order(windows, level, minimum_windows)
    return {
        'cutoff_day': as_of,
        'cycle_days': horizon,
        'nominal_coverage': level,
        'minimum_prior_cycles': minimum_windows,
        'excluded_partial_days': excluded_days,
        'window_breaks': breaks,
        'decisions': decisions,
        'result': replay_stats(decisions),
        'replay_id': sha256(repr((windows, breaks, excluded_days, level, minimum_windows, as_of, horizon)).encode()).hexdigest()[:16],
    }
