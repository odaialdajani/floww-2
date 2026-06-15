#!/usr/bin/env python3
"""Train models optimized for directional Sharpe, not accuracy.
Uses custom Sharpe-based selection and more features."""
import sys, time, numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.train_real_data_ml import compute_features, FEATURE_NAMES, select_features

MODEL_DIR = Path('models')
UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003

def compute_sharpe(y_true, y_pred):
    """Compute directional Sharpe from predictions vs actuals."""
    pnl = []
    for i in range(len(y_true) - 1):
        if y_pred[i] == 2:  # predicted UP -> long
            pnl.append(1 if y_true[i+1] == 2 else (-1 if y_true[i+1] == 0 else 0))
        elif y_pred[i] == 0:  # predicted DOWN -> short
            pnl.append(1 if y_true[i+1] == 0 else (-1 if y_true[i+1] == 2 else 0))
    if len(pnl) < 5:
        return 0
    arr = np.array(pnl)
    return arr.mean() / (arr.std() + 1e-10) * np.sqrt(252)

def walk_forward_sharpe(model, X, y, n_splits=5, embargo=5):
    """Walk-forward evaluating Sharpe on each fold."""
    fold_size = len(X) // (n_splits + 1)
    sharpe_scores = []
    for fold in range(n_splits):
        train_end = fold_size * (fold + 1)
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, len(X))
        if test_end > len(X) or test_start >= len(X):
            break
        model_clone = type(model)(**model.get_params())
        model_clone.fit(X[:train_end], y[:train_end])
        preds = model_clone.predict(X[test_start:test_end])
        actuals = y[test_start:test_end]
        sharpe = compute_sharpe(actuals, preds)
        sharpe_scores.append(sharpe)
    if not sharpe_scores:
        return {'mean_sharpe': 0, 'std_sharpe': 0}
    return {'mean_sharpe': float(np.mean(sharpe_scores)),
            'std_sharpe': float(np.std(sharpe_scores)),
            'fold_sharpe': [float(s) for s in sharpe_scores]}

results = {}
for ticker in ['DIA', 'IWM']:
    print(f"\n=== {ticker} (Sharpe-optimized) ===")
    t0 = time.time()

    df = compute_features(ticker, period='5y')
    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    clean = df[feat_cols + ['target_3class']].dropna().iloc[:-1]
    X_full = clean[feat_cols].values.astype(float)
    y = clean['target_3class'].values.astype(int)
    split = int(len(X_full) * 0.8)
    X_train, X_test = X_full[:split], X_full[split:]
    y_train, y_test = y[:split], y[split:]

    sel_names, sel_idx = select_features(X_train, y_train, feat_cols,
                                         min_variance=0.0003, max_correlation=0.85,
                                         max_features=30)
    X_train_sel = X_train[:, sel_idx]
    X_test_sel = X_test[:, sel_idx]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train_sel)
    X_test_s = scaler.transform(X_test_sel)

    candidates = {
        'rf_100': RandomForestClassifier(n_estimators=100, max_depth=4, min_samples_leaf=25,
                                         max_features='sqrt', random_state=42, n_jobs=-1),
        'rf_300': RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=15,
                                         max_features='sqrt', random_state=42, n_jobs=-1),
        'rf_deep': RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=10,
                                          max_features='log2', random_state=42, n_jobs=-1),
        'gbm': GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.03,
                                           subsample=0.7, min_samples_leaf=25, random_state=42),
        'gbm_deep': GradientBoostingClassifier(n_estimators=300, max_depth=4, learning_rate=0.02,
                                                subsample=0.6, min_samples_leaf=30, random_state=42),
        'logistic': LogisticRegression(C=0.05, max_iter=2000, solver='lbfgs', random_state=42),
    }

    best_model, best_name, best_sharpe, best_cv = None, None, -999, None
    for name, model in candidates.items():
        cv = walk_forward_sharpe(model, X_train_s, y_train)
        print(f"  {name}: sharpe={cv['mean_sharpe']:.2f} ± {cv['std_sharpe']:.2f}")
        if cv['mean_sharpe'] > best_sharpe:
            best_sharpe = cv['mean_sharpe']
            best_model = model
            best_name = name
            best_cv = cv

    if best_model is None:
        raise RuntimeError(f"No model for {ticker}")

    best_model.fit(X_train_s, y_train)
    train_acc = accuracy_score(y_train, best_model.predict(X_train_s))
    test_acc = accuracy_score(y_test, best_model.predict(X_test_s))
    preds = best_model.predict(X_test_s)
    oos_acc = accuracy_score(y_test, preds)
    oos_sharpe = compute_sharpe(y_test, preds)

    elapsed = time.time() - t0
    print(f"  Best: {best_name} sharpe={oos_sharpe:.2f} acc={test_acc:.4f} ({elapsed:.1f}s)")

    import joblib
    ts = time.strftime('%Y%m%d_%H%M%S')
    m_path = MODEL_DIR / f'{ticker}_{best_name}_sharpe_{ts}.joblib'
    s_path = MODEL_DIR / f'{ticker}_{best_name}_sharpe_{ts}_scaler.joblib'

    joblib.dump(best_model, m_path)
    joblib.dump(scaler, s_path)

    results[ticker] = {
        'model': best_name, 'test_acc': test_acc, 'oos_acc': oos_acc,
        'oos_sharpe': round(oos_sharpe, 2), 'gap': train_acc - test_acc,
        'cv_sharpe': best_cv['mean_sharpe'],
        'path': str(m_path),
    }

print("\n=== SUMMARY ===")
for t, r in results.items():
    print(f"{t}: {r['model']} sharpe={r['oos_sharpe']:.2f} acc={r['test_acc']:.4f} cv_sharpe={r['cv_sharpe']:.2f}")
