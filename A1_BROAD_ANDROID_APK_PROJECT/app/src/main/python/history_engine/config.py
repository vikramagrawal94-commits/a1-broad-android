from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
@dataclass(frozen=True)
class HistorySettings:
    token:str=os.getenv('UPSTOX_ACCESS_TOKEN','').strip()
    historical_base_url:str='https://api.upstox.com/v3/historical-candle'
    instruments_file:Path=ROOT/'data'/'nse_equities.json'
    cache_dir:Path=ROOT/'cache'
    discovery_dir:Path=ROOT/'discovery'
    historical_discovery_interval:int=int(os.getenv('HISTORICAL_DISCOVERY_INTERVAL','1'))
    historical_discovery_move:float=float(os.getenv('HISTORICAL_DISCOVERY_MOVE','1.0'))
    historical_discovery_slope:float=float(os.getenv('HISTORICAL_DISCOVERY_SLOPE','0.50'))
    history_discovery_workers:int=int(os.getenv('HISTORY_DISCOVERY_WORKERS','20'))
    # Separate display/config caps retained for compatibility with the original downloader.
    # The downloader currently enforces the shared aggregate HISTORY_TOTAL_RPS limiter.
    history_discovery_rps:float=float(os.getenv('HISTORY_DISCOVERY_RPS','15'))
    history_detail_rps:float=float(os.getenv('HISTORY_DETAIL_RPS','8'))
    history_detail_workers:int=int(os.getenv('HISTORY_DETAIL_WORKERS','20'))
    history_total_rps:float=float(os.getenv('HISTORY_TOTAL_RPS','12'))
    history_min_rps:float=float(os.getenv('HISTORY_MIN_RPS','2'))
    history_request_timeout:int=int(os.getenv('HISTORY_REQUEST_TIMEOUT','30'))
    history_max_retries:int=int(os.getenv('HISTORY_MAX_RETRIES','4'))
    history_retry_base_seconds:float=float(os.getenv('HISTORY_RETRY_BASE_SECONDS','1.5'))
    def validate(self):
        if not self.token:
            raise RuntimeError('UPSTOX_ACCESS_TOKEN is missing. Open .env and paste a fresh token.')
        if not self.instruments_file.exists():
            raise RuntimeError('NSE instrument file missing. Run Refresh NSE instruments from the launcher.')
        if self.history_discovery_workers <= 0 or self.history_detail_workers <= 0:
            raise RuntimeError('History worker counts must be greater than zero.')
        if self.history_total_rps <= 0 or self.history_min_rps <= 0:
            raise RuntimeError('History request-rate settings must be greater than zero.')
