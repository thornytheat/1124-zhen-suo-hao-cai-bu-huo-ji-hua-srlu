"""Point-in-time daily accounting.

迟到的领退用记录会更正最终结算用量（``as_of`` 视图），但周初预测只能使用当时已经
过账、可见的流水。本模块按凭证修订规则在每个可见时点重新结算，保证回测不偷看未来。
"""

from collections import Counter, defaultdict

from .algorithm import DIRECTIONS, select_document
from .contracts import InvalidRow, UsageTicket, parse


def _parsed_tickets(tickets):
    """Drop field-level invalid rows; the service layer already isolates them as rejections."""
    parsed = []
    for row in tickets:
        if isinstance(row, UsageTicket):
            parsed.append(row)
            continue
        try:
            parsed.append(parse(row))
        except InvalidRow:
            continue
    return parsed


def _ticket_effect(ticket):
    if ticket.movement not in DIRECTIONS:
        return None
    if ticket.unit == 'piece':
        packs = 1
    elif ticket.unit == 'case':
        packs = ticket.pack
    else:
        return None
    return DIRECTIONS[ticket.movement] * ticket.units * packs


def visible_tickets(tickets, cutoff):
    """Return the tickets that had been posted and were already due at ``cutoff``."""
    return [
        ticket for ticket in tickets
        if ticket['posted'] <= cutoff and ticket['day'] < cutoff and ticket['posted'] >= ticket['day']
    ]


def settled_totals(tickets):
    """Apply the same revision/movement rules as the ledger and return daily net units."""
    parsed = _parsed_tickets(tickets)
    groups = defaultdict(list)
    for ticket in parsed:
        groups[ticket.store, ticket.ticket].append(ticket)
    totals = Counter()
    for group in groups.values():
        winner, _, net = select_document(group)
        if net is None:
            continue
        totals[winner.store, winner.sku, winner.day] += net
    return totals


def visibility_watermarks(tickets):
    """Per (store, sku, day) posting time of records that arrived after the business day.

    当日或更早过账的流水在业务日当天即可见，不产生水位；只有 ``posted > day`` 的迟到
    记录（含晚到的修订）才会改变该日结算用量在后续周初的可见性。
    """
    watermarks = {}
    for ticket in _parsed_tickets(tickets):
        if _ticket_effect(ticket) is None or ticket.posted <= ticket.day:
            continue
        key = ticket.store, ticket.sku, ticket.day
        previous = watermarks.get(key)
        if previous is None or ticket.posted > previous:
            watermarks[key] = ticket.posted
    return watermarks


def accounting_as_of(tickets, sessions, cutoff):
    """Daily accounting rebuilt from only the flow visible at ``cutoff``."""
    totals = settled_totals(visible_tickets(tickets, cutoff))
    return [
        dict(session, net_units=totals[session['store'], session['sku'], session['day']])
        for session in sessions
    ]
