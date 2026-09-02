from __future__ import annotations

import json
from pathlib import Path


def safe_symbol(symbol: str) -> str:
    return str(symbol).replace('/', '_').replace('\\', '_').replace(':', '_')


def candidate_files_for_day(day_dir: Path):
    """Return files selected by the latest history-engine manifest.

    A manifest is authoritative when present. This prevents stale candle files
    left by older discovery settings from silently entering a new backtest.
    Older caches without a manifest retain the legacy behavior of scanning all
    .json.gz files.

    Returns: (paths, reasons_by_symbol, discovery_metadata, manifest_present)
    """
    manifest_path = day_dir / 'candidate_manifest.json'
    meta_path = day_dir / 'discovery_settings.json'
    metadata = {}
    if meta_path.exists():
        try:
            metadata = json.loads(meta_path.read_text(encoding='utf-8'))
        except Exception:
            metadata = {}

    if not manifest_path.exists():
        return sorted(day_dir.glob('*.json.gz')), {}, metadata, False

    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        # Corrupt manifest should be visible rather than silently broadening the
        # backtest population.
        raise RuntimeError(f'Invalid candidate manifest: {manifest_path}')

    if not isinstance(payload, list):
        raise RuntimeError(f'Candidate manifest must be a list: {manifest_path}')

    reasons = {}
    paths = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get('symbol') or '').strip()
        if not symbol:
            continue
        reasons[symbol] = item.get('reasons') or []
        path = day_dir / f'{safe_symbol(symbol)}.json.gz'
        if path.exists():
            paths.append(path)
    return sorted(paths), reasons, metadata, True
