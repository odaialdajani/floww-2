"""Actual source -> record -> admitted ledger -> existing answer projection."""
import importlib.util
from pathlib import Path

import pytest

from tests.offline_network import deny_external_network  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def packet():
    return load("r14_fixture").generate()


@pytest.mark.parametrize("family",["contract","window","vex","charm"])
def test_recorded_family_reaches_deterministic_answer_without_provider(packet,family):
    selector = packet["admissions"][family]["screen"]
    turn = load("r14_answer").answer(packet,{"question":"Why this wall?","screen":selector})
    assert turn["status"] == "completed" and turn["saved"] is False
    assert turn["answer"]["mode"] == "deterministic"
    assert "Not requested" in turn["answer"]["model_status"]
    facts = {f["metric"]:f for f in turn["answer"]["facts"]}
    assert facts and turn["answer"]["context"] == selector
    if family == "contract":
        assert facts["Exact contract strike"]["value"] == "100.0"
        assert facts["Exact contract multiplier"]["value"] == "100.0"  # resolver preserves exact Decimal text
    else:
        assert facts["Selected display cell"]["value"] == next(f["value"] for f in packet["admissions"][family]["facts"] if f["metric"] == "Selected display cell")
        assert facts["Displayed signed profile"]["value"] == next(f["value"] for f in packet["admissions"][family]["facts"] if f["metric"] == "Displayed signed profile")


@pytest.mark.parametrize("family",["contract","window","vex","charm"])
def test_changed_owning_record_returns_explicit_gap_never_live_replacement(packet,family):
    selector = {**packet["admissions"][family]["screen"],"snapshotId":"not-recorded"}
    turn = load("r14_answer").answer(packet,{"question":"Why this wall?","screen":selector})
    assert turn["answer"]["facts"] == [] and turn["answer"]["gaps"]
