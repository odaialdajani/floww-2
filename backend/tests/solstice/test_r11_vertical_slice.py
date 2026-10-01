"""Producer → real route → recorded projection → exact review → existing evidence."""
import importlib.util
from pathlib import Path


def test_vertical_slice_restores_real_builder_context_and_saves_review():
    path = Path(__file__).resolve().parents[3] / "scripts/r11_fixture.py"
    spec = importlib.util.spec_from_file_location("r11_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packet = module.generate()
    display = packet["display"]
    assert packet["replay"]["context"]["scout"] == display["scout"]
    assert packet["replay"]["context"]["session"] == display["session"]
    assert packet["replay"]["snapshot"]["spot"] == display["spot"]
    assert packet["contract"]["status"] == "ok"
    assert packet["contract"]["matched_identity"]["expiry"] == display["grid"]["expiries"][1]
    assert packet["review"]["durability"] == "durable"
    assert any(f["metric"] == "Selected display cell" for f in packet["lodestar_facts"])
