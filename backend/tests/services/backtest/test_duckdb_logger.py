import pytest

from services.backtest.duckdb_logger import BacktestDuckDBLogger
from services.backtest.report import BacktestResult, TradeRecord


def result(pnl=20.0):
    return BacktestResult(
        ticker="SPY", initial_capital=1000, total_bars=2,
        equity_curve=[1000, 1000 + pnl], drawdown_curve=[0],
        trades=[TradeRecord(entry_bar_idx=0, exit_bar_idx=1, quantity=1,
                            entry_price=10, exit_price=30, net_pnl=pnl, pnl=pnl)],
        metrics={"total_pnl": pnl, "sharpe": 1.5, "n_trades": 1},
    )


def test_persistent_roundtrip_and_unknown_metrics(tmp_path):
    path = str(tmp_path / "backtest.duckdb")
    with BacktestDuckDBLogger(path) as log:
        log.log_all([result()], run_id="one")
    with BacktestDuckDBLogger(path) as log:
        report = log.summary("one")
        assert report["trades"][0]["total_pnl"] == 20
        assert report["meta"][0]["sortino"] is None
        assert report["meta"][0]["calmar"] is None
        assert log.equity_curve("one")[1]["drawdown"] is None


def test_exact_run_identity_and_fold_separation():
    with BacktestDuckDBLogger() as log:
        log.log_all([result(20), result(-5)], run_id="run_%")
        log.log_all([result(999)], run_id="run_%extra")
        report = log.summary("run_%")
        assert report["trades"][0]["count"] == 2
        assert report["trades"][0]["total_pnl"] == 15
        assert [m["total_pnl"] for m in report["meta"]] == [20, -5]
        assert [p["fold"] for p in log.equity_curve("run_%")] == [0, 0, 1, 1]


def test_repeated_run_replaces_data_and_removed_folds():
    with BacktestDuckDBLogger() as log:
        log.log_all([result(), result()], run_id="run")
        log.log_all([result(7)], run_id="run")
        assert log.summary("run")["trades"][0]["count"] == 1
        assert len(log.summary("run")["meta"]) == 1
        assert len(log.equity_curve("run")) == 2


def test_invalid_data_does_not_partially_replace_previous_run():
    with BacktestDuckDBLogger() as log:
        log.log_all([result()], run_id="run")
        bad = result(7)
        bad.trades[0].quantity = True
        with pytest.raises(ValueError):
            log.log_all([result(9), bad], run_id="run")
        assert log.summary("run")["trades"][0]["total_pnl"] == 20


def test_unknown_nonfinite_metrics_are_null_and_not_ranked():
    with BacktestDuckDBLogger() as log:
        r = result()
        r.metrics["sharpe"] = float("inf")
        log.log_all([r], run_id="unknown")
        assert log.summary("unknown")["meta"][0]["sharpe"] is None
        assert log.leaderboard() == []


def test_empty_run_is_explicitly_empty():
    with BacktestDuckDBLogger() as log:
        log.log_all([], run_id="empty")
        assert log.summary("empty")["meta"] == []
        assert log.summary("empty")["trades"][0]["count"] == 0
        assert log.summary("empty")["trades"][0]["total_pnl"] is None


def test_database_failure_rolls_back_all_three_tables(monkeypatch):
    with BacktestDuckDBLogger() as log:
        log.log_all([result()], run_id="run")
        insert = log._insert
        def fail_equity(table, rows):
            if table == "equity_curve":
                raise RuntimeError("disk failure")
            insert(table, rows)
        monkeypatch.setattr(log, "_insert", fail_equity)
        with pytest.raises(RuntimeError, match="disk failure"):
            log.log_all([result(7)], run_id="run")
        assert log.summary("run")["trades"][0]["total_pnl"] == 20
        assert log.summary("run")["meta"][0]["total_pnl"] == 20
        assert log.equity_curve("run")[1]["equity"] == 1020


def test_unknown_trade_is_not_summed_as_zero():
    with BacktestDuckDBLogger() as log:
        data = result()
        data.trades.append(TradeRecord(net_pnl=None, quantity=1))
        log.log_all([data], run_id="unknown-trade")
        totals = log.summary("unknown-trade")["trades"][0]
        assert totals["count"] == 2 and totals["known_pnl_count"] == 1
        assert totals["total_pnl"] is None


def test_extreme_totals_remain_serializable_unknown():
    with BacktestDuckDBLogger() as log:
        data = result()
        data.trades = [TradeRecord(net_pnl=1e308, quantity=1), TradeRecord(net_pnl=1e308, quantity=1)]
        log.log_all([data], run_id="extreme")
        assert log.summary("extreme")["trades"][0]["total_pnl"] is None
