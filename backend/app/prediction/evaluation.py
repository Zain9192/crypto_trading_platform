from __future__ import annotations

import numpy as np
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, precision_score, recall_score


def evaluate(actual_returns, predicted_returns, up_probability, current_prices) -> dict[str, float]:
    actual = np.asarray(actual_returns)
    forecast = np.asarray(predicted_returns)
    prices = np.asarray(current_prices)
    truth, direction = actual > 0, np.asarray(up_probability) >= 0.5
    return {
        "mae": float(mean_absolute_error(prices * (1 + actual), prices * (1 + forecast))),
        "rmse": float(np.sqrt(np.mean((prices * (actual - forecast)) ** 2))),
        "return_mae": float(np.mean(np.abs(actual - forecast))),
        "baseline_mae": float(np.mean(np.abs(prices * actual))),
        "baseline_rmse": float(np.sqrt(np.mean((prices * actual) ** 2))),
        "accuracy": float(accuracy_score(truth, direction)),
        "precision": float(precision_score(truth, direction, zero_division=0)),
        "recall": float(recall_score(truth, direction, zero_division=0)),
        "f1": float(f1_score(truth, direction, zero_division=0)),
    }


def backtest(actual_returns, forecasts, up_probability, fee_bps: float = 10) -> dict:
    """Long/cash, delayed one bar: signal at close t trades only after close t+1.

    The delay avoids crediting a trade at the very close used to create its signal.
    Fees apply on every position transition, including final liquidation.
    """
    if not 0 <= fee_bps <= 1000:
        raise ValueError("Fee must be between 0 and 1000 basis points")
    actual = np.asarray(actual_returns, dtype=float)
    signal = ((np.asarray(forecasts) > 0) & (np.asarray(up_probability) >= 0.5)).astype(float)
    position = np.concatenate(([0.0], signal[:-1]))
    turnover = np.abs(np.diff(np.concatenate(([0.0], position))))
    if len(turnover):
        turnover[-1] += position[-1]
    net = (1 + position * actual) * (1 - fee_bps / 10000) ** turnover - 1
    equity = np.cumprod(1 + net)
    peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    return {
        "total_return": float(equity[-1] - 1) if len(equity) else 0.0,
        "buy_hold_return": float(np.prod(1 + actual) - 1),
        "max_drawdown": float(np.min(equity / peak - 1)) if len(equity) else 0.0,
        "turnover": float(turnover.sum()), "fee_bps": fee_bps,
        "execution": "one_bar_delayed_long_cash", "equity": equity.tolist(),
    }
