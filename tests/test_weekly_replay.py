"""规则1/2/3：逐周时点回测核准安全库存。"""

from clinicstock.reorder_bands.weekly_replay import emergency_gap, replay_weekly_backtest


def ticket(day, units=10, posted=None, revision=1, ticket=None):
    return {'sku': 'S', 'store': '门诊', 'ticket': ticket or f'T{day}', 'movement': 'issue',
            'day': day, 'posted': day if posted is None else posted, 'units': units,
            'unit': 'piece', 'pack': 1, 'revision': revision}


def sessions(days, outage_days=()):
    return [{'sku': 'S', 'store': '门诊', 'day': day, 'observed': day + 1,
             'open_minutes': 480, 'unavailable_minutes': 240 if day in outage_days else 0,
             'closing_units': 100, 'net_units': 0} for day in days]


def steady_history(length):
    days = range(1, length + 1)
    return [ticket(day) for day in days], sessions(list(days))


def test_late_revision_keeps_week_start_forecast_but_updates_settled_usage():
    tickets, base_sessions = steady_history(35)
    before = replay_weekly_backtest(tickets, base_sessions, today=36)
    revised = tickets + [ticket(16, units=40, posted=30, revision=2, ticket='T16')]
    after = replay_weekly_backtest(revised, base_sessions, today=36)
    base_weeks = {w['week_start']: w for w in before['records'][0]['weeks']}
    late_weeks = {w['week_start']: w for w in after['records'][0]['weeks']}
    for start, week in late_weeks.items():
        assert week['predicted_at_week_start'] == base_weeks[start]['predicted_at_week_start']
    target = late_weeks[15]
    assert target['late_posted_days'] == [16]
    assert target['settled_usage'] == 100  # 40 修订量 + 其余六天各 10
    assert base_weeks[15]['settled_usage'] == 70


def test_week_with_outage_day_is_not_a_complete_backtest_week():
    length = 49
    days = list(range(1, length + 1))
    tickets = [ticket(day, units=5 if day == 17 else 10) for day in days]
    replay = replay_weekly_backtest(tickets, sessions(days, outage_days={17}), today=length + 1)
    record = replay['records'][0]
    outage_week = next(w for w in record['weeks'] if w['week_start'] == 15)
    assert outage_week['complete_week'] is False
    assert outage_week['outage_days'] == [17]
    assert record['excluded_outage_weeks'] >= 1
    assert outage_week['residual'] not in record['weekly_residuals']
    assert len(record['weekly_residuals']) == record['complete_weeks']


def test_repaired_outage_demand_still_trains_later_week_forecasts():
    length = 49
    days = list(range(1, length + 1))
    tickets = [ticket(day, units=5 if day == 17 else 10) for day in days]
    replay = replay_weekly_backtest(tickets, sessions(days, outage_days={17}), today=length + 1)
    later = [w for w in replay['records'][0]['weeks'] if w['week_start'] > 17]
    assert later and all(w['predicted_at_week_start'] > 0 for w in later)


def test_weeks_needing_full_seven_days_drop_closed_or_missing_days():
    tickets, base_sessions = steady_history(49)
    # 删除一天的库存记录，模拟整日关闭/缺失（落在已可预测的周内）。
    gapped = [row for row in base_sessions if row['day'] != 16]
    replay = replay_weekly_backtest(tickets, gapped, today=50)
    record = replay['records'][0]
    starts = {w['week_start'] for w in record['weeks']}
    # 含缺失日（15–21）的周不构成完整回测周，不能用于核量。
    assert 15 not in starts
    assert all(w['complete_week'] for w in record['weeks'])


def test_emergency_gap_rounds_up_to_whole_cases_only_when_stock_cannot_cover_forecast():
    assert emergency_gap(on_hand=5, inbound=0, forecast=100, pack=10) == 10
    assert emergency_gap(on_hand=95, inbound=10, forecast=100, pack=10) == 0
    assert emergency_gap(on_hand=0, inbound=0, forecast=0, pack=10) == 0
    assert emergency_gap(on_hand=0, inbound=0, forecast=None, pack=10) == 0
