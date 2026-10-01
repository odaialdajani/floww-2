"""Real producer -> recorder -> recorded projection, no lifespan/providers."""
import importlib.util
from pathlib import Path

from tests.offline_network import deny_external_network  # noqa: F401


def test_recorded_projection_binds_exact_request_and_source_metadata():
    path = Path(__file__).resolve().parents[3] / "scripts/r11_fixture.py"
    spec = importlib.util.spec_from_file_location("r13_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packet = module.generate()
    raw, rep = packet["display"], packet["replay"]
    assert rep["context"]["display"]["map_query"] == raw["map_query"]
    assert rep["context"]["display"]["event_time"] == raw["event_time"]
    from services.solstice_replay import recorded_display
    projection = recorded_display(rep, raw["ticker"], raw["snapshotId"])
    assert projection["grid"]["grid"] == raw["grid"]["grid"]
    assert projection["metrics"]["grids"]["delta"]["grid"] == raw["metrics"]["grids"]["delta"]["grid"]
    assert projection["map_query"] == raw["map_query"]
    assert projection["data_source"] == raw["data_source"]
    assert recorded_display(rep, "QQQ", raw["snapshotId"]) is None
    assert recorded_display(rep, "SPY", "other") is None
    rep["context"].pop("display")
    assert recorded_display(rep, "SPY", raw["snapshotId"]) is None
