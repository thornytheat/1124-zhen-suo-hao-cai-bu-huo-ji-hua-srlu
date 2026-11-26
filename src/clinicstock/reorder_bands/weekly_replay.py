"""Weekly point-in-time replay that certifies the replenishment safety stock.

每个回测周只使用周初已经过账的领用流水和当时可见的库存记录重建预测；迟到的修订只能
更正最终结算用量，不能改变它过账之前任何一周的周初预测。断供日经过暴露修复的用量可以
进入训练，但任何包含断供日（非完整营业日）的周都不是完整回测周，不能用于核量安全库存。
"""

from collections import defaultdict
from math import ceil

from .. import demand_smoothing, outage_today
from ..usage_receipts.point_in_time import accounting_as_of, visibility_watermarks


def _settled_periods(raw_tickets, sessions, cutoff):
    accounting = accounting_as_of(raw_tickets, sessions, cutoff)
    return outage_today.evaluate(accounting, today=cutoff)['records']


def _eligible_demand(periods, cutoff):
    return [row for row in periods if row['eligible'] and row['day'] < cutoff]


def _forecast_view(demand, cutoff):
    return demand_smoothing.evaluate(demand, today=cutoff)['records']


def _week_starts(sessions, today, horizon):
    """Week starts for which a full week has already settled by ``today``."""
    days = sorted({row['day'] for row in sessions if row['day'] < today})
    if not days:
        return []
    first_start = days[0]
    last_start = first_start + ((today - 1 - first_start) // horizon) * horizon
    return list(range(first_start, last_start + 1, horizon))


def replay_weekly_backtest(raw_tickets, sessions, *, today, horizon=7):
    """Replay each settled week using only records visible at that week's start."""
    watermarks = visibility_watermarks(raw_tickets)
    starts = _week_starts(sessions, today, horizon)

    # 最终结算视图：迟到记录在此处才更正结算用量。
    final_periods = {
        (row['store'], row['sku'], row['day']): row
        for row in _settled_periods(raw_tickets, sessions, today)
    }
    final_demand = [row for row in final_periods.values() if row['eligible'] and row['day'] < today]
    final_forecast = {
        (row['store'], row['sku']): row
        for row in _forecast_view(final_demand, today)
    }

    weekly = []
    for start in starts:
        end = start + horizon
        # 周初（start 当天日切前）只可见 day < start 且 posted <= start 的流水。
        periods = _settled_periods(raw_tickets, sessions, start)
        demand = _eligible_demand(periods, start)
        forecast = {
            (row['store'], row['sku']): row
            for row in _forecast_view(demand, start)
        }
        for (store, sku), model in sorted(forecast.items()):
            # 目标周的实际结算与断供事实以最终视图为准（周初尚不可见）。
            cells = [final_periods.get((store, sku, day)) for day in range(start, end)]
            observed = [cell for cell in cells if cell is not None]
            if len(observed) != horizon:
                continue  # 含关闭/缺失日的周不是完整回测周
            outage_days = [cell['day'] for cell in observed if cell['reason'] != 'COMPLETE_DAY']
            complete_week = not outage_days
            if not model.get('daily_forecast') or model.get('forecast_total') is None:
                continue  # 周初当时给不出七日预测，无法核对安全库存
            # 结算用量以最终视图为准；周初不可见的迟到修订在此体现。
            actual_total = sum(cell['net_units'] for cell in observed)
            weekly.append({
                'store': store,
                'sku': sku,
                'week_start': start,
                'week_end': end,
                'predicted_at_week_start': model['forecast_total'],
                'settled_usage': actual_total,
                'residual': actual_total - model['forecast_total'],
                'complete_week': complete_week,
                'outage_days': outage_days,
                'late_posted_days': sorted(
                    day for day in range(start, end)
                    if (store, sku, day) in watermarks and watermarks[(store, sku, day)] > start
                ),
                'visible_through': max(
                    (watermarks.get((store, sku, day), day) for day in range(start, end)),
                    default=start,
                ),
                'basis': 'WEEKDAY_MEDIAN' if all(
                    item['basis'] == 'WEEKDAY_MEDIAN'
                    for item in model['demand_evidence']['cycle']
                ) else 'SPARSE_DEMAND',
            })

    return _certify(weekly, final_forecast, today, horizon)


def _certify(weekly, final_forecast, today, horizon):
    grouped = defaultdict(list)
    for row in weekly:
        grouped[row['store'], row['sku']].append(row)
    records = []
    for (store, sku), weeks in sorted(grouped.items()):
        complete = [week for week in weeks if week['complete_week']]
        residuals = [week['residual'] for week in complete]
        model = final_forecast.get((store, sku), {})
        records.append({
            'store': store,
            'sku': sku,
            'horizon': horizon,
            'replayed_weeks': len(weeks),
            'complete_weeks': len(complete),
            'excluded_outage_weeks': len(weeks) - len(complete),
            'late_corrected_weeks': sum(1 for week in weeks if week['late_posted_days']),
            'weekly_residuals': residuals,
            'forecast_ready_now': model.get('forecast_total') is not None,
            'weeks': weeks,
        })
    return {
        'as_of': today,
        'horizon': horizon,
        'records': records,
        'total_complete_weeks': sum(len([w for w in rows['weeks'] if w['complete_week']]) for rows in records),
    }


def emergency_gap(on_hand, inbound, forecast, pack):
    """整箱应急缺口：关键耗材现货加在途撑不过预测七天时需要补的整箱数。"""
    if forecast is None or forecast <= 0:
        return 0
    shortfall = ceil(forecast) - on_hand - inbound
    return max(0, ceil(shortfall / pack)) if shortfall > 0 else 0
