from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
import gzip
import json
import random
import threading
import time

import requests

from history_engine.config import HistorySettings
from history_engine.instruments import choose


class RateLimiter:
    """Shared adaptive limiter for concurrent historical requests.

    It starts at the configured request rate, slows down automatically after
    HTTP 429 responses, and cautiously recovers after successful requests.
    Worker count controls concurrency; this limiter controls aggregate pace.
    """

    def __init__(self, requests_per_second: float, minimum_rps: float = 2.0):
        self.target_rps = max(requests_per_second, 0.1)
        self.current_rps = self.target_rps
        self.minimum_rps = min(max(minimum_rps, 0.1), self.target_rps)
        self.lock = threading.Lock()
        self.next_allowed = 0.0
        self.successes_since_throttle = 0
        self.rate_limit_events = 0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next_allowed - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            interval = 1.0 / max(self.current_rps, 0.1)
            self.next_allowed = max(now, self.next_allowed) + interval

    def report_rate_limit(self) -> float:
        with self.lock:
            self.rate_limit_events += 1
            self.successes_since_throttle = 0
            self.current_rps = max(self.minimum_rps, self.current_rps * 0.70)
            return self.current_rps

    def report_success(self) -> float:
        with self.lock:
            self.successes_since_throttle += 1
            if self.successes_since_throttle >= 100 and self.current_rps < self.target_rps:
                self.current_rps = min(self.target_rps, self.current_rps + 1.0)
                self.successes_since_throttle = 0
            return self.current_rps

    def snapshot(self) -> tuple[float, int]:
        with self.lock:
            return self.current_rps, self.rate_limit_events


_thread_local = threading.local()


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
        session.mount("https://", adapter)
        _thread_local.session = session
    return session


def previous_weekdays(count: int) -> list[str]:
    result: list[str] = []
    cursor = date.today() - timedelta(days=1)
    while len(result) < count:
        if cursor.weekday() < 5:
            result.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return sorted(result)


def _request_candle_chunk(settings: HistorySettings, limiter: RateLimiter, key: str, interval: int,
                          start_date: str, end_date: str) -> list:
    """Download one Upstox-valid historical chunk.

    Upstox V3 limits minute intervals from 1 to 15 minutes to a maximum
    retrieval window of one calendar month. Keeping chunks at 28 days avoids
    UDAPI1148 when the user asks for 30 trading days (usually 40+ calendar days).
    """
    encoded = quote(key, safe="")
    url = f"{settings.historical_base_url}/{encoded}/minutes/{interval}/{end_date}/{start_date}"
    headers = {
        "Authorization": f"Bearer {settings.token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    last_error: Exception | None = None

    for attempt in range(settings.history_max_retries + 1):
        limiter.wait()
        try:
            response = get_session().get(url, headers=headers, timeout=settings.history_request_timeout)
            if response.status_code == 429:
                limiter.report_rate_limit()
                retry_after = float(response.headers.get("Retry-After", "0") or 0)
                time.sleep(max(retry_after, settings.history_retry_base_seconds * (2 ** attempt)) + random.random())
                continue
            if response.status_code >= 500:
                time.sleep(settings.history_retry_base_seconds * (2 ** attempt) + random.random())
                continue
            if response.status_code != 200:
                body = response.text[:500].replace("\n", " ")
                raise RuntimeError(f"HTTP {response.status_code}: {body} | URL: {url}")
            candles = response.json().get("data", {}).get("candles", [])
            limiter.report_success()
            return candles
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            # Retrying will not repair normal 4xx validation/authentication errors.
            if isinstance(exc, RuntimeError) and "HTTP 4" in str(exc):
                break
            if attempt < settings.history_max_retries:
                time.sleep(settings.history_retry_base_seconds * (2 ** attempt) + random.random())

    raise RuntimeError(f"Historical request failed: {last_error}")


def request_candles(settings: HistorySettings, limiter: RateLimiter, key: str, interval: int,
                    start_date: str, end_date: str) -> list:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError(f"end_date {end_date} is before start_date {start_date}")

    # Upstox allows only one month per request for 1-15 minute candles.
    max_span_days = 28 if interval <= 15 else 80
    rows: list = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=max_span_days - 1), end)
        rows.extend(_request_candle_chunk(
            settings, limiter, key, interval, cursor.isoformat(), chunk_end.isoformat()
        ))
        cursor = chunk_end + timedelta(days=1)

    # Chunks and Upstox responses can be reverse ordered. Deduplicate by timestamp.
    by_timestamp = {row[0]: row for row in rows if isinstance(row, list) and row}
    return [by_timestamp[ts] for ts in sorted(by_timestamp)]


