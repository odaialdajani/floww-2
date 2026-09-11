"""
backend/services/flow_calibration.py

Stage-gated calibrated probability P(move) for Tidehunter Pro alerts.

Replaces the false precision of hand-tuned score weights (two significant
figures from six hand-picked constants) with a MEASURED probability that
the underlying moves ≥ k·σ within N sessions after an alert — provided by
the outcome ledger (services/flow_outcomes.py).

Stage ladder (sample-size honesty is contractual — see outcome_stats):
  STAGE 0  n < 60 measured alerts   → NO MODEL. Every row carries
            p_move=None, p_method="uncalibrated", p_n=<n>. The UI shows
            "uncalibrated: n=k". No fabricated probability, ever.
  STAGE 1  60 ≤ n < 300             → EMPIRICAL hit rate per score DECILE
            (≥6 events per decile required, else that decile is None),
            each with a Wilson 95% CI. Cold-start-safe; no feature matrix.
  STAGE 2  n ≥ 300 AND walk-forward
            Brier beats the decile baseline → L2-regularized logistic
            regression on frozen features. Promoted ONLY when it beats
            stage 1 out-of-time; otherwise stage 1 stays.
  STAGE 3  n ≥ 500 AND logistic won → isotonic calibration on top.

Unit of analysis = ONE alert row (ledger rows are already deduped per
(asof_date, key)); ticker-day clustering is handled by the same
cluster-bootstrap discipline as flow_outcomes.

The p-gate constant lives here and is shared: the SERVER computes p and
attaches it to rows/alerts — the frontend never recomputes, which makes
rule parity structural instead of mirrored (see flow_alerts parity note).

Frozen feature vector (order matters; never reorder — models are pinned):
    0: log10(vol_oi + 1)
    1: log10(max(premium, 1) / 1e3)      # thousands of dollars
    2: dte (capped at 90)
    3: |delta| (0.5 when None)
    4: sigma (capped at 10, 0 when None)
    5: bias_bullish (1/0; calls + BULLISH bias → 1)

No sklearn dependency at stage 0/1 (pure python); stage 2+ uses sklearn
LogisticRegression if available, else stays at stage 1 (honest degradation).
"""

from __future__ import annotations

import logging
import math
import random
from datetime import UTC, datetime
from typing import Any

from services.flow_outcomes import _wilson_ci

logger = logging.getLogger(__name__)

# ── stage gates (the sample-size honesty contract) ──────────────────────────
STAGE1_MIN = 60      # measured alerts before ANY number is shown
STAGE1_MIN_PER_DECILE = 6
STAGE2_MIN = 300
STAGE3_MIN = 500
# Promotion gate: stage-2 logistic must beat stage-1 decile baseline by at
# least this Brier margin out-of-time, else stage 1 stays (parsimony rule).
STAGE2_BRIER_MARGIN = 0.02

# Feature freeze v2 (2026-09-02): mins_since_open added as a frozen covariate
# — retro-trained models see EOD volumes while live alerts fire intraday, so
# time-of-day is the known confounder (plan §2). Sentinel −1.0 = fired outside
# RTH / unknown, kept distinct from any real minute count.
FEATURE_NAMES = ["log_vol_oi", "log_premium_k", "dte", "abs_delta", "sigma",
                 "mins_since_open", "bias_bullish"]


# ── features ────────────────────────────────────────────────────────────────

def feature_vector(a: dict[str, Any]) -> list[float] | None:
    """Frozen feature vector for one alert row (ledger row or live row).

    Returns None when the row lacks the minimum viable fields (malformed) —
    the caller skips it rather than imputing garbage.
    """
    try:
        vol_oi = a.get("vol_oi")
        premium = a.get("premium")
        if vol_oi is None and a.get("vol") and a.get("oi"):
            vol_oi = float(a["vol"]) / max(float(a["oi"]), 1.0)
        if vol_oi is None or premium is None:
            return None
        dte = a.get("dte")
        dte = 90 if dte is None else min(max(float(dte), 0.0), 90.0)
        delta = a.get("delta")
        abs_delta = 0.5 if delta is None else min(abs(float(delta)), 1.0)
        sigma = a.get("sigma")
        sigma_v = 0.0 if sigma is None else min(abs(float(sigma)), 10.0)
        mso = a.get("mins_since_open")
        mso_v = -1.0 if mso is None else min(max(float(mso), -1.0), 390.0)
        side = str(a.get("side") or a.get("type") or "").lower()
        bias = str(a.get("bias") or "").upper()
        bull = 1.0 if (side.startswith("c") or bias == "BULLISH") else 0.0
        return [
            math.log10(max(float(vol_oi), 0.0) + 1.0),
            math.log10(max(float(premium), 1.0) / 1e3),
            dte,
            abs_delta,
            sigma_v,
            mso_v,
            bull,
        ]
    except (TypeError, ValueError):
        return None


# ── stage 1: decile table ───────────────────────────────────────────────────

