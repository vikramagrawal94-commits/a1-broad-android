from pathlib import Path
import gzip
import json
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
OUTPUT = DATA / "nse_equities.json"
TEMP = DATA / "NSE.json.gz"

URLS = [
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz",
]

def download_with_retries(url: str, attempts: int = 3) -> bytes:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            print(f"Attempt {attempt}/{attempts}: {url}")
            response = requests.get(
                url,
                timeout=(15, 60),
                headers={"User-Agent": "Mozilla/5.0 UpstoxScanner/1.1"},
            )
            response.raise_for_status()
            content = response.content
            if len(content) < 1000:
                raise RuntimeError(f"Downloaded file is unexpectedly small: {len(content)} bytes")
            if content[:2] != b"\x1f\x8b":
                raise RuntimeError("Response is not a gzip file.")
            return content
        except Exception as exc:
            last_error = exc
            print(f"Download failed: {exc}")
            if attempt < attempts:
                print("Waiting 3 seconds before retry...")
                time.sleep(3)
    raise RuntimeError(f"All download attempts failed. Last error: {last_error}")

def parse_equities(content: bytes) -> list[dict]:
    TEMP.write_bytes(content)
    try:
        with gzip.open(TEMP, "rt", encoding="utf-8") as handle:
            instruments = json.load(handle)
    finally:
        TEMP.unlink(missing_ok=True)

    if not isinstance(instruments, list):
        raise RuntimeError("Instrument file did not contain a JSON list.")

    equities = [
        x for x in instruments
        if x.get("segment") == "NSE_EQ"
        and x.get("instrument_type") == "EQ"
        and x.get("instrument_key")
        and x.get("trading_symbol")
        and x.get("security_type", "NORMAL") == "NORMAL"
    ]
    if len(equities) < 100:
        raise RuntimeError(
            f"Only {len(equities)} normal NSE equities were found; refusing to replace the file."
        )
    return equities

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in URLS:
        try:
            content = download_with_retries(url)
            equities = parse_equities(content)
            OUTPUT.write_text(json.dumps(equities, indent=2), encoding="utf-8")
            print(f"\nSUCCESS: Saved {len(equities)} NSE equities to:")
            print(OUTPUT)
            return
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            print(f"Source failed: {exc}\n")

    print("Could not refresh the complete NSE list.")
    print("TEST mode will still work because its instruments are built in.")
    print("\nDetails:")
    for error in errors:
        print("-", error)
    raise SystemExit(1)

if __name__ == "__main__":
    main()
