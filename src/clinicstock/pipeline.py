from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from . import carton_budget, consumption_review, demand_smoothing, outage_today, reorder_bands, usage_receipts


SNAPSHOT = 85
DEFAULT_CAPACITY = 48


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


def compose_requests(shelves, trend, intervals):
    keyed = {(row['store'],row['sku']):row for row in trend}
    bounds = {(row['store'],row['sku']):row for row in intervals}
    for item in shelves:
        identity = item['store'],item['sku']
        model = keyed.get(identity,{})
        forecast = model.get('forecast_total')
        safety = bounds.get(identity,{}).get('cycle_buffer')
        yield item | {'forecast':forecast or 0,'buffer':safety or 0,'validated':forecast is not None and safety is not None}


def decisions(order, forecasts):
    forecast = {(row['store'],row['sku']):row['forecast_total'] for row in forecasts}
    return [{
        'sku':row['sku'],'store':row['store'],'stock':row['on_hand'],
        'forecast':round(estimate,1) if (estimate:=forecast.get((row['store'],row['sku']))) is not None else None,
        'buffer':row['buffer'] if row['validated'] else None,'cases':row['allocated_cases'],
        'cost':row['spent']/100,'status':row['state'],'reason':row['reason'],
    } for row in order]


def run(capacity: int | None = None) -> dict:
    data = read_warehouse()
    tickets = usage_receipts.evaluate(data['receipts'],as_of=SNAPSHOT)
    periods = outage_today.evaluate(daily_accounting(tickets['records'],data['daily']),today=SNAPSHOT)
    known = [row for row in periods['records'] if row['eligible']]
    forecast = demand_smoothing.evaluate(known,today=SNAPSHOT)
    validation = forecast_validation(forecast['records'],periods['records'])
    bands = reorder_bands.evaluate(validation,as_of=SNAPSHOT)
    requests = list(compose_requests(data['stock'],forecast['records'],bands['records']))
    money = 1000*(DEFAULT_CAPACITY if capacity is None else capacity)
    purchase = carton_budget.evaluate(requests,money=money)
    closing = [
        dict(row,model=row['predicted'],baseline=row['naive'],realized=row['actual'],closed=row['day']+1,observed=True)
        for row in validation if row['naive'] is not None
    ]
    review = consumption_review.evaluate(closing,as_of=SNAPSHOT)
    decisions_view = decisions(purchase['records'],forecast['records'])
    return {
        'reconciliation': {
            'receipt_balance': usage_receipts.balance_receipts(tickets),
            'exposure_sensitivity': outage_today.compare_exposure_policies(daily_accounting(tickets['records'],data['daily']),today=SNAPSHOT),
            'purchase_comparison': carton_budget.optimize_cartons(requests,money=money),
            'observed_weekly_holdout': consumption_review.compare_weekly_holdout(closing,as_of=SNAPSHOT),
        },
        'metrics': {'耗材品项':len(decisions_view),'建议整箱':sum(row['cases'] for row in decisions_view),
                    '建议金额':round(sum(row['cost'] for row in decisions_view),2),
                    '待人工核量':sum(row['status']=='待人工' for row in decisions_view)},
        'columns': {'sku':'耗材','store':'库点','stock':'现存件数','forecast':'未来七日','buffer':'安全库存',
                    'cases':'建议箱数','cost':'采购金额','status':'处理状态','reason':'处置证据'},
        'rows': decisions_view,
        'series': [{'label':row['label'],'value':round(row['model_mae'],2)}
                   for row in review['records'] if row['scope']=='SKU' and row['model_mae'] is not None],
        'stages': [{'title':title,'summary':summary,'records':result['records'],'errors':result['errors']}
                   for title,summary,result in [
                       ('领用流水','调拨及破损不进入临床消耗，修订冲突保留凭证',tickets),
                       ('可售修复','断供期按暴露比例修正，重度缺失期隔离',periods),
                       ('用量建模','同期中位数结合 Croston 稀疏需求模型',forecast),
                       ('残差区间','非重叠七日回测窗口估计安全件数',bands),
                       ('整箱分配','按优先级、边际短缺减少量和冷位配额采购',purchase),
                       ('消耗复盘','对真实结算窗口同时回放模型与同期基线',review),
                   ]],
    }