def discover(rows: list, move_threshold: float, slope_threshold: float) -> dict[str, list[dict]]:
    """Loose candidate discovery only; this is NOT an A1 trade filter.

    With HISTORICAL_DISCOVERY_INTERVAL=1 the input rows are completed 1-minute
    candles. The existing discovery definition is retained: the current close
    is compared with the earliest close in the most recent three discovery
    candles from the same day, and slope is expressed as average percent/minute
    over that elapsed window. The actual A1 engine later applies its independent
    RSI / rolling-5m move / BB-touch / turnover rules to the downloaded candles.

    Raw move/slope values are stored alongside rounded display values so the
    backtest dashboard can re-evaluate stricter discovery move/slope combinations
    from the baseline 1.0% move / 0.50% per-minute slope candidate superset
    without re-running the downloader.
    """
    parsed = []
    for row in rows:
        if len(row) < 6:
            continue
        try:
            ts = datetime.fromisoformat(row[0])
            parsed.append((ts, float(row[4]), int(row[5])))
        except (TypeError, ValueError):
            continue
    parsed.sort(key=lambda x: x[0])
    hits: dict[str, list[dict]] = defaultdict(list)

    for i in range(1, len(parsed)):
        ts, close, volume = parsed[i]
        same_day = [x for x in parsed[max(0, i - 2):i + 1] if x[0].date() == ts.date()]
        if len(same_day) < 2:
            continue
        baseline = same_day[0][1]
        minutes = max((ts - same_day[0][0]).total_seconds() / 60, 1)
        move = ((close / baseline) - 1) * 100 if baseline else 0
        slope = move / min(minutes, 3)
        if move >= move_threshold or slope >= slope_threshold:
            hits[ts.date().isoformat()].append({
                "time": ts.isoformat(),
                "move": round(move, 3),
                "slope": round(slope, 3),
                "move_raw": move,
                "slope_raw": slope,
                "volume": volume,
            })
    return hits


def safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("\\", "_").replace(":", "_")


