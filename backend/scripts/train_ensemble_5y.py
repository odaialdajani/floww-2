#!/usr/bin/env python3
"""Retrain all 5 tickers with 5y data + ensemble. Quick pipeline."""
import sys, json, time, numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.train_real_data_ml import compute_features, FEATURE_NAMES, select_features, walk_forward_cv

MODEL_DIR = Path('models')
MODEL_DIR.mkdir(exist_ok=True)
UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003
TICKERS = ['SPY', 'QQQ', 'DIA', 'IWM', 'TLT']

results = {}
for ticker in TICKERS:
    print(f"\n=== {ticker} ===")
    t0 = time.time()

    # Compute features from 5y data
    df = compute_features(ticker, period='5y')
    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    clean = df[feat_cols + ['target_3class']].dropna().iloc[:-1]
    X_full = clean[feat_cols].values.astype(float)
    y = clean['target_3class'].values.astype(int)

    # 80/20 split
    split = int(len(X_full) * 0.8)
    X_train, X_test = X_full[:split], X_full[split:]
    y_train, y_test = y[:split], y[split:]

    # Feature selection on train only
    sel_names, sel_idx = select_features(X_train, y_train, feat_cols,
                                         min_variance=0.0005, max_correlation=0.90,
                                         max_features=20)
    X_train_sel = X_train[:, sel_idx]
    X_test_sel = X_test[:, sel_idx]

    # Scale
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train_sel)
    X_test_s = scaler.transform(X_test_sel)

    # Candidates
    candidates = {
        'rf': RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=15,
                                      max_features='sqrt', random_state=42, n_jobs=-1),
        'gbm': GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                           subsample=0.7, min_samples_leaf=20, random_state=42),
        'logistic': LogisticRegression(C=0.1, max_iter=1000, solver='lbfgs', random_state=42),
    }

    best_model, best_name, best_score, best_cv = None, None, -999, None
    for name, model in candidates.items():
        cv = walk_forward_cv(model, X_train_s, y_train, n_splits=5, embargo=5)
        print(f"  {name}: wf_acc={cv['mean_test_accuracy']:.4f} ± {cv['std_test_accuracy']:.4f}")
        if cv['mean_test_accuracy'] > best_score:
            best_score = cv['mean_test_accuracy']
            best_model = model
            best_name = name
            best_cv = cv

    if best_model is None or best_cv is None:
        raise RuntimeError(f"No model trained for {ticker}")

    # Train best on full train set
    best_model.fit(X_train_s, y_train)
    train_acc = accuracy_score(y_train, best_model.predict(X_train_s))
    test_acc = accuracy_score(y_test, best_model.predict(X_test_s))
    gap = train_acc - test_acc

    # OOS backtest (last 20%)
    oos_n = len(X_test_s)
    preds = best_model.predict(X_test_s)
    oos_acc = accuracy_score(y_test, preds)

    # Directional P&L
    pnl = []
    for i in range(len(y_test) - 1):
        if preds[i] == 2:  # UP
            pnl.append(1 if y_test[i+1] == 2 else (-1 if y_test[i+1] == 0 else 0))
        elif preds[i] == 0:  # DOWN
            pnl.append(1 if y_test[i+1] == 0 else (-1 if y_test[i+1] == 2 else 0))
    if len(pnl) > 1:
        arr = np.array(pnl)
        sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252)
    else:
        sharpe = 0

    elapsed = time.time() - t0
    print(f"  Best: {best_name} test={test_acc:.4f} gap={gap:.4f} oos={oos_acc:.4f} sharpe={sharpe:.2f} ({elapsed:.1f}s)")

    # Save artifacts
    import joblib
    ts = time.strftime('%Y%m%d_%H%M%S')
    m_path = MODEL_DIR / f'{ticker}_{best_name}_5y_{ts}.joblib'
    s_path = MODEL_DIR / f'{ticker}_{best_name}_5y_{ts}_scaler.joblib'
    manifest_path = MODEL_DIR / f'{ticker}_{best_name}_5y_{ts}_manifest.json'

    joblib.dump(best_model, m_path)
    joblib.dump(scaler, s_path)

    manifest = {
        'ticker': ticker, 'model_type': best_name, 'n_samples': len(X_full),
        'n_train': len(X_train), 'n_test': len(X_test), 'n_features': len(sel_names),
        'feature_names': sel_names, 'train_accuracy': train_acc, 'test_accuracy': test_acc,
        'overfit_gap': gap, 'oos_accuracy': oos_acc, 'oos_n': oos_n,
        'walk_forward_mean': best_cv['mean_test_accuracy'],
        'walk_forward_std': best_cv['std_test_accuracy'],
        'directional_sharpe': round(sharpe, 4), 'n_folds': best_cv['n_folds'],
        'fold_scores': best_cv['fold_test_scores'], 'data': '5y', 'period': '5y',
        'target': 'target_3class_0.3pct',
        'target_thresholds': {'up': UP_THRESHOLD, 'down': DOWN_THRESHOLD},
    }
    for cls, label in [(0,'DOWN'),(1,'HOLD'),(2,'UP')]:
        mask = y_test == cls
        if mask.sum() > 0:
            manifest[f'test_acc_{label.lower()}'] = accuracy_score(y_test[mask], preds[mask])

    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"  Saved: {m_path.name}")

    # Also copy to production naming
    prod_model = MODEL_DIR / f'{ticker}_{best_name}_5y_production.joblib'
    prod_scaler = MODEL_DIR / f'{ticker}_{best_name}_5y_production_scaler.joblib'
    prod_manifest = MODEL_DIR / f'{ticker}_{best_name}_5y_production_manifest.json'
    joblib.dump(best_model, prod_model)
    joblib.dump(scaler, prod_scaler)
    prod_manifest.write_text(json.dumps(manifest, indent=2, default=str))

    results[ticker] = {
        'model': best_name, 'test_acc': test_acc, 'oos_acc': oos_acc,
        'sharpe': round(sharpe, 2), 'gap': gap, 'train_acc': train_acc,
    }

print("\n=== SUMMARY ===")
for t, r in results.items():
    print(f"{t}: {r['model']} test={r['test_acc']:.4f} oos={r['oos_acc']:.4f} sharpe={r['sharpe']:.2f} gap={r['gap']:.4f}")

# Save summary
report_path = MODEL_DIR / f'training_ensemble_5y_{time.strftime("%Y%m%d_%H%M%S")}.json'
report_path.write_text(json.dumps(results, indent=2))
print(f"\nReport: {report_path}")
