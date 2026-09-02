from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
import csv
import json
import os
import time

import requests

from backtest_engine.config import BacktestSettings
from backtest_engine.multi_profile_backtest import load, first_signal, simulate, metrics
from history_engine.config import HistorySettings
from history_engine.download_history import (
    RateLimiter,
    previous_weekdays,
    load_or_download_discovery,
    materialize_candidate_day,
)
from history_engine.instruments import choose
from shared.a1_rules import candle_filter_label
from shared.history_manifest import candidate_files_for_day

PACKAGE_ROOT = Path(__file__).resolve().parent
INSTRUMENTS_FILE = PACKAGE_ROOT / "data" / "nse_equities.json"


def strategy_summary() -> str:
    return "\n".join([
        "SELECTED A1 BROAD SETUP",
        "RSI >90 and <98",
        "Rolling 5-minute move >2.5%",
        "Upper-BB touches exactly 2, 3, or 5 in the last 5m",
        "5-minute turnover >Rs2Cr and <Rs7Cr",
        "No NEW signals from 11:00 to 11:59",
        "SHORT entry: next 1-minute open",
        "Target: dynamic middle Bollinger Band (1.00x)",
        "Stop: Rs150 per trade",
        "Max hold: 20 minutes",
        "Capital Rs5,000 | Margin 5x | Backtest charges Rs50",
        "",
        "60-day canonical research reference:",
        "311 trades | Net P&L Rs18,261.45 | PF 1.55 | Max DD Rs2,838.01",
        "Past performance is not a guarantee of future returns.",
    ])