def load_or_download_discovery(settings: HistorySettings, limiter: RateLimiter, key: str,
                               symbol: str, interval: int, start_date: str,
                               end_date: str, discovery_root: Path) -> tuple[str, dict]:
    cache = discovery_root / f"{safe_symbol(symbol)}.json.gz"
    if cache.exists() and cache.stat().st_size > 50:
        with gzip.open(cache, "rt", encoding="utf-8") as fh:
            rows = json.load(fh).get("candles", [])
    else:
        rows = request_candles(settings, limiter, key, interval, start_date, end_date)
        temp = cache.with_suffix(cache.suffix + ".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as fh:
            json.dump({"instrument_key": key, "symbol": symbol, "candles": rows}, fh)
        temp.replace(cache)
    hits = discover(rows, settings.historical_discovery_move, settings.historical_discovery_slope)
    # When discovery itself is 1-minute, these rows are already the exact detail
    # candles. Return them so Stage 2 can materialize shortlisted stock-days
    # locally instead of making duplicate API requests.
    return key, hits, (rows if interval == 1 else None)


def materialize_candidate_day(settings: HistorySettings, key: str, symbol: str, day: str,
                              reasons: list[dict], day_rows: list) -> dict:
    """Write one shortlisted day from already-downloaded 1-minute discovery rows."""
    day_rows = sorted(day_rows, key=lambda r: r[0])
    day_dir = settings.cache_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    target = day_dir / f"{safe_symbol(symbol)}.json.gz"
    if day_rows and not (target.exists() and target.stat().st_size > 50):
        temp = target.with_suffix(target.suffix + ".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as fh:
            json.dump({"symbol": symbol, "instrument_key": key, "date": day, "candles": day_rows}, fh)
        temp.replace(target)
    return {"symbol": symbol, "instrument_key": key, "reasons": reasons}


def download_candidate_day(settings: HistorySettings, limiter: RateLimiter, key: str,
                           symbol: str, day: str, reasons: list[dict]) -> dict:
    day_dir = settings.cache_dir / day
    day_dir.mkdir(parents=True, exist_ok=True)
    target = day_dir / f"{safe_symbol(symbol)}.json.gz"
    if not (target.exists() and target.stat().st_size > 50):
        rows = request_candles(settings, limiter, key, 1, day, day)
        temp = target.with_suffix(target.suffix + ".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as fh:
            json.dump({"symbol": symbol, "instrument_key": key, "date": day, "candles": rows}, fh)
        temp.replace(target)
    return {"symbol": symbol, "instrument_key": key, "reasons": reasons}


def eta_text(started: float, completed: int, total: int) -> str:
    if completed <= 0:
        return "calculating"
    elapsed = time.monotonic() - started
    remaining = max(total - completed, 0) * elapsed / completed
    mins, secs = divmod(int(remaining), 60)
    return f"{mins:02d}:{secs:02d}"


def main() -> None:
    settings = HistorySettings()
    settings.validate()
    raw = input("How many previous trading days? [5]: ").strip() or "5"
    count = max(1, int(raw))
    dates = previous_weekdays(count)
    start_date, end_date = dates[0], dates[-1]
    keys, names = choose(settings)
    interval = settings.historical_discovery_interval
    discovery_root = settings.discovery_dir / f"{start_date}_to_{end_date}_{interval}m"
    discovery_root.mkdir(parents=True, exist_ok=True)
    candidate_map: dict[str, dict[str, list[dict]]] = defaultdict(dict)

    print(f"\nA1 STREAMING HISTORY + 1-MINUTE DOWNLOAD PIPELINE")
    print(f"Stage 1/3: selecting stocks with {interval}-minute discovery candles, then downloading their 1-minute candles.")
    print(f"Parallel workers: {settings.history_discovery_workers} | rate cap: {settings.history_discovery_rps:.1f} requests/sec")
    print("Cached stocks are skipped automatically; interrupted runs can be resumed.\n")

    # One shared limiter keeps the combined discovery + detail traffic inside
    # a single aggregate request budget while both pools run concurrently.
    shared_limiter = RateLimiter(settings.history_total_rps, settings.history_min_rps)
    discovery_limiter = shared_limiter
    detail_limiter = shared_limiter
    failures = 0
    detailed_failures = 0
    discovery_started = time.monotonic()
    detail_started = time.monotonic()
    error_path = discovery_root / "errors.txt"
    manifests: dict[str, list[dict]] = defaultdict(list)
    scheduled_pairs: set[tuple[str, str]] = set()
    detail_futures: dict = {}
    detail_completed = 0

    def consume_finished_detail(block: bool = False) -> None:
        """Collect completed one-minute downloads while discovery continues."""
        nonlocal detailed_failures, detail_completed
        if not detail_futures:
            return
        finished = []
        if block:
            finished = list(as_completed(list(detail_futures)))
        else:
            finished = [future for future in list(detail_futures) if future.done()]
        for future in finished:
            day, key = detail_futures.pop(future)
            detail_completed += 1
            try:
                manifests[day].append(future.result())
            except Exception as exc:
                detailed_failures += 1
                day_dir = settings.cache_dir / day
                day_dir.mkdir(parents=True, exist_ok=True)
                with (day_dir / "download_errors.txt").open("a", encoding="utf-8") as fh:
                    fh.write(f"{key}\t{exc}\n")

    if interval == 1:
        print("1-minute discovery optimization: shortlisted daily candle files are reused")
        print("from Stage-1 discovery data; duplicate 1-minute API downloads are avoided.\n")
    else:
        print("V24 improvement: one-minute candidate downloads begin immediately while")
        print("the remaining stocks are still being scanned. No stage-barrier waiting.\n")

    with ThreadPoolExecutor(max_workers=settings.history_discovery_workers) as discovery_executor, \
            ThreadPoolExecutor(max_workers=settings.history_detail_workers) as detail_executor:
        discovery_futures = {
            discovery_executor.submit(
                load_or_download_discovery, settings, discovery_limiter, key,
                names.get(key, key), interval, start_date, end_date, discovery_root
            ): key for key in keys
        }

        for idx, future in enumerate(as_completed(discovery_futures), 1):
            key = discovery_futures[future]
            try:
                returned_key, hits, discovery_rows = future.result()
                symbol = names.get(returned_key, returned_key)
                discovery_rows_by_day = defaultdict(list)
                if interval == 1 and discovery_rows is not None:
                    for row in discovery_rows:
                        if not isinstance(row, list) or not row:
                            continue
                        try:
                            discovery_rows_by_day[datetime.fromisoformat(row[0]).date().isoformat()].append(row)
                        except (TypeError, ValueError):
                            continue
                for day, reasons in hits.items():
                    if day not in dates:
                        continue
                    candidate_map[day][returned_key] = reasons
                    pair = (day, returned_key)
                    if pair not in scheduled_pairs:
                        scheduled_pairs.add(pair)
                        if interval == 1 and discovery_rows is not None:
                            # 1-minute discovery already contains the detail data;
                            # reuse it locally to avoid a second network download.
                            detail_future = detail_executor.submit(
                                materialize_candidate_day, settings, returned_key,
                                symbol, day, reasons, discovery_rows_by_day.get(day, [])
                            )
                        else:
                            detail_future = detail_executor.submit(
                                download_candidate_day, settings, detail_limiter,
                                returned_key, symbol, day, reasons
                            )
                        detail_futures[detail_future] = pair
            except Exception as exc:
                failures += 1
                with error_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"{key}\t{exc}\n")

            consume_finished_detail(block=False)
            if idx % 10 == 0 or idx == len(keys):
                found = len(scheduled_pairs)
                current_rps, rate_limits = shared_limiter.snapshot()
                print(
                    f"\rDiscovery {idx}/{len(keys)} | pairs {found} | 1m done {detail_completed}/{found} "
                    f"| failures {failures}+{detailed_failures} "
                    f"| combined pace {current_rps:.1f} rps "
                    f"| 429s {rate_limits} "
                    f"| ETA {eta_text(discovery_started, idx, len(keys))}",
                    end="", flush=True,
                )

        print("\n\nDiscovery complete. Waiting only for remaining one-minute candidate downloads.")
        consume_finished_detail(block=True)

    print(
        f"Detailed downloads complete: {detail_completed}/{len(scheduled_pairs)} "
        f"| failures {detailed_failures} | elapsed {eta_text(detail_started, len(scheduled_pairs), len(scheduled_pairs))}"
    )

    for day in dates:
        day_dir = settings.cache_dir / day
        day_dir.mkdir(parents=True, exist_ok=True)
        manifest = sorted(manifests.get(day, []), key=lambda x: x["symbol"])
        (day_dir / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (day_dir / "discovery_settings.json").write_text(json.dumps({
            "interval_minutes": interval,
            "move_threshold_pct": settings.historical_discovery_move,
            "slope_threshold_pct_per_min": settings.historical_discovery_slope,
            "logic": "move >= threshold OR slope >= threshold",
            "slope_window": "average pct/min using up to the last 3 discovery candles from the same day",
        }, indent=2), encoding="utf-8")

    print("\n\nHistorical candidate discovery complete.")
    for day in dates:
        print(f" {day}: {len(candidate_map.get(day, {}))} candidates")

    print('\nHistory download finished. Now run BACKTEST ENGINE.')


if __name__ == "__main__":
    main()
