from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from . import carton_budget, consumption_review, demand_smoothing, outage_today, reorder_bands, usage_receipts
from .reorder_bands.weekly_replay import replay_weekly_backtest


SNAPSHOT = 85
DEFAULT_CAPACITY = 48
MINIMUM_VERIFICATION_WEEKS = 4


def read_warehouse():
    source = Path(__file__).resolve().parents[2] / 'sample_data' / 'community_clinic_stockroom.json'
    return json.loads(source.read_text(encoding='utf-8'))


def daily_accounting(tickets, sessions):
    totals = Counter()
    for ticket in tickets:
        if ticket['net'] is not None:
            totals[ticket['sku'],ticket['store'],ticket['day']] += ticket['net']
    return [session|{'net_units':totals[session['sku'],session['store'],session['day']]} for session in sessions]


def forecast_validation(forecasts, sessions):
    observed = {(row['store'],row['sku'],row['day']) for row in sessions if row['reason']=='COMPLETE_DAY'}
    return [
        dict(record,store=source['store'],sku=source['sku'],available=True)
        for source in forecasts for record in source['training_errors']
        if (source['store'],source['sku'],record['day']) in observed
    ]


def compose_requests(shelves, trend, intervals, replay):
    keyed = {(row['store'],row['sku']):row for row in trend}
    bounds = {(row['store'],row['sku']):row for row in intervals}
    replayed = {(row['store'],row['sku']):row for row in replay['records']}
    for item in shelves:
        identity = item['store'],item['sku']
        model = keyed.get(identity,{})
        forecast = model.get('forecast_total')
        band = bounds.get(identity,{})
        # 安全库存必须由逐周回测中足够数量的完整周核准；含断供日的周不计入完整周。
        enough_weeks = replayed.get(identity,{}).get('complete_weeks', 0) >= MINIMUM_VERIFICATION_WEEKS
        safety = band.get('cycle_buffer') if enough_weeks else None
        # 预测本身不可用时仍不可核量；预测可用但完整回测周不足时安全库存留待人工核量。
        yield item | {
            'forecast':forecast or 0,
            'buffer':safety or 0,
            'validated':forecast is not None and safety is not None,
        }


def decisions(order, forecasts, replay):
    forecast = {(row['store'],row['sku']):row['forecast_total'] for row in forecasts}
    replayed = {(row['store'],row['sku']):row for row in replay['records']}
    view = []
    for row in order:
        identity = row['store'], row['sku']
        evidence = replayed.get(identity, {})
        view.append({
            'sku':row['sku'],'store':row['store'],'stock':row['on_hand'],
            'forecast':round(estimate,1) if (estimate:=forecast.get(identity)) is not None else None,
            'buffer':row['buffer'] if row['validated'] else None,'cases':row['allocated_cases'],
            'cost':row['spent']/100,'status':row['state'],'reason':row['reason'],
            'emergency_cases':row['emergency_cases'],
            'complete_replay_weeks':evidence.get('complete_weeks', 0),
            'excluded_outage_weeks':evidence.get('excluded_outage_weeks', 0),
            'late_corrected_weeks':evidence.get('late_corrected_weeks', 0),
        })
    return view


def run(capacity: int | None = None) -> dict:
    data = read_warehouse()
    tickets = usage_receipts.evaluate(data['receipts'],as_of=SNAPSHOT)
    # 逐周时点回测：周初预测只看当时可见的流水与库存记录，迟到记录只在最终结算用量中更正。
    replay = replay_weekly_backtest(data['receipts'], data['daily'], today=SNAPSHOT)
    periods = outage_today.evaluate(daily_accounting(tickets['records'],data['daily']),today=SNAPSHOT)
    known = [row for row in periods['records'] if row['eligible']]
    forecast = demand_smoothing.evaluate(known,today=SNAPSHOT)
    validation = forecast_validation(forecast['records'],periods['records'])
    bands = reorder_bands.evaluate(validation,as_of=SNAPSHOT)
    requests = list(compose_requests(data['stock'],forecast['records'],bands['records'],replay))
    money = 1000*(DEFAULT_CAPACITY if capacity is None else capacity)
    purchase = carton_budget.evaluate(requests,money=money)
    closing = [
        dict(row,model=row['predicted'],baseline=row['naive'],realized=row['actual'],closed=row['day']+1,observed=True)
        for row in validation if row['naive'] is not None
    ]
    review = consumption_review.evaluate(closing,as_of=SNAPSHOT)
    decisions_view = decisions(purchase['records'],forecast['records'],replay)
    emergency_lines = [row for row in purchase['records'] if row['emergency_cases']]
    return {
        'reconciliation': {
            'receipt_balance': usage_receipts.balance_receipts(tickets),
            'exposure_sensitivity': outage_today.compare_exposure_policies(daily_accounting(tickets['records'],data['daily']),today=SNAPSHOT),
            'purchase_comparison': carton_budget.optimize_cartons(requests,money=money),
            'observed_weekly_holdout': consumption_review.compare_weekly_holdout(closing,as_of=SNAPSHOT),
            'weekly_safety_replay': replay,
        },
        'metrics': {'耗材品项':len(decisions_view),'建议整箱':sum(row['cases'] for row in decisions_view),
                    '建议金额':round(sum(row['cost'] for row in decisions_view),2),
                    '待人工核量':sum(row['status']=='待人工' for row in decisions_view),
                    '应急整箱建议':sum(row['emergency_cases'] for row in emergency_lines)},
        'columns': {'sku':'耗材','store':'库点','stock':'现存件数','forecast':'未来七日','buffer':'安全库存',
                    'cases':'建议箱数','cost':'采购金额','status':'处理状态','reason':'处置证据',
                    'emergency_cases':'应急整箱','complete_replay_weeks':'完整回测周',
                    'excluded_outage_weeks':'排除断供周','late_corrected_weeks':'迟到更正周'},
        'rows': decisions_view,
        'series': [{'label':row['label'],'value':round(row['model_mae'],2)}
                   for row in review['records'] if row['scope']=='SKU' and row['model_mae'] is not None],
        'stages': [{'title':title,'summary':summary,'records':result['records'],'errors':result['errors']}
                   for title,summary,result in [
                       ('领用流水','调拨及破损不进入临床消耗，修订冲突保留凭证',tickets),
                       ('可售修复','断供期按暴露比例修正，重度缺失期隔离；断供回补量可训练但不核量',periods),
                       ('用量建模','同期中位数结合 Croston 稀疏需求模型，回测只用周初可见流水',forecast),
                       ('残差区间','非重叠七日回测窗口估计安全件数，完整周不足留待人工核量',bands),
                       ('整箱分配','先补关键耗材预计缺口与应急整箱，再补一般缺口，最后安全库存',purchase),
                       ('消耗复盘','对真实结算窗口同时回放模型与同期基线',review),
                   ]],
    }
