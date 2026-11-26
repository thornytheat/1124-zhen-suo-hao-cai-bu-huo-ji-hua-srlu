from collections import Counter

import pytest

from clinicstock.usage_receipts import balance_receipts, evaluate
from clinicstock.pipeline import read_warehouse, run


def movement(ticket,**extra):
    return {'sku':'BOX','store':'西门诊','ticket':ticket,'movement':'issue','day':12,'posted':13,
            'units':3,'unit':'case','pack':6,'revision':1}|extra


def journal(data, as_of=20):
    return balance_receipts(evaluate(data,as_of=as_of))


def test_inventory_changes_only_include_consumption_issues_and_returns():
    values=[movement('i'),movement('r',movement='return',units=2,unit='piece'),
            movement('t',movement='transfer_out',units=4),movement('b',movement='breakage',units=4,unit='piece')]
    report=journal(values)
    proof,=report['inventory_ledgers']
    assert proof['issued']==18 and proof['returned']==2
    assert proof['transfer']==24 and proof['discard']==4
    assert proof['net_demand']==report['total_net_demand']==16
    assert report['gross_valid_documents']==4
    assert proof['days']==[{'day':12,'issues':18,'returns':2,'transfer':24,'discard':4,'net_consumption':16,'requires_count':False}]
    assert report['balance_ok'] and proof['closure_verified']


def test_receipt_revision_and_late_return_audited_without_reducing_current_day_twice():
    first=movement('i')
    closed=movement('r',movement='return',units=2,posted=21)
    data=[first,first|{'revision':3,'units':4},closed,first|{'ticket':'bad','movement':'refund'},first|{'ticket':'data','units':'4'}]
    view=journal(data)
    house,=view['inventory_ledgers']
    assert view['late_documents']==[{'store':'西门诊','ticket':'r','posted':21,'revision':1}]
    assert view['field_failures']==1
    assert view['raw_rows']==len(data) and view['balance_ok']
    assert house['late_or_invalid']=={'UNSUPPORTED_MOVEMENT':1,'NOT_POSTED_AT_SNAPSHOT':1}
    assert house['superseded']==1 and house['net_demand']==24


def test_negative_day_flags_count_reconciliation_without_fabricating_sales():
    entries=[movement('r',movement='return',units=4),movement('i',day=10,posted=10,units=1)]
    rows=journal(entries)['inventory_ledgers'][0]['days']
    assert [item['requires_count'] for item in rows]==[False,True]
    assert sum(row['net_consumption'] for row in rows)==-18
    assert rows[1]['net_consumption']==-24


def test_independent_stockrooms_can_use_identical_ticket_identifiers():
    one=movement('x')
    view=journal([one,one|{'store':'北站','units':1}])
    assert view['gross_valid_documents']==2 and view['total_net_demand']==24
    assert len(view['inventory_ledgers'])==2
    assert all(site['closure_verified'] for site in view['inventory_ledgers'])


def test_duplicate_posted_document_cannot_be_accepted_in_final_chain():
    one=evaluate([movement('a')],as_of=20)
    two=one|{'records':one['records']*2}
    with pytest.raises(ValueError,match='DOUBLE_POSTED_DOCUMENT'):
        balance_receipts(two)


def test_fixture_balance_matches_sparse_only_product_and_open_stock():
    view=run()
    detail=view['reconciliation']['receipt_balance']
    assert detail['balance_ok'] and detail['raw_rows']==len(read_warehouse()['receipts'])
    parsed=view['stages'][0]['records']
    assert detail['total_net_demand']==sum(row['net'] for row in parsed if row['net'] is not None)
    assert len(detail['inventory_ledgers'])==view['metrics']['耗材品项']
    assert sum(row['net_demand'] for row in detail['inventory_ledgers'])==detail['total_net_demand']
    assert all(row['closure_verified'] for row in detail['inventory_ledgers'])