def _decile_of(score: float | None) -> int | None:
    if score is None:
        return None
    return max(0, min(9, int(float(score) // 10)))


def fit_decile_model(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """STAGE 1 — empirical hit rate per score decile with Wilson CIs.

    rows: labeled alert rows (from flow_outcomes.label_alerts) with
          hit (bool), score, and features available.
    """
    buckets: dict[int, list[int]] = {d: [] for d in range(10)}
    for r in rows:
        if r.get("hit") is None or r.get("censored"):
            continue
        d = _decile_of(r.get("score"))
        if d is None:
            continue
        buckets[d].append(1 if r["hit"] else 0)
    table = {}
    usable = 0
    for d, hits in buckets.items():
        n = len(hits)
        if n >= STAGE1_MIN_PER_DECILE:
            h = sum(hits)
            ci = _wilson_ci(h, n)
            table[str(d)] = {"n": n, "hits": h, "p": round(h / n, 4),
                             "ci": [round(ci[0], 4), round(ci[1], 4)]}
            usable += n
        else:
            table[str(d)] = {"n": n, "hits": sum(hits), "p": None, "ci": None}
    if usable < STAGE1_MIN:
        return None
    return {"kind": "decile", "table": table, "n": usable,
            "trained_at": datetime.now(UTC).isoformat()}


def decile_predict(model: dict[str, Any], score: float | None) -> float | None:
    if model is None or score is None:
        return None
    cell = (model.get("table") or {}).get(str(_decile_of(score)))
    return cell.get("p") if cell else None


# ── stage 2/3: logistic (+isotonic) ──────────────────────────────────────────

def _brier(ps: list[float], ys: list[int]) -> float:
    if not ps:
        return 1.0
    return sum((p - y) ** 2 for p, y in zip(ps, ys, strict=False)) / len(ps)


def fit_logistic_model(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """STAGE 2 — L2 logistic on frozen features with walk-forward promotion.

    Train = rows with asof_date ≤ cutoff; test = rows after it (30d split).
    Promoted only if test Brier beats the stage-1 decile baseline by
    STAGE2_BRIER_MARGIN. Sklearn unavailable → returns None (stay stage 1).
    """
    try:
        from sklearn.linear_model import LogisticRegression
    except Exception:
        logger.info("flow_calibration: sklearn unavailable — staying at stage 1")
        return None

    measured = [r for r in rows if r.get("hit") is not None and not r.get("censored")
                and not r.get("earnings_ambiguous")]
    if len(measured) < STAGE2_MIN:
        return None
    X, y, dates, scores = [], [], [], []
    for r in measured:
        fv = feature_vector(r)
        if fv is None:
            continue
        X.append(fv)
        y.append(1 if r["hit"] else 0)
        dates.append(str(r.get("asof_date") or ""))
        scores.append(r.get("score"))
    if len(y) < STAGE2_MIN:
        return None

    cutoff = sorted(set(dates))[-30] if len(set(dates)) > 30 else sorted(set(dates))[0]
    train_idx = [i for i, d in enumerate(dates) if d <= cutoff]
    test_idx = [i for i, d in enumerate(dates) if d > cutoff]
    if len(train_idx) < STAGE2_MIN // 2 or len(test_idx) < 30:
        return None

    # Walk-forward guard: train must strictly precede test (out-of-time only).
    if max(dates[i] for i in train_idx) >= min(dates[i] for i in test_idx):
        return None

    decile = fit_decile_model([measured[i] for i in train_idx])
    base_ps = [decile_predict(decile, scores[i]) or 0.5 for i in test_idx]
    base_brier = _brier(base_ps, [y[i] for i in test_idx])

    lam = 1.0 / max(len(train_idx), 1)
    clf = LogisticRegression(C=1.0 / (lam * len(train_idx)), max_iter=1000)
    try:
        clf.fit([X[i] for i in train_idx], [y[i] for i in train_idx])
        test_ps = clf.predict_proba([X[i] for i in test_idx])[:, 1].tolist()
    except Exception as e:
        logger.warning("flow_calibration: logistic fit failed: %s", e)
        return None
    lr_brier = _brier(test_ps, [y[i] for i in test_idx])

    if lr_brier > base_brier - STAGE2_BRIER_MARGIN:
        logger.info("flow_calibration: logistic did not beat decile baseline "
                    "(%.4f vs %.4f) — staying at stage 1", lr_brier, base_brier)
        return None

    # Refit on ALL measured rows for production.
    clf.fit(X, y)
    model: dict[str, Any] = {
        "kind": "logistic",
        "coef": [round(float(c), 6) for c in clf.coef_[0]],
        "intercept": round(float(clf.intercept_[0]), 6),
        "features": FEATURE_NAMES,
        "n": len(y),
        "train_brier": round(lr_brier, 4),
        "base_brier": round(base_brier, 4),
        "isotonic": False,
        "trained_at": datetime.now(UTC).isoformat(),
    }
    # STAGE 3 — isotonic on top when the sample supports it.
    if len(y) >= STAGE3_MIN:
        try:
            from sklearn.isotonic import IsotonicRegression
            full_ps = clf.predict_proba(X)[:, 1]
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(full_ps, y)
            model["isotonic"] = True
            model["iso_thresholds"] = iso.X_thresholds_.tolist()
            model["iso_values"] = iso.y_thresholds_.tolist()
        except Exception as e:
            logger.info("flow_calibration: isotonic unavailable (%s) — logistic uncalibrated-curve", e)
    return model


# ── public API ───────────────────────────────────────────────────────────────

def fit_calibration(labeled_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit the best honest model for the supplied labeled ledger rows.

    Returns a status blob: {stage, model, n, method_note}. stage follows the
    ladder; model is None at stage 0.
    """
    measured = [r for r in (labeled_rows or []) if r.get("hit") is not None
                and not r.get("censored") and not r.get("earnings_ambiguous")]
    n = len(measured)
    if n < STAGE1_MIN:
        return {"stage": 0, "model": None, "n": n,
                "method_note": f"uncalibrated: n={n} < {STAGE1_MIN} — no honest probability yet"}
    logistic = fit_logistic_model(measured)
    if logistic is not None:
        stage = 3 if logistic.get("isotonic") else 2
        return {"stage": stage, "model": logistic, "n": n,
                "method_note": "logistic" + ("+isotonic" if logistic.get("isotonic") else "")}
    decile = fit_decile_model(measured)
    if decile is not None:
        return {"stage": 1, "model": decile, "n": n,
                "method_note": "empirical decile hit rates (Wilson CI)"}
    return {"stage": 0, "model": None, "n": n,
            "method_note": f"uncalibrated: insufficient per-decile coverage at n={n}"}


def predict_p_move(calibration: dict[str, Any] | None, row: dict[str, Any]) -> dict[str, Any]:
    """Attach p_move/p_method/p_n to a row. NEVER returns a number below stage 1.

    Server-side only: the frontend consumes the attached fields verbatim —
    structural parity, no mirrored math.
    """
    stage = (calibration or {}).get("stage", 0)
    model = (calibration or {}).get("model")
    n = (calibration or {}).get("n", 0)
    if stage < 1 or model is None:
        return {"p_move": None, "p_method": "uncalibrated", "p_n": n}
    if model.get("kind") == "decile":
        p = decile_predict(model, row.get("score"))
        if p is None:  # decile under-covered → honest None, not a fallback guess
            return {"p_move": None, "p_method": "uncalibrated_decile", "p_n": n}
        return {"p_move": p, "p_method": "decile", "p_n": n}
    if model.get("kind") == "logistic":
        fv = feature_vector(row)
        if fv is None:
            return {"p_move": None, "p_method": "missing_features", "p_n": n}
        z = sum(c * x for c, x in zip(model["coef"], fv, strict=False)) + model["intercept"]
        p = 1.0 / (1.0 + math.exp(-z))
        if model.get("isotonic"):
            p = _iso_apply(model, p)
        return {"p_move": round(p, 4), "p_method": "logistic+isotonic" if model.get("isotonic") else "logistic", "p_n": n}
    return {"p_move": None, "p_method": "uncalibrated", "p_n": n}


def _iso_apply(model: dict[str, Any], p: float) -> float:
    """Piecewise-linear isotonic mapping (thresholds/values from fit)."""
    xs = model.get("iso_thresholds") or []
    ys = model.get("iso_values") or []
    if not xs or not ys:
        return p
    if p <= xs[0]:
        return float(ys[0])
    if p >= xs[-1]:
        return float(ys[-1])
    for i in range(1, len(xs)):
        if p <= xs[i]:
            x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
            if x1 == x0:
                return float(y1)
            return float(y0 + (y1 - y0) * (p - x0) / (x1 - x0))
    return float(ys[-1])


def calibration_status_blob(calibration: dict[str, Any]) -> dict[str, Any]:
    """What /outcomes and the UI surface about the calibration itself."""
    return {
        "stage": calibration.get("stage", 0),
        "n": calibration.get("n", 0),
        "method_note": calibration.get("method_note", ""),
        "model_kind": (calibration.get("model") or {}).get("kind"),
        "isotonic": bool((calibration.get("model") or {}).get("isotonic")),
        "brier": {
            "logistic": (calibration.get("model") or {}).get("train_brier"),
            "decile_baseline": (calibration.get("model") or {}).get("base_brier"),
        },
        "coef": (calibration.get("model") or {}).get("coef"),
        "features": (calibration.get("model") or {}).get("features", FEATURE_NAMES),
        "trained_at": (calibration.get("model") or {}).get("trained_at"),
    }


def _demo() -> None:  # pragma: no cover - manual smoke
    rng = random.Random(1)
    rows = []
    for i in range(80):
        score = min(99.0, 40 + i * 0.7)
        hit = rng.random() < (score / 100) * 0.8
        rows.append({"score": score, "hit": hit, "censored": False,
                     "asof_date": f"2099-01-{(i % 28) + 1:02d}",
                     "vol_oi": 3.0, "premium": 1e6, "dte": 5, "delta": 0.4, "sigma": 4.0})
    print(fit_calibration(rows))


if __name__ == "__main__":  # pragma: no cover
    _demo()