def _base(base_dir: str) -> Path:
    p = Path(base_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _history_settings(base_dir: str, token: str) -> HistorySettings:
    base = _base(base_dir)
    # Keep mobile request load deliberately below the desktop build.
    return replace(
        HistorySettings(),
        token=(token or "").strip(),
        instruments_file=INSTRUMENTS_FILE,
        cache_dir=base / "cache",
        discovery_dir=base / "discovery",
        historical_discovery_interval=1,
        historical_discovery_move=1.0,
        historical_discovery_slope=0.50,
        history_discovery_workers=4,
        history_detail_workers=2,
        history_total_rps=6.0,
        history_discovery_rps=6.0,
        history_detail_rps=4.0,
        history_min_rps=1.0,
    )


def diagnostics(base_dir: str, token: str) -> str:
    base = _base(base_dir)
    checks = []
    token = (token or "").strip()
    checks.append((bool(token), "Upstox token present"))
    try:
        count = len(json.loads(INSTRUMENTS_FILE.read_text(encoding="utf-8")))
        checks.append((count > 500, f"Packaged NSE instrument file: {count} rows"))
    except Exception as exc:
        checks.append((False, f"NSE instrument file error: {exc}"))
    if token:
        try:
            r = requests.get(
                "https://api.upstox.com/v2/user/profile",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=20,
            )
            checks.append((r.status_code == 200, f"Upstox authorization HTTP {r.status_code}"))
        except Exception as exc:
            checks.append((False, f"Upstox connection error: {exc}"))
    base.mkdir(parents=True, exist_ok=True)
    lines = ["A1 MOBILE DIAGNOSTICS"]
    for ok, msg in checks:
        lines.append(("PASS  " if ok else "FAIL  ") + msg)
    return "\n".join(lines)


def download_history(base_dir: str, token: str, days: int) -> str:
    settings = _history_settings(base_dir, token)
    settings.validate()
    days = max(1, int(days))
    dates = previous_weekdays(days)
    start_date, end_date = dates[0], dates[-1]
    keys, names = choose(settings)
    interval = 1
    discovery_root = settings.discovery_dir / f"{start_date}_to_{end_date}_{interval}m"
    discovery_root.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)

    limiter = RateLimiter(settings.history_total_rps, settings.history_min_rps)
    manifests: dict[str, list[dict]] = defaultdict(list)
    candidate_map: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    failures = 0
    processed = 0
    started = time.monotonic()

    def worker(key: str):
        return load_or_download_discovery(
            settings, limiter, key, names.get(key, key), interval,
            start_date, end_date, discovery_root,
        )

    with ThreadPoolExecutor(max_workers=settings.history_discovery_workers) as ex:
        futures = {ex.submit(worker, key): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            processed += 1
            try:
                returned_key, hits, discovery_rows = future.result()
                symbol = names.get(returned_key, returned_key)
                by_day = defaultdict(list)
                for row in discovery_rows or []:
                    if not isinstance(row, list) or not row:
                        continue
                    try:
                        d = datetime.fromisoformat(row[0]).date().isoformat()
                        by_day[d].append(row)
                    except Exception:
                        pass
                for day, reasons in hits.items():
                    if day not in dates:
                        continue
                    candidate_map[day][returned_key] = reasons
                    item = materialize_candidate_day(
                        settings, returned_key, symbol, day, reasons, by_day.get(day, [])
                    )
                    manifests[day].append(item)
            except Exception as exc:
                failures += 1
                with (discovery_root / "errors.txt").open("a", encoding="utf-8") as fh:
                    fh.write(f"{key}\t{exc}\n")

    for day in dates:
        day_dir = settings.cache_dir / day
        day_dir.mkdir(parents=True, exist_ok=True)
        manifest = sorted(manifests.get(day, []), key=lambda x: x.get("symbol", ""))
        (day_dir / "candidate_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (day_dir / "discovery_settings.json").write_text(json.dumps({
            "interval_minutes": 1,
            "move_threshold_pct": 1.0,
            "slope_threshold_pct_per_min": 0.50,
            "logic": "move >= threshold OR slope >= threshold",
            "purpose": "loose discovery only; actual A1 trade engine uses canonical filters",
        }, indent=2), encoding="utf-8")

    summary = {
        "days_requested": days,
        "start_date": start_date,
        "end_date": end_date,
        "stocks_scanned": processed,
        "failures": failures,
        "candidate_stock_days": sum(len(v) for v in candidate_map.values()),
        "elapsed_minutes": round((time.monotonic() - started) / 60, 2),
        "cache_dir": str(settings.cache_dir),
    }
    (settings.cache_dir / "mobile_history_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return "A1 HISTORY COMPLETE\n" + "\n".join(f"{k}: {v}" for k, v in summary.items())


def run_backtest(base_dir: str, days: int) -> str:
    base = _base(base_dir)
    cache = base / "cache"
    dirs = sorted(p for p in cache.iterdir() if p.is_dir() and p.name[:4].isdigit()) if cache.exists() else []
    dirs = dirs[-max(1, int(days)):] if dirs else []
    if not dirs:
        return "No cached 1-minute candles. Run Download / discover history first."

    settings = replace(
        BacktestSettings(),
        cache_dir=cache,
        output_dir=base / "reports",
    )
    trades = []
    files = 0
    candidate_signals = 0
    warnings = 0
    for day_dir in dirs:
        paths, _, _, _ = candidate_files_for_day(day_dir)
        for path in paths:
            files += 1
            try:
                symbol, candles = load(path)
                match = first_signal(candles, settings)
                if match:
                    candidate_signals += 1
                    trade = simulate(candles, symbol, match, settings)
                    if trade:
                        trades.append(trade)
            except Exception:
                warnings += 1

    trades = sorted(trades, key=lambda t: (t.entry_time, t.symbol))
    m = metrics(trades)
    report_dir = base / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "a1_mobile_trades.csv"
    if trades:
        rows = [asdict(t) for t in trades]
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8")

    summary = {
        "days_tested": len(dirs),
        "files_scanned": files,
        "candidate_signals": candidate_signals,
        "warnings": warnings,
        **m,
        "filters": candle_filter_label(),
        "target": "1.00x dynamic middle BB",
        "stop_rupees": 150,
        "max_hold_minutes": 20,
    }
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    text = "\n".join([
        "A1 BROAD MOBILE CANONICAL BACKTEST",
        f"Days: {summary['days_tested']} | Files: {files} | Trades: {m['trades']}",
        f"Win rate: {m['win_rate']:.2f}%",
        f"Net P&L: Rs{m['net_pnl']:.2f}",
        f"Expectancy/trade: Rs{m['expectancy']:.2f}",
        f"Profit factor: {m['profit_factor']}",
        f"Max drawdown: Rs{m['max_drawdown']:.2f}",
        f"Targets: {m['targets']} | Stops: {m['stops']} | Time exits: {m['time_exits']}",
        "",
        "Filters: " + candle_filter_label(),
        "Target: 1.00x dynamic middle BB | Stop Rs150 | Hold 20m",
        f"Trade CSV: {csv_path}",
    ])
    (report_dir / "report.txt").write_text(text, encoding="utf-8")
    return text


def cached_days(base_dir: str) -> str:
    cache = _base(base_dir) / "cache"
    if not cache.exists():
        return "No cached history yet."
    days = sorted(p.name for p in cache.iterdir() if p.is_dir() and p.name[:4].isdigit())
    if not days:
        return "No cached history yet."
    return f"Cached trading days: {len(days)}\nFirst: {days[0]}\nLast: {days[-1]}"


def latest_report(base_dir: str) -> str:
    p = _base(base_dir) / "reports" / "report.txt"
    if not p.exists():
        return "No backtest report yet."
    return p.read_text(encoding="utf-8")
