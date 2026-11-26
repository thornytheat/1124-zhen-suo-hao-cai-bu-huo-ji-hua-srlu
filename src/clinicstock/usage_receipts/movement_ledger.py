from collections import Counter, defaultdict


def signed_details(reports):
    issued=0
    returned=0
    transfer=0
    broken=0
    for row in reports:
        if row['net'] is None:
            continue
        if row['movement']=='issue':
            issued+=row['net']
        elif row['movement']=='return':
            returned-=row['net']
        else:
            quantity=row['units']*(row['pack'] if row['unit']=='case' else 1)
            if row['movement']=='transfer_out':
                transfer+=quantity
            else:
                broken+=quantity
    return issued,returned,transfer,broken


def daily_adjustments(items):
    sessions=defaultdict(list)
    for row in items:
        if row['net'] is not None:
            sessions[row['day']].append(row)
    return [{'day':day,'issues':a,'returns':b,'transfer':c,'discard':d,'net_consumption':a-b,
             'requires_count':a<b} for day,events in sorted(sessions.items())
            for a,b,c,d in [signed_details(events)]]


def balance_receipts(validated):
    registered={}
    sites=defaultdict(list)
    expired=[]
    for row in validated['records']:
        key=(row['store'],row['ticket'])
        if row['net'] is not None:
            if key in registered:
                raise ValueError('DOUBLE_POSTED_DOCUMENT')
            registered[key]=row['net']
        elif row['reason']=='NOT_POSTED_AT_SNAPSHOT':
            expired.append({'store':row['store'],'ticket':row['ticket'],'posted':row['posted'],'revision':row['revision']})
        sites[row['store'],row['sku']].append(row)
    ledgers=[]
    for (store,sku), entries in sorted(sites.items()):
        stashed=Counter(row['reason'] for row in entries if row['net'] is None)
        issued,returned,transfer,breakage=signed_details(entries)
        occupied=daily_adjustments(entries)
        superseded=sum(row.get('superseded',0) for row in entries)
        ledgers.append({'store':store,'sku':sku,'issued':issued,'returned':returned,'transfer':transfer,'discard':breakage,
                        'net_demand':issued-returned,'days':occupied,'closure_verified':sum(day['net_consumption'] for day in occupied)==issued-returned,
                        'late_or_invalid':dict(stashed),'superseded':superseded,'raw_rows':len(entries)+superseded})
    raw=sum(row['raw_rows'] for row in ledgers)+validated['rejected_count']
    return {'inventory_ledgers':ledgers,'gross_valid_documents':len(registered),'late_documents':expired,
            'field_failures':validated['rejected_count'],'balance_ok':raw==validated['accepted_count']+validated['rejected_count'],
            'raw_rows':raw,'total_net_demand':sum(registered.values())}
