from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_timestamp(value) -> datetime:
    return datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))


def parse_rows(rows) -> list[Candle]:
    result=[]
    for row in rows or []:
        try:
            if isinstance(row, dict):
                ts=row.get('timestamp') or row.get('time')
                o,h,l,c,v=row['open'],row['high'],row['low'],row['close'],row.get('volume',0)
            else:
                if len(row)<6: continue
                ts,o,h,l,c,v=row[:6]
            result.append(Candle(parse_timestamp(ts),float(o),float(h),float(l),float(c),float(v)))
        except (TypeError,ValueError,KeyError):
            continue
    result.sort(key=lambda x:x.timestamp)
    return result
