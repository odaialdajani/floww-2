"""OFFLINE fixtures in the real recorder schema; no real approval or market proof.

Issuer keys, policy, owner, lifecycle, costs and source rows here are explicitly
synthetic. The actual recorder writes only a temporary DuckDB; production
adapter reads it and signed temporary records without any write capability.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

from scripts.paper_synthetic_fixture import synthetic_policy_body
from services.agent.paper import execution, risk
from services.agent.paper.policy import binding_of, create_policy
from services.agent.paper.public_source_adapter import (
    AuthenticatedEvidenceDirectory,
    PublicPaperSourceAdapter,
    SourceRefusal,
    StoredPublicSnapshots,
    inspect_saved_observations,
    inspect_stored_row,
    market_session,
)
from services.agent.paper.repository import PaperConflict, canonical, digest
from services.heatmap_history import record_snapshot

NOW = datetime(2026, 11, 6, 15, tzinfo=UTC)
CID = "SPY261113C00600000"
OWNER, ACCOUNT, EPOCH = (f"00000000-0000-4000-8000-{i:012d}" for i in (1, 2, 3))
KEYS = {"confirmation": b"synthetic-owner-key-" * 3, "source_evidence": b"synthetic-source-key-" * 3}
KEYS["policy_acceptance"] = KEYS["confirmation"]


class FakeReadOnlyAccount:
    def __init__(self, account):
        self.account = account

    async def read(self, owner, account):
        return copy.deepcopy(self.account) if (owner, account) == (OWNER, ACCOUNT) else None


def sign(directory, kind, body):
    unsigned = dict(kind=kind, body=body)
    record = dict(unsigned, signature=hmac.new(KEYS[kind], canonical(unsigned).encode(), hashlib.sha256).hexdigest())
    reference = digest(record)
    (directory / (reference + ".json")).write_text(canonical(record))
    return reference


def save_snapshot(path, *, sid="synthetic-snapshot", changes=None):
    contract = dict(osi=CID, expiry="2026-11-13", type="call", strike=600, strike_exact="600", multiplier=100,
                    multiplier_source="synthetic-provider-spec", adjusted=False,
                    bid=2, ask=2.1, bid_size=2, ask_size=3,
                    bid_timestamp=(NOW - timedelta(seconds=2)).isoformat(),
                    ask_timestamp=(NOW - timedelta(seconds=1)).isoformat(), received_at=NOW.isoformat())
    contract.update(changes or {})
    conn = duckdb.connect(str(path))
    payload = dict(ticker="SPY", data_source="public_api", contracts=[contract],
                   asof=NOW.isoformat(), source_received_at=NOW.isoformat(), expiries_used=["2026-11-13"])
    assert record_snapshot(conn, payload, snapshot_id=sid) == sid
    conn.close()


@pytest.fixture
async def setup(tmp_path):
    path, directory = tmp_path / "synthetic.duckdb", tmp_path / "synthetic-issuer"
    directory.mkdir()
    save_snapshot(path)
    current = dict(owner=OWNER, account_id=ACCOUNT, epoch=EPOCH, venue="internal", version=4,
                   state=execution.new_book("10000", currency="USD"))
    binding = binding_of(current)
    policy = create_policy(binding, synthetic_policy_body(), policy_id="00000000-0000-4000-8000-000000000004",
                           policy_version=1, effective_at=NOW, accepted_at=NOW, accepted_by=OWNER,
                           acceptance_evidence=["SYNTHETIC-OWNER-CHOICE"], now=NOW, verify_acceptance=lambda _: True)
    current["state"]["risk_policy"] = policy
    terms = dict(contract_id=CID, product_kind="option", currency="USD", premium_factor="100", side="buy",
                 quantity=1, limit="2.10", fee_per_unit="0.65", slippage_enabled=True, slippage_method="price",
                 price_increment="0.05", max_quote_age_seconds=60, max_spread="0.20", latency_ms=0,
                 order_expires_at=(NOW + timedelta(minutes=5)).isoformat(), proposal_digest="a" * 64)
    metadata = dict(contract_id=CID, product_kind="option", currency="USD", premium_factor="100",
                    source_id="SYNTHETIC-CONTRACT-SPEC", verified_at=NOW.isoformat(), underlying="SPY", strike="600",
                    right="call", adjusted=False, exercise_style="american", settlement_style="physical",
                    deliverable=dict(kind="shares", quantity="100", currency="USD", symbol="SPY"),
                    last_trade_at="2026-11-13T21:00:00+00:00", expiry_at="2026-11-13T21:00:00+00:00",
                    exercise_cutoff_at="2026-11-13T22:00:00+00:00", settlement_at="2026-11-16T15:00:00+00:00",
                    instrument_class="standard_equity_option", size_unit="contracts", price_unit="USD_per_share",
                    corporate_action_status="clear", lifecycle_status="active")
    contract_hash, lifecycle_hash = risk.metadata_digests(metadata)
    costs = dict(exit_cost_per_unit="5.65", lifecycle_cost_per_unit="1", maximum_loss="217.30",
                 maximum_loss_basis="prepaid_long_zero_recovery_plus_costs", cost_basis="linear_per_unit",
                 contract_digest=contract_hash, lifecycle_digest=lifecycle_hash)
    source = StoredPublicSnapshots(path)
    selections = [dict(snapshot_id="synthetic-snapshot", contract_id=CID)]
    records = await source.read(selections)
    intent = dict(kind="stage", order_id=EPOCH + ":1", structure_id=EPOCH + ":1")
    bundle = dict(intent=intent, binding=binding, policy_digest=policy["digest"], economics_digest=digest(risk.economics(terms)),
                  verified_at=NOW.isoformat(), valid_until=(NOW + timedelta(minutes=5)).isoformat(),
                  metadata=[metadata], costs=costs, selections=selections,
                  source_refs=["public-stored:" + digest(row) for row in records],
                  session_open=dict(session_id="XNYS:2026-11-06", source_id="SYNTHETIC-OPEN-VALUATION",
                                    observed_at="2026-11-06T14:30:00+00:00", equity="10000"))
    acceptance = dict(binding=binding, policy=policy, accepted_by=OWNER, authentication="authenticated_owner_session")
    confirmation = dict(intent=intent, binding=binding, policy_digest=policy["digest"], economics=risk.economics(terms),
                        accepted_by=OWNER, authentication="authenticated_owner_session", account_version=4,
                        accepted_at=NOW.isoformat(), valid_until=(NOW + timedelta(minutes=5)).isoformat(),
                        proposal_version=1, policy_acceptance_ref=sign(directory, "policy_acceptance", acceptance))
    repo = FakeReadOnlyAccount(current)
    authority = AuthenticatedEvidenceDirectory(directory, confirmation_key=KEYS["confirmation"],
                                               evidence_key=KEYS["source_evidence"])
    clock = [NOW]
    adapter = PublicPaperSourceAdapter(repo, snapshots=source, evidence=authority, clock=lambda: clock[0])
    context = SimpleNamespace(path=path, directory=directory, current=current, binding=binding, terms=terms,
                              source=source, records=records, bundle=bundle, confirmation=confirmation, repo=repo,
                              adapter=adapter, clock=clock, authority=authority)
    context.resign = lambda: resign(context)
    context.ref = context.resign()
    return context


def resign(c):
    c.confirmation["evidence_ref"] = sign(c.directory, "source_evidence", c.bundle)
    c.ref = dict(confirmation_id=sign(c.directory, "confirmation", c.confirmation))
    return c.ref


async def capture(c, **changes):
    kwargs = dict(binding=c.binding, expected_version=4, action="entry", frozen_parameters=c.terms,
                  quote=None, confirmation_ref=c.ref)
    kwargs.update(changes)
    return await c.adapter.capture_verified_inputs(**kwargs)


async def verify(c, captured, **changes):
    kwargs = dict(owner=OWNER, current_account=c.current, frozen_parameters=c.terms,
                  confirmation_record=captured.confirmation_record, immutable_source_refs=captured.immutable_source_refs)
    kwargs.update(changes)
    return await c.adapter.verify_admission(**kwargs)


async def test_actual_recorder_shape_and_restart_capture(setup):
    c = setup
    before = c.path.read_bytes()
    result = await capture(c)
    assert result.executable_quote["bid_observed_at"] != result.executable_quote["ask_observed_at"]
    assert result.executable_quote["observed_at"] == result.executable_quote["bid_observed_at"]
    assert result.opening_trade_evidence["costs"]["maximum_loss"] == "217.30"
    assert await verify(c, result) is True
    c.adapter = PublicPaperSourceAdapter(c.repo, snapshots=StoredPublicSnapshots(c.path), evidence=c.authority,
                                         clock=lambda: NOW)
    assert await capture(c) == result
    assert c.path.read_bytes() == before
    assert c.current["state"]["cash"] == "10000" and not c.current["state"]["orders"]


@pytest.mark.parametrize("field,value", [("quantity", 2), ("contract_id", "SPY261113P00600000"),
                                          ("premium_factor", "1"), ("fee_per_unit", "0")])
async def test_forged_request_economics(setup, field, value):
    with pytest.raises(SourceRefusal, match="confirmation_economics"):
        await capture(setup, frozen_parameters=dict(setup.terms, **{field: value}))


async def test_request_cannot_supply_approval_or_quote(setup):
    c = setup
    with pytest.raises(SourceRefusal, match="confirmation_selection_only"):
        await capture(c, confirmation_ref=dict(c.ref, approved=True))
    with pytest.raises(SourceRefusal, match="request_quote_not_source_truth"):
        await capture(c, quote={"bid_size": 999, "equity": "1000000"})


@pytest.mark.parametrize("field,value,reason", [
    ("accepted_by", ACCOUNT, "owner"), ("policy_digest", "f" * 64, "policy"),
    ("account_version", 3, "account_version"), ("authentication", "request_boolean", "owner"),
    ("valid_until", NOW.isoformat(), "expired"),
])
async def test_signed_but_wrong_confirmation_refused(setup, field, value, reason):
    c = setup
    c.confirmation[field] = value
    c.resign()
    with pytest.raises(SourceRefusal, match=reason):
        await capture(c)


async def test_invalid_signature_and_changed_persisted_confirmation(setup):
    c = setup
    path = c.directory / (c.ref["confirmation_id"] + ".json")
    record = json.loads(path.read_text())
    record["signature"] = "0" * 64
    ref = digest(record)
    (c.directory / (ref + ".json")).write_text(canonical(record))
    with pytest.raises(SourceRefusal, match="authentication_failed"):
        await capture(c, confirmation_ref=dict(confirmation_id=ref))
    result = await capture(c)
    path.write_text(canonical(record))
    with pytest.raises(SourceRefusal, match="immutable_evidence_changed"):
        await verify(c, result)


@pytest.mark.parametrize("column,value,reason", [
    ("bid_ts", None, "bid_clock_missing"), ("received_at", None, "quote_receipt_missing"),
    ("bid_size", None, "bid_size"), ("bid_size", 0, "bid_size"), ("ask_size", None, "ask_size"),
    ("ask_size", 0, "ask_size"), ("bid_ts", "2026-11-06T14:58:00+00:00", "bid_stale"),
    ("ask_ts", "2026-11-06T15:00:01+00:00", "ask_clock_order"),
    ("received_at", "2026-11-06T14:59:57+00:00", "bid_clock_order"),
    ("multiplier_source", "DEFAULT_STANDARD", "standard_multiplier"),
    ("strike_exact", "601", "strike_or_right"), ("provider", "fallback", "public_source"),
])
async def test_signed_row_cannot_override_source_defects(setup, column, value, reason):
    c = setup
    conn = duckdb.connect(str(c.path))
    conn.execute(f"UPDATE contract_observations_v2 SET {column}=?", [value])
    conn.close()
    rows = await c.source.read(c.bundle["selections"])
    c.bundle["source_refs"] = ["public-stored:" + digest(row) for row in rows]
    c.resign()
    with pytest.raises((SourceRefusal, ValueError), match=reason):
        await capture(c)


@pytest.mark.parametrize("field,value,reason", [
    ("size_unit", None, "units"), ("corporate_action_status", "unknown", "corporate_action"),
    ("lifecycle_status", "unknown", "lifecycle"), ("adjusted", True, "lifecycle"),
    ("premium_factor", "150", "multiplier"), ("instrument_class", "index_option", "unsupported"),
    ("last_trade_at", NOW.isoformat(), "lifecycle event"),
])
async def test_signed_unknown_metadata_refuses(setup, field, value, reason):
    c = setup
    c.bundle["metadata"][0][field] = value
    c.resign()
    with pytest.raises((SourceRefusal, ValueError), match=reason):
        await capture(c)


async def test_missing_costs_open_equity_and_held_marks(setup):
    c = setup
    c.bundle["costs"] = None
    c.resign()
    with pytest.raises(SourceRefusal, match="costs"):
        await capture(c)
    c.bundle["session_open"] = None
    c.resign()
    with pytest.raises(SourceRefusal, match="opening_equity"):
        await capture(c)
    c.current["state"]["positions"]["held"] = dict(contract_id="OTHER")
    with pytest.raises(SourceRefusal, match="full_book_source_coverage"):
        await capture(c)


async def test_capture_detached_and_persisted_source_change_detected(setup):
    c = setup
    result = await capture(c)
    frozen = copy.deepcopy(result)
    c.bundle["metadata"][0]["strike"] = "999"
    assert result == frozen
    conn = duckdb.connect(str(c.path))
    conn.execute("UPDATE contract_observations_v2 SET bid_size=99")
    conn.close()
    with pytest.raises(SourceRefusal, match="immutable_source_changed"):
        await verify(c, result)
    assert result == frozen


async def test_owner_epoch_source_refs_cannot_be_forged(setup):
    c = setup
    result = await capture(c)
    with pytest.raises(SourceRefusal, match="owner"):
        await verify(c, result, owner=ACCOUNT)
    with pytest.raises(SourceRefusal, match="captured_evidence"):
        await verify(c, result, immutable_source_refs=["forged"])
    c.current["epoch"] = "00000000-0000-4000-8000-000000000005"
    with pytest.raises(PaperConflict, match="recovery"):
        await verify(c, result)


async def test_receipt_snapshot_and_opposite_side_cannot_refresh_liquidity(setup):
    c = setup
    first = (await capture(c)).executable_quote
    save_snapshot(c.path, sid="synthetic-snapshot-2", changes={"bid_timestamp": NOW.isoformat()})
    c.bundle["selections"][0]["snapshot_id"] = "synthetic-snapshot-2"
    rows = await c.source.read(c.bundle["selections"])
    c.bundle["source_refs"] = ["public-stored:" + digest(row) for row in rows]
    c.resign()
    second = (await capture(c)).executable_quote
    assert second["source_id"] == first["source_id"]
    # The unchanged ask event cannot refill: changed quote content under its
    # original key is conservatively refused by existing execution accounting.
    book = execution.new_book("1000", currency="USD")
    staged, event = execution.stage_order(book, **dict(c.terms, slippage_enabled=False, epoch=EPOCH, now=NOW, committed_version=1))
    filled, _, _ = execution.fill_order(staged, event["order_id"], first, now=NOW, committed_version=2)
    with pytest.raises(ValueError, match="changed content"):
        execution.fill_order(filled, event["order_id"], second, now=NOW, committed_version=3)


@pytest.mark.parametrize("stamp,reason", [
    ("2026-11-07T15:00:00+00:00", "market_closed"),
    ("2026-11-06T21:00:00+00:00", "cutoff"),
    ("2026-11-27T18:00:00+00:00", "cutoff"),
])
def test_calendar_weekend_close_and_half_day(stamp, reason):
    with pytest.raises(SourceRefusal, match=reason):
        market_session(stamp)


async def test_inspection_keeps_missing_and_zero_and_never_admits(setup):
    row = copy.deepcopy(setup.records[0])
    row["contract"]["bid_size"] = None
    row["contract"]["ask_size"] = 0
    probe = inspect_stored_row(row, now=NOW, max_age_seconds=60)
    assert not probe["admitted"]
    assert "bid_size_missing" in probe["gaps"] and "ask_size_nonpositive_or_invalid" in probe["gaps"]
    assert "confirmation_unavailable" in probe["gaps"] and "size_unit_unverified" in probe["gaps"]


async def test_reader_refuses_duplicate_overflow_missing_and_symlink_evidence(setup):
    c = setup
    with pytest.raises(SourceRefusal, match="source_rows_exceeded"):
        await c.source.read(c.bundle["selections"] * 65)
    with pytest.raises(SourceRefusal, match="duplicate_source"):
        await c.source.read(c.bundle["selections"] * 2)
    with pytest.raises(SourceRefusal, match="unavailable_or_ambiguous"):
        await c.source.read([dict(snapshot_id="missing", contract_id=CID)])
    ref = c.ref["confirmation_id"]
    path = c.directory / (ref + ".json")
    actual = c.directory / "original.json"
    path.rename(actual)
    path.symlink_to(actual)
    with pytest.raises(SourceRefusal, match="persisted_evidence_unavailable"):
        await capture(c)


async def test_role_separation_and_confirmation_replay(setup):
    c = setup
    result = await capture(c)
    c.current["version"] = 6
    with pytest.raises(SourceRefusal, match="account_version"):
        await verify(c, result)
    c.current["version"] = 4
    c.adapter.evidence = AuthenticatedEvidenceDirectory(c.directory, confirmation_key=KEYS["source_evidence"],
                                                         evidence_key=KEYS["confirmation"])
    with pytest.raises(SourceRefusal, match="authentication_failed"):
        await capture(c)


async def test_policy_approval_must_match_exact_persisted_policy(setup):
    c = setup
    c.confirmation["policy_acceptance_ref"] = sign(c.directory, "policy_acceptance", dict(accepted_by=OWNER))
    c.resign()
    with pytest.raises(SourceRefusal, match="policy_acceptance_mismatch"):
        await capture(c)


async def test_same_side_event_shares_liquidity_across_orders(setup):
    c = setup
    quote = (await capture(c)).executable_quote
    parameters = dict(c.terms, quantity=2, slippage_enabled=False, epoch=EPOCH, now=NOW)
    book = execution.new_book("2000", currency="USD")
    book, first = execution.stage_order(book, **parameters, committed_version=1)
    book, second = execution.stage_order(book, **parameters, committed_version=2)
    book, fill, _ = execution.fill_order(book, first["order_id"], quote, now=NOW, committed_version=3)
    assert fill["quantity"] == 2
    book, fill, _ = execution.fill_order(book, second["order_id"], quote, now=NOW, committed_version=4)
    assert fill["quantity"] == 1
    assert book["quotes"][digest([quote["contract_id"], quote["source_id"]])]["used_ask"] == 3


async def test_reader_deadline_is_finite(setup, monkeypatch):
    import subprocess

    import services.agent.paper.public_source_adapter as module
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] <= 5
        raise subprocess.TimeoutExpired("synthetic-read-only-child", kwargs["timeout"])
    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(SourceRefusal, match="stored_snapshot_deadline"):
        await setup.source.read(setup.bundle["selections"])


def test_real_saved_endpoint_shape_remains_data_only():
    # Field shape matches the actual bounded saved read. Values are fictional.
    key = "SPY|call|600|2026-11-13"
    payload = dict(source="public-scan-observations",
                   rows=[["SPY", CID, "call", 600.0, "2026-11-13", 1, 2, 0.2, 0.5, 600.0]],
                   quote_truth={key: dict(bid=2.0, ask=2.1, bid_source_time=NOW.timestamp()-2,
                                          ask_source_time=NOW.timestamp()-1)},
                   row_observations={key: dict(received_at=NOW.timestamp(), source="public_api")})
    report = inspect_saved_observations(payload, now=NOW)
    observation = report["observations"][0]
    assert not report["admitted"] and not observation["admitted"]
    assert "bid_size_missing" in observation["gaps"]
    assert "immutable_recorder_snapshot_unavailable" in observation["gaps"]
    assert observation["quote_source"]["bid_event_at"] != observation["quote_source"]["ask_event_at"]
    assert payload["rows"][0][3] == 600.0


async def test_captured_inputs_feed_existing_risk_and_cannot_override_limits(setup):
    c = setup
    captured = await capture(c)
    result = risk.prepare_stage(c.current, c.terms, expected_version=4,
                                trade_evidence=captured.opening_trade_evidence, frame=captured.frame, now=NOW)
    assert result["status"] == "pass", result["reason"]
    assert result["admission_allowed"] is False
    policy = c.current["state"]["risk_policy"]
    policy["body"]["limits"]["per_trade_max_loss"] = "10"
    policy["digest"] = digest({key: value for key, value in policy.items() if key != "digest"})
    c.confirmation["policy_digest"] = c.bundle["policy_digest"] = policy["digest"]
    c.confirmation["policy_acceptance_ref"] = sign(c.directory, "policy_acceptance",
        dict(binding=c.binding, policy=policy, accepted_by=OWNER, authentication="authenticated_owner_session"))
    c.resign()
    captured = await capture(c)  # Source truth is separate from risk approval.
    result = risk.prepare_stage(c.current, c.terms, expected_version=4,
                                trade_evidence=captured.opening_trade_evidence, frame=captured.frame, now=NOW)
    assert result["status"] == "refuse"
    assert result["state"] is None and result["admission_allowed"] is False


async def test_complete_held_book_is_valued_from_stored_marks(setup):
    from services.agent.paper.valuation import observe
    c = setup
    c.current["state"]["cash"] = "9800"
    c.current["state"]["positions"]["synthetic-held"] = dict(
        contract_id=CID, product_kind="option", premium_factor="100", lots=[dict(quantity=1, cost_per_unit="200")])
    captured = await capture(c)
    observation = observe(c.current["state"], captured.frame, now=NOW, binding=c.binding)
    assert observation["equity"] == "10000.0"
    assert observation["unknown_positions"] == 0
    assert observation["positions"][0]["mark_source"] == captured.executable_quote["source_id"]


async def test_stored_view_cannot_redirect_reader_to_external_file(setup):
    c = setup
    bait = c.path.parent / "synthetic-private-file.txt"
    bait.write_text("SYNTHETIC-DO-NOT-READ-AS-SOURCE")
    conn = duckdb.connect(str(c.path))
    conn.execute("ALTER TABLE heatmap_snapshots_v2 RENAME TO original_header")
    # A table-shaped view attempts external file access when selected. The
    # constructor path is trusted, but the reader still rejects this metadata.
    escaped = str(bait).replace("'", "''")
    conn.execute("CREATE VIEW heatmap_snapshots_v2 AS SELECT 'synthetic-snapshot' AS snapshot_id, "
                 "'SPY' AS ticker, 'public_api' AS data_source, content AS received_at "
                 "FROM read_text('" + escaped + "')")
    conn.close()
    with pytest.raises(SourceRefusal, match="stored_snapshot_unavailable_or_ambiguous"):
        await c.source.read(c.bundle["selections"])
    assert bait.read_text() == "SYNTHETIC-DO-NOT-READ-AS-SOURCE"


async def test_even_a_local_table_view_is_not_an_admitted_snapshot(setup):
    c = setup
    conn = duckdb.connect(str(c.path))
    conn.execute("ALTER TABLE contract_observations_v2 RENAME TO original_contracts")
    conn.execute("CREATE VIEW contract_observations_v2 AS SELECT * FROM original_contracts")
    conn.close()
    with pytest.raises(SourceRefusal, match="stored_snapshot_unavailable_or_ambiguous"):
        await c.source.read(c.bundle["selections"])


@pytest.mark.parametrize("value", ["", "   ", "\t", "DEFAULT_STANDARD", "MULTIPLIER_UNKNOWN"])
async def test_review_blank_or_unknown_multiplier_provenance(setup, value):
    c = setup
    conn = duckdb.connect(str(c.path))
    conn.execute("UPDATE contract_observations_v2 SET multiplier_source=?", [value])
    conn.close()
    rows = await c.source.read(c.bundle["selections"])
    c.bundle["source_refs"] = ["public-stored:" + digest(row) for row in rows]
    c.resign()
    with pytest.raises(SourceRefusal, match="standard_multiplier_unverified"):
        await capture(c)
    assert "standard_multiplier_unverified" in inspect_stored_row(rows[0], now=NOW, max_age_seconds=60)["gaps"]


async def test_review_exact_same_contract_reduction_target_is_authorized(setup):
    c = setup
    opening = (await capture(c)).opening_trade_evidence
    c.terms.update(side="sell", structure_id="held-A")
    c.current["state"]["cash"] = "9600"
    for key in ("held-A", "held-B"):
        c.current["state"]["positions"][key] = dict(contract_id=CID, product_kind="option", premium_factor="100",
                                                    lots=[dict(quantity=1, cost_per_unit="200")])
        c.current["state"]["exit_capacity"][key] = dict(events=execution.EXIT_EVENTS,
                                                        orders=execution.EXIT_ORDERS, quotes=execution.EXIT_QUOTES)
    c.current["state"]["risk_trades"] = {key: copy.deepcopy(opening) for key in ("held-A", "held-B")}
    c.confirmation["intent"] = c.bundle["intent"] = dict(kind="stage", order_id=EPOCH + ":1", structure_id="held-A")
    c.confirmation["economics"] = risk.economics(c.terms)
    c.bundle["economics_digest"] = digest(risk.economics(c.terms))
    c.resign()
    first = await capture(c, action="reduce")
    legitimate = risk.prepare_stage(c.current, c.terms, expected_version=4, trade_evidence=None, frame=first.frame, now=NOW)
    assert legitimate["status"] == "pass", legitimate["reason"]
    redirected = dict(c.terms, structure_id="held-B")
    # Both held structures have the same valid source and economics. Authority,
    # not generic risk arithmetic, must distinguish the exact intended target.
    with pytest.raises(SourceRefusal, match="intent"):
        await capture(c, action="reduce", frozen_parameters=redirected)
    with pytest.raises(SourceRefusal, match="intent"):
        await verify(c, first, frozen_parameters=redirected)


@pytest.fixture
async def service_context(setup, tmp_path):
    # Actual service/admission/guarded repository, with faithful isolated Mongo
    # fake and a private temporary lease. No application book or live service.
    from test_agent_paper_runner import _FakeDatabase

    from scripts.paper_synthetic_fixture import persist_synthetic_policy
    from services.agent.paper.execution_control import PaperExecutionAuthority
    from services.agent.paper.guarded_repository import GuardedPaperRepository
    from services.agent.paper.service import PreparedPaperService
    from services.execution_lease import acquire_lease, release_lease

    c = setup
    repo = GuardedPaperRepository(_FakeDatabase())
    await repo.initialize()
    await repo.create(OWNER, ACCOUNT, execution.new_book("10000", currency="USD"))
    await persist_synthetic_policy(repo, OWNER, ACCOUNT, synthetic_policy_body(), now=NOW)
    lease_path = str(tmp_path / "synthetic-public-executor.lease")
    lease = acquire_lease(lease_path, "synthetic-public-service")
    assert lease["ok"]
    authority = PaperExecutionAuthority(lease_path, lease["token"], lambda: "running")
    c.repo = repo
    c.adapter.repository = repo
    c.service = PreparedPaperService(repo, admission_adapter=c.adapter, execution_authority=authority, clock=lambda: c.clock[0])
    repo.accounts.server_clock = lambda: c.clock[0]
    await c.service.admission.bind_execution(OWNER, ACCOUNT)
    c.current = await repo.read(OWNER, ACCOUNT)
    c.binding = binding_of(c.current)
    c.terms.update(latency_ms=1000, slippage_enabled=False)
    policy = c.current["state"]["risk_policy"]
    c.confirmation.update(binding=c.binding, policy_digest=policy["digest"], account_version=c.current["version"],
                          economics=risk.economics(c.terms),
                          intent=dict(kind="stage", order_id=c.current["epoch"] + ":1", structure_id=c.current["epoch"] + ":1"))
    c.confirmation["policy_acceptance_ref"] = sign(c.directory, "policy_acceptance",
        dict(binding=c.binding, policy=policy, accepted_by=OWNER, authentication="authenticated_owner_session"))
    c.bundle.update(binding=c.binding, policy_digest=policy["digest"], economics_digest=digest(risk.economics(c.terms)),
                    intent=c.confirmation["intent"])
    c.resign()
    try:
        yield c
    finally:
        release_lease(lease_path, lease["token"])


async def service_operation(c):
    from services.agent.paper.repository import operation_id
    current = await c.repo.read(OWNER, ACCOUNT)
    return operation_id(current["version"], epoch=current["epoch"])


async def service_stage(c):
    parent = await service_operation(c)
    result, created = await c.service.stage(OWNER, ACCOUNT, parent, c.terms, c.ref)
    assert created
    assert result["body"]["assessment_status"] == "pass"
    c.stage_artifact = next(row for row in c.repo.admissions.docs if row["parent_operation"] == parent)
    c.stage_order = result["body"]["order_id"]
    await c.service.admission.replenish(OWNER, ACCOUNT)
    return result


async def issue_synthetic_fill(c, *, new_time=None, quote_changes=None, capture_inputs=True):
    # TEST-ONLY issuer: independently signed new source after the 1s latency.
    c.current = await c.repo.read(OWNER, ACCOUNT)
    order = c.current["state"]["orders"][c.stage_order]
    at = new_time or NOW + timedelta(seconds=2)
    c.clock[0] = at
    sid = "synthetic-fresh-fill-" + str(c.current["version"])
    save_snapshot(c.path, sid=sid, changes={"bid_timestamp": at.isoformat(), "ask_timestamp": at.isoformat(),
                                           "received_at": at.isoformat(), **(quote_changes or {})})
    c.bundle["selections"] = [dict(snapshot_id=sid, contract_id=CID)]
    c.bundle["source_refs"] = ["public-stored:" + digest(row) for row in await c.source.read(c.bundle["selections"])]
    intent = dict(kind="fill", order_id=order["order_id"], structure_id=order["structure_id"],
                  stage_artifact_digest=c.stage_artifact["artifact_digest"])
    c.confirmation.update(intent=intent, account_version=c.current["version"], accepted_at=at.isoformat(),
                          economics=risk.economics(order))
    c.bundle.update(intent=intent, verified_at=at.isoformat(), economics_digest=digest(risk.economics(order)))
    c.resign()
    selector = dict(binding=c.binding, policy_digest=c.confirmation["policy_digest"],
                    account_version=c.current["version"], intent=intent)
    KEYS["fill_selection"] = KEYS["confirmation"]
    ref = sign(c.directory, "fill_selection", dict(selector=selector, confirmation_id=c.ref["confirmation_id"]))
    index_path = c.directory / ("fill-" + digest(selector) + ".json")
    index_path.write_bytes((c.directory / (ref + ".json")).read_bytes())
    c.fill_index = index_path
    if not capture_inputs:
        return None
    return await c.adapter.capture_verified_inputs(binding=c.binding, expected_version=c.current["version"], action="entry",
                                                  frozen_parameters=order, quote=None, confirmation_ref=None)


async def test_review_real_service_stage_and_fill_after_one_second_latency(service_context):
    c = service_context
    await service_stage(c)
    original = await c.repo.read(OWNER, ACCOUNT)
    with pytest.raises(SourceRefusal, match="fresh_fill_authority_unavailable"):
        await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, None)
    assert await c.repo.read(OWNER, ACCOUNT) == original
    captured = await issue_synthetic_fill(c)
    assert execution.instant(captured.executable_quote["observed_at"]) >= NOW + timedelta(seconds=1)
    operation = await service_operation(c)
    result, created = await c.service.quote(OWNER, ACCOUNT, operation, c.stage_order, captured.executable_quote)
    assert created and result["body"]["assessment_status"] == "pass"
    after = await c.repo.read(OWNER, ACCOUNT)
    assert after["state"]["orders"][c.stage_order]["filled"] == 1
    assert after["state"]["cash"] == "9789.35"
    # Exact saved receipt is recoverable without recapture, even after expiry.
    c.clock[0] += timedelta(hours=2)
    retried, created = await c.service.quote(OWNER, ACCOUNT, operation, c.stage_order, captured.executable_quote)
    assert not created and retried == result
    assert await c.repo.read(OWNER, ACCOUNT) == after


async def test_review_same_economics_fill_order_substitution_refused(service_context):
    c = service_context
    await service_stage(c)
    captured = await issue_synthetic_fill(c)
    current = await c.repo.read(OWNER, ACCOUNT)
    original = current["state"]["orders"][c.stage_order]
    other = c.current["epoch"] + ":999"
    current["state"]["orders"][other] = dict(original, order_id=other)
    with pytest.raises(SourceRefusal, match="lineage_missing"):
        await c.adapter.verify_admission(owner=OWNER, current_account=current,
            frozen_parameters=current["state"]["orders"][other], confirmation_record=captured.confirmation_record,
            immutable_source_refs=captured.immutable_source_refs)


async def test_review_fill_parent_and_index_tampering_refuses(service_context):
    c = service_context
    await service_stage(c)
    captured = await issue_synthetic_fill(c)
    record = json.loads(c.fill_index.read_text())
    record["body"]["selector"]["account_version"] += 1
    c.fill_index.write_text(canonical(record))
    with pytest.raises(SourceRefusal, match="authentication_failed"):
        await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, captured.executable_quote)
    await issue_synthetic_fill(c)
    c.repo.admissions.docs[0]["command"]["parameters"]["quantity"] += 1
    with pytest.raises(SourceRefusal, match="stage_artifact_changed"):
        await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, captured.executable_quote)



async def test_review_partial_fills_preserve_identity_as_mutable_order_fields_change(service_context):
    c = service_context
    c.terms["quantity"] = 2
    c.confirmation["economics"] = risk.economics(c.terms)
    c.bundle["economics_digest"] = digest(risk.economics(c.terms))
    c.bundle["costs"]["maximum_loss"] = "434.60"
    c.resign()
    await service_stage(c)
    first = await issue_synthetic_fill(c, quote_changes=dict(bid_size=1, ask_size=1))
    await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, first.executable_quote)
    current = await c.repo.read(OWNER, ACCOUNT)
    assert current["state"]["orders"][c.stage_order]["remaining"] == 1
    assert len(current["state"]["orders"][c.stage_order]["fills"]) == 1
    await c.service.admission.replenish(OWNER, ACCOUNT)
    # Reconstruct adapter as a restarted process, keeping durable stage lineage.
    c.adapter = PublicPaperSourceAdapter(c.repo, snapshots=c.source, evidence=c.authority, clock=lambda: c.clock[0])
    c.service.admission.adapter = c.adapter
    second = await issue_synthetic_fill(c, new_time=NOW + timedelta(seconds=3))
    await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, second.executable_quote)
    current = await c.repo.read(OWNER, ACCOUNT)
    assert current["state"]["orders"][c.stage_order]["filled"] == 2
    assert current["state"]["cash"] == "9578.70"
    assert len(current["state"]["orders"][c.stage_order]["fills"]) == 2


async def test_review_existing_risk_retains_pre_latency_refusal(service_context):
    c = service_context
    await service_stage(c)
    early = (NOW + timedelta(milliseconds=500)).isoformat()
    captured = await issue_synthetic_fill(c, quote_changes=dict(bid_timestamp=early, ask_timestamp=early))
    with pytest.raises(PaperConflict, match="before simulated latency"):
        await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, captured.executable_quote)
    current = await c.repo.read(OWNER, ACCOUNT)
    assert current["state"]["cash"] == "10000"
    assert current["state"]["orders"][c.stage_order]["filled"] == 0
    assert not current["state"]["risk_control"]["pending"]
    assert len(c.repo.admissions.docs) == 2  # Refused assessment retained durably.


async def test_review_stale_fresh_source_selection_never_writes(service_context):
    c = service_context
    await service_stage(c)
    before = await c.repo.read(OWNER, ACCOUNT)
    stale = (NOW - timedelta(seconds=61)).isoformat()
    await issue_synthetic_fill(c, new_time=NOW + timedelta(seconds=2), capture_inputs=False,
                               quote_changes=dict(bid_timestamp=stale, ask_timestamp=stale))
    with pytest.raises(SourceRefusal, match="bid_stale"):
        await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, None)
    assert await c.repo.read(OWNER, ACCOUNT) == before
    assert len(c.repo.admissions.docs) == 1


async def test_review_missing_successful_stage_receipt_refuses(service_context):
    c = service_context
    await service_stage(c)
    captured = await issue_synthetic_fill(c)
    operation = c.stage_artifact["resolve_operation"]
    c.repo.events.docs = [event for event in c.repo.events.docs if event["operation_id"] != operation]
    # replenish projected the stage events; deleting only this synthetic durable
    # receipt must not let a signed source/index invent an executed stage.
    with pytest.raises(SourceRefusal, match="successful_stage_receipt"):
        await c.service.quote(OWNER, ACCOUNT, await service_operation(c), c.stage_order, captured.executable_quote)
