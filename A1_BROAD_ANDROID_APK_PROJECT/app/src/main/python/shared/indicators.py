import math

def ema(values, period):
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    alpha = 2 / (period + 1)
    for x in values[period:]:
        value = alpha * x + (1 - alpha) * value
    return value

def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = [max(x, 0) for x in changes[-period:]]
    losses = [max(-x, 0) for x in changes[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

def bollinger(values, period=20, multiplier=2):
    if len(values) < period:
        return None
    sample = values[-period:]
    middle = sum(sample) / period
    std = math.sqrt(sum((x-middle)**2 for x in sample) / period)
    return middle, middle + multiplier*std, middle - multiplier*std
