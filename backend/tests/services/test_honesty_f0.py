"""P0 honesty regressions (Agent 2, astra/f0-honesty-backend). One test per fix-queue ID."""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services import gex_paper_accurate as gpa


def test_f1_no_fabricated_ssrn_citation():
    doc = gpa.charm_hedging_pressure.__doc__ or ""
    assert "5054370" not in doc
    assert "SSRN" not in doc


def test_f1_args_match_signature():
    sig = set(inspect.signature(gpa.charm_hedging_pressure).parameters)
    doc = gpa.charm_hedging_pressure.__doc__ or ""
    for name in ("gamma", "net_gamma"):
        assert f"{name}:" not in doc, f"documented arg {name} absent from signature"
    for name in sig:
        assert name in doc
    assert sig == {"delta", "theta", "dte_days"}


def test_f1_charm_held_unverified():
    out = gpa.charm_hedging_pressure(delta=0.5, theta=0.05, dte_days=2.0)
    assert out["signal"] == "CHARM_BUYING_PRESSURE"
    text = out.get("interpretation", "")
    assert "Per Ni-Pearson 2021" not in text
    lowered = text.lower()
    assert any(m in lowered for m in ("proxy", "heuristic", "unverified")), text


def test_f3_no_numeric_crash_probability():
    out = gpa.flash_crash_risk(gamma_imbalance_pct=-3.0, flip_distance_pct=0.5)
    assert "crash_probability_estimate" not in out
    assert out.get("stability") in ("fragile", "stable")
    assert "risk_level" in out


def test_f7_no_phantom_charm_comment():
    src = Path(__file__).resolve().parents[2] / "services" / "morning_briefing.py"
    text = src.read_text()
    assert "Ni-Pearson 2021 Charm" not in text


def test_f4_oi_pcr_labeled_proxy():
    out = gpa.put_call_ratio_signal(call_oi=80.0, put_oi=20.0)
    text = (out.get("interpretation", "") + " " + (gpa.put_call_ratio_signal.__doc__ or "")).lower()
    assert "oi-based" in text or "oi based" in text or "oi proxy" in text
    assert "pan-poteshman 2006" not in out.get("interpretation", "").lower()
