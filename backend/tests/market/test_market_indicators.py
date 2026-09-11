from app.market.services.indicators import calculate_indicators


def test_calculate_indicators_returns_columns():
    candles = [
        {"close": float(index), "volume": 100.0}
        for index in range(1, 40)
    ]

    result = calculate_indicators(candles)

    assert "sma" in result.columns
    assert "ema" in result.columns
    assert "rsi" in result.columns
    assert "macd" in result.columns
