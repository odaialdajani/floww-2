# Live model audit — 27 Sep 2026

Produced by `qc/audit/truth_audit.sh`, which runs as step 4 of every CI
`backend-tests` job. It is the repo's only automated overfit check.

## Why this needed a separate run

Rules 9-12 (Sharpe ceiling, sample floor, feature/sample ratio, accuracy
ceiling) only **block** when the commit subject claims ML/model work. On every
other commit they print `WARN`. That scoping is deliberate — the script's own
comments say enforcing them unconditionally "would block unrelated work on
pre-existing model debt — the fastest way to get a gate switched off."

The consequence is that normal commits report `24 passed, 0 failed` while this
debt sits unread. To surface it without changing any enforcement, run the
audit against a commit subject that trips the trigger:

```bash
git worktree add --detach /tmp/probe origin/main
cd /tmp/probe
git commit --allow-empty -m 'chore: quarantine degenerate models'
bash qc/audit/truth_audit.sh
```

## Findings: 6 violations across 24 audited models

All six models are in `backend/models/` and **live, not quarantined**. All were
trained 2026-05-24.

| Model | Finding |
|---|---|
| `SPY_rf_20260524_020801_meta.json` | **`avg_test_sharpe` 8.0202 > 5** |
| `SPY_rf_20260524_020801_meta.json` | feature/sample ratio **0.28125** (45 features / 160 samples) |
| `IWM_rf_20260524_022147_meta.json` | feature/sample ratio **0.275** (44 / 160) |
| `TLT_rf_20260524_022154_meta.json` | feature/sample ratio **0.275** (44 / 160) |
| `QQQ_rf_20260524_022055_meta.json` | feature/sample ratio **0.275** (44 / 160) |
| `QQQ_rf_20260524_022118_meta.json` | feature/sample ratio **0.275** (44 / 160) |

`SPY_rf_20260524_020801` also reports `avg_test_accuracy` 0.82 on daily
direction. Its `sharpe`, `n_train`, `trained_at` and `ticker` fields are
`null` — the values above come from the walk-forward schema
(`avg_test_sharpe` / `fold_details[].n_train`).

## What this is and is not

**This is a measurement, not a verdict.** Nothing here has been changed,
quarantined, or retrained. The ratio rule flags 44-45 features against 160
samples as thin; whether that is acceptable for this feature set is a modeling
decision, and the 6 identical failures across 4 tickers suggest a shared
training configuration rather than four independent problems.

The Sharpe 8.0202 is the one to look at first. Sharpe above 5 on *daily
direction* is the specific overfit signature Rule 9 exists to catch, and 8.02
is far enough past the threshold that it is unlikely to be a rounding artifact.

**It is not evidence of predictive skill.** A high backtest Sharpe on a model
whose own audit flags it as overfit is evidence about the fitting procedure,
not about the market. If these models feed any ranking, conviction, or
trade-type decision, that path is exactly where an overfit artifact does the
most damage, and the honest state is "unvalidated" until the artifact is
explained.

## Status

Open question, deliberately not actioned. Retraining or quarantining a model is
a judgment about which artifacts to trust, and that is not a call to make
silently inside a docs commit.
