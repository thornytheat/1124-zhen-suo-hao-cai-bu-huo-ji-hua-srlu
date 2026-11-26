from dataclasses import replace
import math

import pytest

from clinicstock.usage_receipts.contracts import UsageTicket, InvalidRow, parse
from clinicstock.usage_receipts.service import evaluate, validate
from clinicstock.usage_receipts import algorithm

def ticket(name='D-15', **values):
    return dict(sku='GAUZE-10', store='门诊', ticket=name, movement='issue', day=5, posted=5,
                units=4, unit='case', pack=12, revision=1) | values


def test_case_converts_to_individual_pieces():
    assert evaluate([ticket()], as_of=8)['records'][0]['net'] == 48


def test_return_reverses_inventory_consumption():
    val = evaluate([ticket(movement='return')], as_of=8)['records'][0]
    assert val['net'] == -48


def test_transfer_cannot_be_mistaken_for_clinic_consumption():
    assert evaluate([ticket(movement='transfer_out')], as_of=8)['records'][0]['net'] == 0


def test_physically_equivalent_counts_are_one_document():
    rows = [ticket(), ticket(unit='piece', units=48)]
    result = evaluate(rows, as_of=8)['records'][0]
    assert result['net'] == 48 and result['superseded'] == 1


def test_revision_supersedes_original_amount_without_order_dependence():  # TRAP-26
    rows = [ticket(units=4), ticket(revision=2, units=6)]
    assert evaluate(rows, as_of=9) == evaluate(reversed(rows), as_of=9)
    assert evaluate(rows, as_of=9)['records'][0]['net'] == 72


def test_returns_and_issues_cannot_share_a_revision():  # TRAP-14
    rows = evaluate([ticket(),ticket(movement='return')], as_of=8)['records']
    assert rows[0]['reason'] == 'CHALLENGED_REVISION'
    assert rows[0]['net'] is None


def test_unposted_ticket_must_not_contribute_a_duplicate():
    rows = evaluate([ticket(), ticket(posted=9, revision=5)], as_of=8)['records']
    assert [row['net'] for row in rows] == [None,48]


def test_store_specific_ticket_numbers_are_not_global():
    rows = evaluate([ticket(), ticket(store='注射室')], as_of=8)['records']
    assert sum(row['net'] for row in rows) == 96
