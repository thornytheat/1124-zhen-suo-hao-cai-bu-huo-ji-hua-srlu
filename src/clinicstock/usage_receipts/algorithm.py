from __future__ import annotations

from .contracts import UsageTicket

from collections import defaultdict
from dataclasses import asdict


DIRECTIONS = {'issue': 1, 'return': -1, 'transfer_out': 0, 'breakage': 0}


def movement_effect(ticket):
    if ticket.movement not in DIRECTIONS:
        return None, 'UNSUPPORTED_MOVEMENT'
    if ticket.unit == 'piece':
        packs = 1
    elif ticket.unit == 'case':
        packs = ticket.pack
    else:
        return None, 'UNSUPPORTED_COUNTING_UNIT'
    return DIRECTIONS[ticket.movement]*ticket.units*packs, 'POSTED'


def logical_ticket(item):
    return item.sku, item.day, item.movement, movement_effect(item)


def select_document(rows):
    revision = max(ticket.revision for ticket in rows)
    top = [ticket for ticket in rows if ticket.revision == revision]
    winner = min(top, key=lambda item: (item.posted, item.sku, item.day, item.movement, item.units, item.unit, item.pack))
    if len({logical_ticket(item) for item in top}) > 1:
        return winner, 'CHALLENGED_REVISION', None
    net, reason = movement_effect(winner)
    return winner, reason, net


def calculate(records, *, as_of):
    groups = defaultdict(list)
    result = []
    for ticket in records:
        if ticket.posted > as_of or ticket.day >= as_of:
            result.append(asdict(ticket) | {'reason':'NOT_POSTED_AT_SNAPSHOT','net':None})
        elif ticket.posted < ticket.day:
            result.append(asdict(ticket) | {'reason':'POSTED_BEFORE_OCCURRENCE','net':None})
        else:
            groups[ticket.store,ticket.ticket].append(ticket)
    for group in groups.values():
        winner, cause, net = select_document(group)
        result.append(asdict(winner) | {'reason': cause, 'net': net, 'superseded': len(group)-1})
    return sorted(result, key=lambda row: (row['day'], row['store'], row['sku'], row['ticket'], row['reason']))
