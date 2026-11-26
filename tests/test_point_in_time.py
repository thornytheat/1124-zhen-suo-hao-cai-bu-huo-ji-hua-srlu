"""规则2：迟到的领退用记录更正结算用量，但周初预测只用当时可见的流水。"""

from clinicstock.usage_receipts.point_in_time import (
    accounting_as_of,
    settled_totals,
    visibility_watermarks,
    visible_tickets,
)


def ticket(day, posted, units, revision=1, ticket='T1', movement='issue'):
    return {'sku': 'S', 'store': '门诊', 'ticket': ticket, 'movement': movement,
            'day': day, 'posted': posted, 'units': units, 'unit': 'piece',
            'pack': 1, 'revision': revision}


def session(day):
    return {'sku': 'S', 'store': '门诊', 'day': day, 'observed': day + 1,
            'open_minutes': 480, 'unavailable_minutes': 0,
            'closing_units': 100, 'net_units': 0}


def test_late_revision_is_invisible_before_posting_but_corrects_settlement_after():
    tickets = [ticket(5, 5, 4), ticket(5, 12, 10, revision=2)]
    sessions = [session(5)]
    assert accounting_as_of(tickets, sessions, 8)[0]['net_units'] == 4
    assert accounting_as_of(tickets, sessions, 13)[0]['net_units'] == 10


def test_visibility_filter_requires_posted_and_due_tickets():
    tickets = [ticket(5, 5, 4), ticket(9, 12, 7, ticket='T9')]
    assert {row['ticket'] for row in visible_tickets(tickets, 8)} == {'T1'}
    assert {row['ticket'] for row in visible_tickets(tickets, 13)} == {'T1', 'T9'}


def test_watermark_only_tracks_posting_after_the_business_day():
    tickets = [ticket(5, 5, 4), ticket(6, 20, 8, ticket='T6', revision=2)]
    marks = visibility_watermarks(tickets)
    assert marks == {('门诊', 'S', 6): 20}


def test_invalid_movement_and_unit_do_not_create_watermarks_or_totals():
    bad = [ticket(5, 5, 4, movement='refund'),
           dict(ticket(6, 6, 4, ticket='T6'), unit='不明')]
    assert visibility_watermarks(bad) == {}
    assert dict(settled_totals(bad)) == {}


def test_revision_selection_is_order_independent_at_each_cutoff():
    tickets = [ticket(5, 12, 10, revision=2), ticket(5, 5, 4)]
    sessions = [session(5)]
    assert accounting_as_of(list(reversed(tickets)), sessions, 13)[0]['net_units'] == 10
    assert accounting_as_of(list(reversed(tickets)), sessions, 8)[0]['net_units'] == 4
