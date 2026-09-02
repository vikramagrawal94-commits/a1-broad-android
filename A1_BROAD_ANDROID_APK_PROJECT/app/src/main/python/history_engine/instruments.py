import json
def choose(settings):
    items=json.loads(settings.instruments_file.read_text(encoding='utf-8'));selected=[]
    for x in items:
        if x.get('segment')=='NSE_EQ' and x.get('instrument_type')=='EQ' and x.get('security_type','NORMAL')=='NORMAL' and x.get('instrument_key') and x.get('trading_symbol'):selected.append(x)
    if len(selected)<500:raise RuntimeError(f'Only {len(selected)} normal NSE equities found. Run instrument refresh.')
    selected=selected[:5000];return [x['instrument_key'] for x in selected],{x['instrument_key']:x['trading_symbol'] for x in selected}
