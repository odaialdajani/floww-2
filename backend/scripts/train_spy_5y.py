#!/usr/bin/env python3
"""
scripts/train_spy_5y.py

Train ML models on 5 years of SPY data downloaded live from yfinance.
66 engineered features, walk-forward CV, RF/GBM/Logistic models.
Saves production artifacts + generates report.

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_spy_5y
    cd backend && .venv/bin/python3 -m scripts.train_spy_5y --ticker SPY --period 5y
    cd backend && .venv/bin/python3 -m scripts.train_spy_5y --quick
    cd backend && .venv/bin/python3 -m scripts.train_spy_5y --all-tickers
"""
from __future__ import annotations

import argparse, json, logging, time, sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("train_spy_5y")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def download_data(ticker: str, period: str = "5y") -> pd.DataFrame:
    log.info("Downloading %s (%s)...", ticker, period)
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"]).copy()
    log.info("Downloaded %d rows, %s to %s", len(df), df.index[0], df.index[-1])
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer 66 features from OHLCV. Fully vectorized."""
    features = pd.DataFrame(index=df.index)
    close  = df["Close"].astype(float)
    high   = df["High"].astype(float)
    low    = df["Low"].astype(float)
    volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(1.0, index=df.index)
    open_  = df["Open"].astype(float) if "Open" in df.columns else close

    # Returns
    for h in [1, 2, 3, 5, 10, 15, 21, 60]:
        features[f"ret_{h}d"] = close.pct_change(h)
    features["log_ret_1d"] = np.log(close / close.shift(1))
    features["overnight_gap"] = open_ / close.shift(1) - 1.0

    # SMAs + price-relative
    for w in [5, 10, 21, 50, 100, 200]:
        sma = close.rolling(w, min_periods=w).mean()
        features[f"sma_{w}"] = sma
        features[f"price_vs_sma_{w}"] = close / sma - 1.0
    sma5 = close.rolling(5).mean()
    sma21 = close.rolling(21).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    features["sma_5_21_diff"] = sma5 - sma21
    features["sma_10_50_diff"] = close.rolling(10).mean() - sma50
    features["sma_21_200_diff"] = sma21 - sma200
    features["sma_5_21_cross"] = np.sign(features["sma_5_21_diff"])
    features["golden_cross"] = ((sma50.shift(1) < sma200.shift(1)) & (sma50 > sma200)).astype(float)

    # ATR
    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    for w in [7, 14, 21]:
        features[f"atr_{w}"] = tr.rolling(w, min_periods=w).mean()
    features["atr_14_pct"] = features["atr_14"] / close

    # Volume
    for w in [5, 10, 21, 50]:
        features[f"vol_sma_{w}"] = volume.rolling(w, min_periods=w).mean()
    features["rel_vol_5_21"] = features["vol_sma_5"] / (features["vol_sma_21"] + 1e-10)
    features["vol_ratio_5_21"] = volume / (features["vol_sma_21"] + 1e-10)
    features["vol_chg_5d"] = volume.pct_change(5)

    # Realized volatility
    lr = features["log_ret_1d"]
    for w in [5, 10, 21, 60]:
        features[f"realvol_{w}d"] = lr.rolling(w, min_periods=w).std() * np.sqrt(252)
    features["vol_ratio_5_21_real"] = features["realvol_5d"] / (features["realvol_21d"] + 1e-10)
    features["vol_regime"] = (features["realvol_21d"] > features["realvol_21d"].rolling(60).mean()).astype(float)

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14, min_periods=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14, min_periods=14).mean()
    rs = gain / (loss + 1e-10)
    features["rsi_14"] = 100 - (100 / (1 + rs))
    features["rsi_overbought"] = (features["rsi_14"] > 70).astype(float)
    features["rsi_oversold"] = (features["rsi_14"] < 30).astype(float)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_sig = macd.ewm(span=9, adjust=False).mean()
    features["macd"] = macd
    features["macd_signal"] = macd_sig
    features["macd_hist"] = macd - macd_sig
    features["macd_cross"] = np.sign(features["macd_hist"])

    # Bollinger Bands
    sma20 = close.rolling(20, min_periods=20).mean()
    std20 = close.rolling(20, min_periods=20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    features["bb_upper"] = bb_upper
    features["bb_lower"] = bb_lower
    features["bb_width"] = (bb_upper - bb_lower) / (sma20 + 1e-10)
    features["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)

    # Momentum / Mean Reversion
    features["ret_momentum"] = close.pct_change(5)
    features["ret_accel"] = close.pct_change(5).diff()
    features["mean_rev_21d"] = (close - sma21) / (std20 + 1e-10)
    features["ret_skew_21d"] = lr.rolling(21).skew()
    features["ret_kurt_21d"] = lr.rolling(21).kurt()

    # Calendar
    dates = pd.to_datetime(features.index)
    features["day_of_week"] = dates.dayofweek.astype(float)
    features["day_of_month"] = dates.day.astype(float)
    features["month"] = dates.month.astype(float)
    features["is_month_end"] = dates.is_month_end.astype(float)
    features["is_month_start"] = dates.is_month_start.astype(float)
    features["is_fomc_month"] = (dates.month.isin([3,6,9,12])).astype(float)

    # Targets
    next_ret = close.pct_change(1).shift(-1)
    features["target_1d_ret"] = next_ret
    features["target_dir"] = (next_ret > 0).astype(int)
    target3 = pd.Series(1, index=features.index, dtype=int)
    target3 = target3.where(~next_ret.gt(0.003), 2)
    target3 = target3.where(~next_ret.lt(-0.003), 0)
    features["target_3class"] = target3

    features = features.replace([np.inf, -np.inf], np.nan)
    log.info("Engineered %d features", len([c for c in features.columns if not c.startswith("target")]))
    return features


def select_features(X, y, names, max_features=30, min_var=1e-6, max_corr=0.92):
    mask = np.ones(X.shape[1], dtype=bool)
    var = np.var(X, axis=0)
    mask[var < min_var] = False
    idx = np.where(mask)[0]
    if len(idx) > 1:
        cm = np.corrcoef(X[:, idx], rowvar=False)
        drop = set()
        for i in range(len(idx)):
            for j in range(i+1, len(idx)):
                if abs(cm[i,j]) > max_corr:
                    drop.add(idx[j])
        for d in drop: mask[d] = False
    idx = np.where(mask)[0]
    if len(idx) > max_features:
        from sklearn.ensemble import RandomForestClassifier
        rf = RandomForestClassifier(n_estimators=50, max_depth=3, random_state=42, n_jobs=-1)
        rf.fit(X[:, idx], y)
        top = np.argsort(rf.feature_importances_)[-max_features:]
        new_mask = np.zeros(X.shape[1], dtype=bool)
        new_mask[idx[top]] = True
        mask = new_mask
    sel = [names[i] for i in range(len(names)) if mask[i]]
    log.info("Selected %d features: %s", len(sel), sel[:12])
    return sel, [i for i in range(len(names)) if mask[i]]


def walk_forward_cv(model, X, y, n_splits=5, embargo=5):
    from sklearn.metrics import accuracy_score
    from sklearn.base import clone
    fold_size = len(X) // (n_splits + 1)
    accs, sharpes, gaps = [], [], []
    for fold in range(n_splits):
        te = fold_size * (fold + 1)
        ts = te + embargo
        te_end = min(ts + fold_size, len(X))
        if te_end > len(X) or ts >= len(X): break
        m = clone(model)
        m.fit(X[:te], y[:te])
        p_train = m.predict(X[:te])
        p_test = m.predict(X[ts:te_end])
        y_test = y[ts:te_end]
        train_acc = accuracy_score(y[:te], p_train)
        test_acc = accuracy_score(y_test, p_test)
        rets = []
        for p, a in zip(p_test, y_test):
            if p == 2:   rets.append(1.0 if a == 2 else -1.0)
            elif p == 0: rets.append(-1.0 if a == 0 else 1.0)
            else:        rets.append(0.0)
        sharpe = float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))
        accs.append(test_acc); sharpes.append(sharpe)
        gaps.append(train_acc - test_acc)
        log.info("  Fold %d: train=%.4f test=%.4f sharpe=%.3f", fold+1, train_acc, test_acc, sharpe)
    return {
        "n_folds": len(accs),
        "mean_acc": float(np.mean(accs)), "std_acc": float(np.std(accs)),
        "mean_sharpe": float(np.mean(sharpes)), "mean_gap": float(np.mean(gaps)),
        "fold_accs": [float(a) for a in accs], "fold_sharpes": [float(s) for s in sharpes],
    }


def train_ticker(ticker: str, period: str = "5y", quick: bool = False, target_type: str = "both"):
    t0 = time.time()
    df = download_data(ticker, period)
    feats = engineer_features(df)
    feat_cols = [c for c in feats.columns if not c.startswith("target")]
    clean = feats[feat_cols + ["target_dir", "target_3class"]].copy()
    clean[feat_cols] = clean[feat_cols].fillna(0.0)
    clean = clean.dropna(subset=["target_dir", "target_3class"]).iloc[:-1]
    log.info("Clean: %d rows", len(clean))

    results = {}
    for tname, tcol in [("2class", "target_dir"), ("3class", "target_3class")]:
        if target_type not in ("both", tname): continue
        log.info("\n%s — %s", ticker, tname)
        y = clean[tcol].values.astype(int)
        X_all = clean[feat_cols].values.astype(float)
        for cls in sorted(np.unique(y)):
            log.info("  Class %d: %.1f%% (%d)", cls, (y==cls).mean()*100, (y==cls).sum())

        split = int(len(X_all) * 0.8)
        X_tr, X_te = X_all[:split], X_all[split:]
        y_tr, y_te = y[:split], y[split:]
        log.info("Train: %d  Test: %d", len(X_tr), len(X_te))

        sel_names, sel_idx = select_features(X_tr, y_tr, feat_cols, max_features=30)
        X_tr_s = X_tr[:, sel_idx]; X_te_s = X_te[:, sel_idx]

        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr_s); X_te_s = scaler.transform(X_te_s)

        from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        n_est = 50 if quick else 300
        candidates = {
            "rf": RandomForestClassifier(n_estimators=n_est, max_depth=5, min_samples_leaf=10, max_features="sqrt", random_state=42, n_jobs=-1),
            "gbm": GradientBoostingClassifier(n_estimators=n_est, max_depth=3, learning_rate=0.05, subsample=0.7, min_samples_leaf=15, random_state=42),
            "logistic": LogisticRegression(C=0.1, max_iter=1000, solver="lbfgs", random_state=42),
        }

        best_model, best_name, best_score, best_cv = None, None, -999, None
        for name, model in candidates.items():
            cv = walk_forward_cv(model, X_tr_s, y_tr, n_splits=3 if quick else 5, embargo=5)
            score = cv["mean_sharpe"] + cv["mean_acc"]
            log.info("  %s: acc=%.4f ± %.4f, sharpe=%.3f", name, cv["mean_acc"], cv["std_acc"], cv["mean_sharpe"])
            if score > best_score:
                best_score, best_model, best_name, best_cv = score, model, name, cv

        log.info("Best: %s (score=%.4f)", best_name, best_score)
        best_model.fit(X_tr_s, y_tr)

        from sklearn.metrics import accuracy_score, classification_report
        p_te = best_model.predict(X_te_s)
        te_acc = accuracy_score(y_te, p_te)
        tr_acc = accuracy_score(y_tr, best_model.predict(X_tr_s))

        rets = []
        for p, a in zip(p_te, y_te):
            if p == (2 if tname == "3class" else 1): rets.append(1.0 if a == p else -1.0)
            elif p == 0: rets.append(-1.0 if a == 0 else 1.0)
            else: rets.append(0.0)
        te_sharpe = float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))

        maj_cls = int(pd.Series(y_tr).mode().iloc[0])
        maj_acc = accuracy_score(y_te, [maj_cls]*len(y_te))
        per_acc = accuracy_score(y_te, np.roll(y_te, 1))

        labels = ["DOWN","HOLD","UP"] if tname=="3class" else ["DOWN","UP"]
        log.info("\n%s", classification_report(y_te, p_te, target_names=labels, zero_division=0))

        results[tname] = {
            "model_type": best_name, "n_train": len(X_tr), "n_test": len(X_te),
            "n_features": len(sel_names), "feature_names": sel_names,
            "train_acc": tr_acc, "test_acc": te_acc, "test_sharpe": te_sharpe,
            "overfit_gap": tr_acc - te_acc,
            "wf_mean_acc": best_cv["mean_acc"], "wf_std_acc": best_cv["std_acc"],
            "wf_mean_sharpe": best_cv["mean_sharpe"], "wf_gap": best_cv["mean_gap"],
            "n_folds": best_cv["n_folds"], "fold_accs": best_cv["fold_accs"],
            "fold_sharpes": best_cv["fold_sharpes"],
            "majority_baseline": maj_acc, "persistence_baseline": per_acc,
            "beats_majority": te_acc > maj_acc, "beats_persistence": te_acc > per_acc,
        }

        # Save artifacts
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        import joblib
        mpath = MODELS_DIR / f"{ticker}_{best_name}_{tname}_{ts_str}.joblib"
        spath = MODELS_DIR / f"{ticker}_{best_name}_{tname}_{ts_str}_scaler.joblib"
        apath = MODELS_DIR / f"{ticker}_{best_name}_{tname}_{ts_str}_manifest.json"
        joblib.dump(best_model, mpath)
        joblib.dump(scaler, spath)
        manifest = {k: v for k, v in results[tname].items() if k not in ("fold_accs","fold_sharpes")}
        manifest["model_path"] = str(mpath); manifest["scaler_path"] = str(spath)
        manifest["created_at"] = datetime.now(UTC).isoformat()
        with open(apath, "w") as f: json.dump(manifest, f, indent=2, default=str)
        log.info("Saved: %s", mpath.name)

    results["elapsed_sec"] = round(time.time() - t0, 1)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--target", choices=["2class","3class","both"], default="both")
    parser.add_argument("--all-tickers", action="store_true")
    args = parser.parse_args()

    tickers = ["SPY","QQQ","DIA","IWM","TLT"] if args.all_tickers else [args.ticker.upper()]
    all_results = {}
    for ticker in tickers:
        try:
            all_results[ticker] = train_ticker(ticker, args.period, args.quick, args.target)
        except Exception as e:
            log.error("Failed %s: %s", ticker, e, exc_info=True)
            all_results[ticker] = {"error": str(e)}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rpath = REPORTS_DIR / f"train_spy_5y_{ts}.json"
    with open(rpath, "w") as f: json.dump(all_results, f, indent=2, default=str)
    log.info("Report: %s", rpath)

    # Summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    for ticker, tr in sorted(all_results.items()):
        if "error" in tr:
            print(f"{ticker}: ERROR - {tr['error']}")
            continue
        for tname in ["2class", "3class"]:
            if tname in tr:
                r = tr[tname]
                print(f"\n{ticker} {tname}: {r['model_type']} | test={r['test_acc']:.4f} | sharpe={r['test_sharpe']:.3f} | wf={r['wf_mean_acc']:.4f}±{r['wf_std_acc']:.4f} | gap={r['overfit_gap']:.4f} | beats_maj={r['beats_majority']}")

if __name__ == "__main__":
    main()
