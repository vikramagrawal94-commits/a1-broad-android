from __future__ import annotations
import argparse,csv,gzip,json
from dataclasses import asdict,dataclass
from pathlib import Path
from statistics import mean
from shared.candles import parse_rows
from shared.indicators import bollinger
from shared.strategy_engine import evaluate_profile
from backtest_engine.config import BacktestSettings
from strategies.profiles import A1_V1
from shared.history_manifest import candidate_files_for_day
@dataclass
class Trade:
    profile_code:str;profile_name:str;trade_date:str;symbol:str;signal_time:str;entry_time:str;exit_time:str
    entry_price:float;exit_price:float;stop_price:float;quantity:int;exit_reason:str;hold_minutes:int
    gross_pnl:float;charges:float;net_pnl:float;move_5m_pct:float;rsi:float;bb_touches_last_5:int;bb_middle_signal:float;turnover_5m:float
def load(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:p=json.load(f)
    return str(p.get('symbol') or path.stem),parse_rows(p.get('candles',[]))
def first_signal(candles,s,profile=A1_V1):
    r=s.rules
    for i in range(20,len(candles)-2):
        if (candles[i].timestamp.hour,candles[i].timestamp.minute)>=(r.cutoff_hour,r.cutoff_minute):continue
        m=evaluate_profile(candles,i,r,profile)
        if m:return m
    return None
def simulate(candles,symbol,m,s):
    i=m.signal_index; ec=candles[i+1];entry=ec.open;f=m.features
    if f.bb_middle>=entry:return None
    qty=int((s.trade_capital*s.margin_multiple)//entry)
    if qty<1:return None
    stop=entry+s.stop_rupees/qty
    future=candles[i+2:i+2+s.max_holding_minutes]
    if not future:return None
    reason='TIME_EXIT';xp=future[-1].close;xt=future[-1].timestamp;hold=len(future)
    for n,c in enumerate(future,1):
        if c.high>=stop:reason='STOP';xp=stop;xt=c.timestamp;hold=n;break
        idx=i+1+n;bands=bollinger([x.close for x in candles[:idx+1]],20,2)
        if bands is None:continue
        target=float(bands[0])
        if c.open<=target:reason='TARGET';xp=c.open;xt=c.timestamp;hold=n;break
        if c.low<=target:reason='TARGET';xp=target;xt=c.timestamp;hold=n;break
    gross=(entry-xp)*qty;net=gross-s.charges_per_trade
    return Trade(m.profile.code,m.profile.name,ec.timestamp.date().isoformat(),symbol,candles[i].timestamp.isoformat(),ec.timestamp.isoformat(),xt.isoformat(),round(entry,4),round(xp,4),round(stop,4),qty,reason,hold,round(gross,2),round(s.charges_per_trade,2),round(net,2),round(f.move_5m_pct,4),round(f.rsi,2),f.bb_touches_last_5,round(f.bb_middle,4),round(f.turnover_5m,2))
def metrics(ts):
    ts=sorted(ts,key=lambda x:(x.entry_time,x.symbol));p=[t.net_pnl for t in ts];wins=[x for x in p if x>0];loss=[x for x in p if x<=0];eq=peak=dd=0
    for x in p:eq+=x;peak=max(peak,eq);dd=max(dd,peak-eq)
    return dict(trades=len(ts),win_rate=round(len(wins)/len(ts)*100,2) if ts else 0,net_pnl=round(sum(p),2),expectancy=round(mean(p),2) if p else 0,profit_factor=round(sum(wins)/abs(sum(loss)),2) if loss and sum(loss)!=0 else None,max_drawdown=round(dd,2),targets=sum(t.exit_reason=='TARGET' for t in ts),stops=sum(t.exit_reason=='STOP' for t in ts),time_exits=sum(t.exit_reason=='TIME_EXIT' for t in ts))
def write_csv(path,rows):
    rows=list(rows);path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:path.write_text('',encoding='utf-8');return
    with path.open('w',newline='',encoding='utf-8') as h:w=csv.DictWriter(h,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
def run(days=60,cache_dir=None):
    s=BacktestSettings();root=cache_dir or s.cache_dir;dirs=sorted(p for p in root.iterdir() if p.is_dir() and p.name[:4].isdigit()) if root.exists() else [];dirs=dirs[-days:] if days>0 else dirs
    if not dirs:raise SystemExit(f'No historical cache found under {root.resolve()}. Run HISTORY ENGINE first.')
    trades=[]
    for d in dirs:
        print('Scanning',d.name)
        paths, _, _, _ = candidate_files_for_day(d)
        for path in paths:
            try:
                symbol,candles=load(path);m=first_signal(candles,s)
                if m:
                    t=simulate(candles,symbol,m,s)
                    if t:trades.append(t)
            except Exception as e:print('WARN',path.name,e)
    out=s.output_dir;out.mkdir(parents=True,exist_ok=True);write_csv(out/'exact_engine_trades.csv',(asdict(t) for t in trades));m=metrics(trades);summary={'profile_code':'A1-V1','profile_name':'A1_CANONICAL_REVERSAL',**m};write_csv(out/'exact_engine_summary.csv',[summary]);(out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('\nA1 V1 SHARED LIVE/PAPER CANDLE-LAYER BACKTEST');print(f"Trades {m['trades']} | Win {m['win_rate']:.2f}% | Net P/L {m['net_pnl']:.2f} | Exp/Tr {m['expectancy']:.2f} | PF {m['profit_factor']} | DD {m['max_drawdown']:.2f}")
    print('LIVE/PAPER uses the same selected candle/turnover/time filters. No order-book/delta entry gate.')
    print('Saved:',out.resolve());return trades,m
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--days',type=int,default=60);ap.add_argument('--cache-dir',type=Path);a=ap.parse_args();run(a.days,a.cache_dir)
if __name__=='__main__':main()
