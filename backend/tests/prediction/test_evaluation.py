import pytest

from app.prediction.evaluation import backtest, evaluate


def test_known_regression_and_direction_metrics():
    result = evaluate([0.1, -0.1], [0.05, -0.05], [0.8, 0.2], [100, 100])
    assert result["mae"] == pytest.approx(5)
    assert result["rmse"] == pytest.approx(5)
    assert result["accuracy"] == result["precision"] == result["recall"] == result["f1"] == 1
    assert result["baseline_mae"] == pytest.approx(10)


def test_backtest_delays_signal_and_charges_entry_and_exit():
    result = backtest([0.5, 0.1, 0], [0.1, 0.1, 0.1], [0.8, 0.8, 0.8], fee_bps=10)
    # Cannot earn the first 50% move: the first signal has not executed yet.
    assert result["total_return"] == pytest.approx(1.1 * 0.999 ** 2 - 1)
    assert result["turnover"] == 2
    assert result["max_drawdown"] <= 0
