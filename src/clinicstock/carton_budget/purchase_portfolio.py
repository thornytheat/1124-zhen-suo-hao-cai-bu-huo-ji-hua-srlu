from dataclasses import dataclass
from math import gcd

from .algorithm import (
    calculate,
    demand_inventory,
    forecast_gap_units,
)
from .contracts import parse


@dataclass(frozen=True,slots=True)
class Portfolio:
    # 三层覆盖（件）：关键耗材预计缺口、一般耗材预计缺口、经验证的安全库存。
    critical_gap: int = 0
    standard_gap: int = 0
    buffer_units: int = 0
    picks: tuple = ()

    @property
    def value(self):
        # 低层级覆盖字典序优先：预算不足时先补关键缺口，再补一般缺口，最后补安全库存。
        return (self.critical_gap, self.standard_gap, self.buffer_units)

    def attach(self, row, cases, unmet):
        delivered = cases * row.pack
        if unmet is None:
            return self
        if not row.validated:
            # 未核量品项只允许关键耗材的应急整箱，全部计入其预计缺口层。
            covered = min(unmet, delivered)
            critical = covered if row.critical else 0
            standard = 0 if row.critical else covered
            if cases == 0:
                return Portfolio(self.critical_gap, self.standard_gap, self.buffer_units, self.picks)
            return Portfolio(self.critical_gap + critical,
                             self.standard_gap + standard,
                             self.buffer_units,
                             self.picks + ((row.sku, row.store, cases),))
        gap = forecast_gap_units(row)
        gap_cover = min(gap, delivered)
        # 整箱取整带来的超盖与已验证安全库存同属最后预算层。
        buffer_cover = max(0, delivered - gap_cover)
        critical = gap_cover if row.critical else 0
        standard = 0 if row.critical else gap_cover
        return Portfolio(self.critical_gap + critical,
                         self.standard_gap + standard,
                         self.buffer_units + buffer_cover,
                         self.picks + ((row.sku, row.store, cases),))


def preference(allocation, spend):
    return allocation.value, -spend, -len(allocation.picks)


def improves(left,spend,right):
    if not right:
        return True
    first = preference(left,spend)
    second = preference(right,spend)
    return first>second or first==second and left.picks<right.picks


def available_choices(source):
    seen={}
    for row in source:
        account=(row.sku,row.store)
        if account in seen and seen[account]!=row:
            raise ValueError('CONFLICTING_PURCHASE_SNAPSHOT')
        seen[account]=row
    quota=[]
    for key,row in sorted(seen.items()):
        count,unmet,reason=demand_inventory(row)
        quota.append((row,count,unmet,reason))
    return quota


def advance_funding(options, row, maximum, unmet, money, unit):
    after={}
    cost=row.case_cost//unit
    for spend,prior in options.items():
        remaining=(money-spend)//cost
        for count in range(min(maximum,remaining)+1):
            total=spend+count*cost
            candidate=prior.attach(row,count,unmet)
            if improves(candidate,total,after.get(total)):
                after[total]=candidate
    return after


def exact_cost_envelope(rows, money, state_limit):
    divisor=0
    for item,maximum,_,_ in rows:
        if maximum and item.case_cost<=money:
            divisor=gcd(divisor,item.case_cost)
    if not divisor:
        return {0:Portfolio()},1
    limit=money//divisor
    if limit>state_limit:
        return None,divisor
    choices={0:Portfolio()}
    for row, maximum, unmet, reason in rows:
        if not maximum or row.case_cost>money:
            continue
        choices=advance_funding(choices,row,maximum,unmet,limit,divisor)
    return choices,divisor


def baseline_metrics(source, money):
    rows=calculate(source,money=money)
    scores=Portfolio()
    spent=0
    lookup={(one.sku,one.store):one for one in source}
    for result in rows:
        account=result['sku'],result['store']
        scores=scores.attach(lookup[account],result['allocated_cases'],result['shortage'])
        spent+=result['spent']
    return scores,spent


def describe_plan(selected, spent, money, scale, method, baseline, baseline_spend, row_states):
    inventory={(row.sku,row.store):(row,maximum,unmet,reason) for row,maximum,unmet,reason in row_states}
    resolved=[]
    for sku, store, count in selected.picks:
        stock,maximum,unmet,reason=inventory[sku,store]
        resolved.append({'sku':sku,'store':store,'cases':count,'critical':stock.critical,'preview_reason':reason,
                         'maximum_cases':maximum,'usable_coverage':min(unmet,count*stock.pack),
                         'cost_cents':count*stock.case_cost,'unfilled_units':max(0,unmet-count*stock.pack)})
    return {'method':method,'budget_cents':money,'spent_cents':spent,'remaining_cents':money-spent,'step_cents':scale,
            'critical_gap_units':selected.critical_gap,'standard_gap_units':selected.standard_gap,
            'buffer_units':selected.buffer_units,
            'critical_units':selected.critical_gap,'standard_units':selected.standard_gap,
            'weighted_coverage':sum(selected.value),
            'baseline_weighted_coverage':sum(baseline.value),'baseline_spend_cents':baseline_spend,
            'added_coverage':sum(selected.value)-sum(baseline.value),'lines':resolved,
            'verified_cost':sum(row['cost_cents'] for row in resolved)==spent}


def optimize_cartons(records, *, money, maximum_states=8500):
    if type(money) is not int or not 0<=money<=10**7 or type(maximum_states) is not int or not 1<=maximum_states<=20000:
        raise ValueError('INVALID_PORTFOLIO_CONSTRAINTS')
    source=[parse(row) for row in records]
    working=available_choices(source)
    baseline,baseline_spend=baseline_metrics(source,money)
    candidates,scale=exact_cost_envelope(working,money,maximum_states)
    if candidates is None:
        return describe_plan(baseline,baseline_spend,money,scale,'GREEDY_BUDGET_BOUND',baseline,baseline_spend,working)
    high_budget,chosen=max(candidates.items(),key=lambda item:preference(item[1],item[0]))
    return describe_plan(chosen,high_budget*scale,money,scale,'BOUNDED_INTEGER_OPTIMUM',baseline,baseline_spend,working)
