# A1 Broad Research Android APK

Android/Chaquopy edition of the selected A1 broad setup.

## Canonical strategy

- SHORT only
- RSI >90 and <98
- rolling 5-minute move >2.5%
- upper-Bollinger touches exactly 2, 3, or 5 in the last five 1-minute candles
- 5-minute turnover > Rs2Cr and < Rs7Cr
- no new signals 11:00-11:59
- entry next 1-minute open
- dynamic middle-BB target (1.00x)
- Rs150 stop per trade
- 20-minute maximum hold
- Rs5,000 capital, 5x margin
- Rs50 backtest charges

Reference canonical 60-day research result: 311 trades, Rs18,261.45 net, PF 1.55, max DD Rs2,838.01.

## APK scope

This mobile APK performs Upstox diagnostics, 1-minute historical discovery/download, and local canonical backtesting. Real-money order placement is intentionally disabled in the APK. Keep the app open during large downloads.

## Automatic build

GitHub Actions builds `app-debug.apk` on every push to `main` and exposes it as the artifact **A1-Broad-Research-APK**.
