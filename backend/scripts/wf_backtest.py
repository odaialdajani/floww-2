#!/usr/bin/env python3
"""Comprehensive walk-forward backtest for all production models."""
import sys, json, numpy as np, pandas as pd, joblib
from pathlib import Path
from sklearn.metrics import accuracy_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_real_data_ml import compute_features, FEATURE_NAMES

MODEL_DIR = Path('models')
PROD_MODELS = {
    'SPY': ('SPY_rf_production.joblib', 'SPY_rf_production_scaler.joblib'),
    'QQQ': ('QQQ_rf_production.joblib', 'QQQ_rf_production_scaler.joblib'),
    'DIA': ('DIA_rf_production.joblib', 'DIA_rf_production_scaler.joblib'),
    'IWM': ('IWM_rf_production.joblib', 'IWM_rf_production_scaler.joblib'),
    'TLT': ('TLT_rf_production.joblib', 'TLT_rf_production_scaler.joblib'),
}

results = {}
for ticker, (model_name, scaler_name) in PROD_MODELS.items():
    print(f"\n=== {ticker} ===")
    model_path = MODEL_DIR / model_name
    scaler_path = MODEL_DIR / scaler_name
    manifest_path = MODEL_DIR / model_name.replace('.joblib', '_manifest.json')

    if not model_path.exists():
        print(f"  SKIP: {model_name} not found")
        continue

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    # Load manifest for selected features
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        sel_names = manifest.get('feature_names', [])
    else:
        sel_names = []

    # Get data
    df = compute_features(ticker, period='5y')
    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    clean = df[feat_cols + ['target_3class']].dropna().iloc[:-1]
    X = clean[feat_cols].values.astype(float)
    y = clean['target_3class'].values.astype(int)

    # Use selected features
    if sel_names:
        sel_idx = [feat_cols.index(f) for f in sel_names if f in feat_cols]
        X_sel = X[:, sel_idx]
    else:
        # Fallback: use all features model expects
        n_expected = scaler.n_features_in_
        X_sel = X[:, :n_expected] if X.shape[1] >= n_expected else X

    X_s = scaler.transform(X_sel)

    # Walk-forward evaluation (5 folds, embargo=5)
    fold_size = len(X_s) // (5 + 1)
    fold_results = []
    for fold in range(5):
        train_end = fold_size * (fold + 1)
        test_start = train_end + 5  # embargo
        test_end = min(test_start + fold_size, len(X_s))
        if test_end > len(X_s) or test_start >= len(X_s):
            break

        model_clone = type(model)(**model.get_params())
        model_clone.fit(X_s[:train_end], y[:train_end])
        preds = model_clone.predict(X_s[test_start:test_end])
        actuals = y[test_start:test_end]
        acc = accuracy_score(actuals, preds)

        # Directional P&L
        pnl = []
        for i in range(len(actuals) - 1):
            if preds[i] == 2:
                pnl.append(1 if actuals[i+1] == 2 else (-1 if actuals[i+1] == 0 else 0))
            elif preds[i] == 0:
                pnl.append(1 if actuals[i+1] == 0 else (-1 if actuals[i+1] == 2 else 0))
        sharpe = 0
        if len(pnl) > 1:
            arr = np.array(pnl)
            sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252)

        fold_results.append({'acc': acc, 'sharpe': sharpe, 'n_test': len(actuals)})
        print(f"  Fold {fold+1}: acc={acc:.4f} sharpe={sharpe:.2f} n={len(actuals)}")

    if fold_results:
        mean_acc = np.mean([f['acc'] for f in fold_results])
        mean_sharpe = np.mean([f['sharpe'] for f in fold_results])
        total_trades = sum(f['n_test'] for f in fold_results)
        print(f"  Mean: acc={mean_acc:.4f} sharpe={mean_sharpe:.2f}")
        results[ticker] = {'mean_acc': round(mean_acc, 4), 'mean_sharpe': round(mean_sharpe, 2), 'nfolds': len(fold_results)}
    else:
        results[ticker] = {'error': 'no folds evaluated'}

print("\n=== WALK-FORWARD BACKTEST SUMMARY ===")
for t, r in results.items():
    if 'error' in r:
        print(f"{t}: ERROR - {r['error']}")
    else:
        print(f"{t}: acc={r['mean_acc']:.4f} sharpe={r['mean_sharpe']:.2f} folds={r['nfolds']}")

# Save
report_path = MODEL_DIR / f'wf_backtest_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.json'
report_path.write_text(json.dumps(results, indent=2))
print(f"\nSaved: {report_path}")
