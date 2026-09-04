import pandas as pd


def calculate_indicators(candles: list[dict]) -> dict:
    df = pd.DataFrame(candles)

    close = df["close"]
    sma = close.rolling(20).mean()
    ema = close.ewm(span=20, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    macd = (
        close.ewm(span=12, adjust=False).mean()
        - close.ewm(span=26, adjust=False).mean()
    )

    std = close.rolling(20).std()

    return {
        "sma": sma.iloc[-1],
        "ema": ema.iloc[-1],
        "rsi": rsi.iloc[-1],
        "macd": macd.iloc[-1],
        "bollinger_upper": (sma + (2 * std)).iloc[-1],
        "bollinger_lower": (sma - (2 * std)).iloc[-1],
    }
