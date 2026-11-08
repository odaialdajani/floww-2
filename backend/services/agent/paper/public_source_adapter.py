"""Read-only Public snapshot admission; never installed or provisioned on import.

Public's stored quote rows alone are insufficient authority. The constructor
must receive independently provisioned, authenticated persisted confirmations
and evidence. This module contains no issuer, writer, account creation or broker
capability. Local hashes bind bytes; only the injected issuer keys authenticate
missing units, lifecycle, costs, opening equity and owner acceptance.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from services.agent.paper import execution, risk, valuation
from services.agent.paper.accounting import exact
from services.agent.paper.admission import CapturedInputs
from services.agent.paper.policy import binding_of, validate_policy, valuation_policy
from services.agent.paper.repository import PaperConflict, canonical, digest, operation_version, scope, validate_json
from services.solstice_calendar import ET, exchange_day_info

MAX_ROWS = 64
MAX_BYTES = 64 * 1024
REF = re.compile(r"[a-f0-9]{64}")
OSI = re.compile(r"([A-Z][A-Z0-9.]{0,11})(\d{6})([CP])(\d{8})")


class SourceRefusal(PaperConflict):
    """Stable local refusal code; no provider data, credentials or paths."""


def _require(test, code):
    if not test:
        raise SourceRefusal(code)


def _bounded(value):
    try:
        value = validate_json(value)
        _require(len(canonical(value).encode()) <= MAX_BYTES, "source_bytes_exceeded")
        return value
    except (TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, SourceRefusal):
            raise
        raise SourceRefusal("source_record_invalid") from None


def _ref(value):
    _require(isinstance(value, str) and REF.fullmatch(value), "evidence_reference_invalid")
    return value


def _multiplier_provenance(value):
    # Actual recorder shape is a bounded label, not a producer-authenticated
    # enum. Reject its known analytical refusal/default markers; the separate
    # signed source issuer must still establish the label's factual origin.
    return (isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:/-]{0,199}", value) is not None
            and value not in {"DEFAULT_STANDARD", "MULTIPLIER_UNKNOWN", "MULTIPLIER_INVALID",
                              "MULTIPLIER_ALIAS_DISAGREE", "CONTRACT_QUARANTINED"})


class AuthenticatedEvidenceDirectory:
    """Read existing content-addressed records, authenticated with server keys.

    A separate issuer MUST establish authenticated owner acceptance and source
    truth before signing. There is deliberately no issuance/provisioning API.
    Keys are constructor capabilities, never accepted through capture requests.
    Production issuance and key management are not supplied by this adapter.
    """
    def __init__(self, directory, *, confirmation_key: bytes, evidence_key: bytes):
        _require(all(type(key) is bytes and len(key) >= 32
                     for key in (confirmation_key, evidence_key)), "issuer_keys_unavailable")
        _require(confirmation_key != evidence_key, "independent_issuer_keys_required")
        self._directory = Path(directory).resolve(strict=True)
        self._keys = {"confirmation": confirmation_key, "policy_acceptance": confirmation_key,
                      "source_evidence": evidence_key, "fill_selection": confirmation_key}

    async def read(self, reference, kind):
        return await self._read_file(_ref(reference) + ".json", kind, expected_digest=reference)

    async def resolve_fill(self, selector):
        """Read an independently issued exact-version selector, never issue one.

        Its owner-role signature binds the exact successful stage lineage and
        chooses a separately signed fill confirmation/fresh source bundle.
        """
        selector = _bounded(selector)
        try:
            record = await self._read_file("fill-" + digest(selector) + ".json", "fill_selection")
        except SourceRefusal as exc:
            if str(exc) == "persisted_evidence_unavailable":
                raise SourceRefusal("fresh_fill_authority_unavailable") from None
            raise
        body = record["body"]
        _require(isinstance(body, dict) and set(body) == {"selector", "confirmation_id"}
                 and body["selector"] == selector, "fill_selection_binding_mismatch")
        return dict(confirmation_id=_ref(body["confirmation_id"])), "fill-selection:" + digest(record)

    async def _read_file(self, filename, kind, *, expected_digest=None):
        _require(kind in self._keys, "evidence_kind_invalid")
        try:
            fd = os.open(self._directory / filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, "evidence_file_invalid")
                raw = stream.read(MAX_BYTES + 1)
            _require(len(raw) <= MAX_BYTES, "source_bytes_exceeded")
            record = _bounded(json.loads(raw))
            _require(set(record) == {"kind", "body", "signature"} and record["kind"] == kind,
                     "evidence_kind_invalid")
            _require(expected_digest is None or digest(record) == expected_digest, "immutable_evidence_changed")
            expected = hmac.new(self._keys[kind], canonical({"kind": kind, "body": record["body"]}).encode(),
                                hashlib.sha256).hexdigest()
            _require(isinstance(record["signature"], str)
                     and hmac.compare_digest(expected, record["signature"]), "evidence_authentication_failed")
            return record
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            raise SourceRefusal("persisted_evidence_unavailable") from None


# Child has no application imports, provider client, environment-derived path or
# migration helpers. Every query uses bound parameters and a finite row limit.
# Only the exact existing recorder schema is selected; no ensure_tables call.
_READ_SCRIPT = r'''
import duckdb, json, sys
path, selections = json.loads(sys.stdin.read(65537))
conn = duckdb.connect(path, read_only=True, config={"threads": 1, "memory_limit": "64MB",
    "enable_external_access": False, "autoinstall_known_extensions": False, "autoload_known_extensions": False})
required = {'heatmap_snapshots_v2', 'contract_observations_v2'}
tables = conn.execute("SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='main' AND table_name IN ('heatmap_snapshots_v2','contract_observations_v2')").fetchall()
if len(tables)!=2 or {name for name,kind in tables if kind=='BASE TABLE'}!=required:
    raise ValueError('stored_base_tables_required')
headers = "snapshot_id ticker data_source received_at".split()
fields = "snapshot_id ticker osi expiry strike_exact opt_type multiplier multiplier_source bid ask bid_size ask_size bid_ts ask_ts received_at provider".split()
text_fields = set(fields) - {"multiplier", "bid", "ask", "bid_size", "ask_size"}
def columns(names):
    return ','.join(("CASE WHEN length("+n+")<=200 THEN "+n+" ELSE NULL END AS "+n) if n in text_fields or n in headers else ("CAST("+n+" AS VARCHAR) AS "+n if n in {"multiplier", "bid", "ask"} else n) for n in names)
conn.execute("BEGIN TRANSACTION")
result=[]
for selection in selections:
    header=conn.execute("SELECT "+columns(headers)+" FROM main.heatmap_snapshots_v2 WHERE snapshot_id=? LIMIT 2", [selection['snapshot_id']]).fetchall()
    rows=conn.execute("SELECT "+columns(fields)+" FROM main.contract_observations_v2 WHERE snapshot_id=? AND osi=? LIMIT 2", [selection['snapshot_id'], selection['contract_id']]).fetchall()
    if len(header)!=1 or len(rows)!=1:
        raise ValueError('missing_or_ambiguous_source')
    result.append({'snapshot':dict(zip(headers,header[0])), 'contract':dict(zip(fields,rows[0]))})
conn.execute("ROLLBACK")
conn.close()
encoded=json.dumps(result,allow_nan=False,separators=(',',':'))
if len(encoded.encode())>65536: raise ValueError('source_bytes_exceeded')
sys.stdout.write(encoded)
'''


class StoredPublicSnapshots:
    """Bounded data-only reads of existing recorder rows in one DB snapshot."""
    def __init__(self, path, *, timeout_seconds=3):
        self._path = str(Path(path).resolve(strict=True))
        _require(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 5,
                 "source_timeout_invalid")
        self._timeout = timeout_seconds

    async def read(self, selections):
        selections = _bounded(selections)
        _require(isinstance(selections, list) and 1 <= len(selections) <= MAX_ROWS, "source_rows_exceeded")
        seen = set()
        for item in selections:
            _require(isinstance(item, dict) and set(item) == {"snapshot_id", "contract_id"}, "source_selection_invalid")
            _require(all(isinstance(v, str) and 1 <= len(v) <= 200 for v in item.values()), "source_selection_invalid")
            key = tuple(item.values())
            _require(key not in seen, "duplicate_source_selection")
            seen.add(key)
        def run():
            try:
                completed = subprocess.run([sys.executable, "-I", "-c", _READ_SCRIPT],
                                           input=canonical([self._path, selections]), text=True,
                                           capture_output=True, timeout=self._timeout, check=False)
                _require(completed.returncode == 0, "stored_snapshot_unavailable_or_ambiguous")
                _require(len(completed.stdout.encode()) <= MAX_BYTES, "source_bytes_exceeded")
                return _bounded(json.loads(completed.stdout))
            except subprocess.TimeoutExpired:
                raise SourceRefusal("stored_snapshot_deadline") from None
            except (OSError, json.JSONDecodeError):
                raise SourceRefusal("stored_snapshot_unavailable") from None
        return await asyncio.to_thread(run)


def market_session(now):
    now = execution.instant(now)
    day = now.astimezone(ET).date().isoformat()
    info = exchange_day_info(day)
    _require(info["is_open"], "market_closed_or_calendar_unknown")
    opened = datetime.fromisoformat(day + "T" + info["open_et"]).replace(tzinfo=ET).astimezone(UTC)
    closed = datetime.fromisoformat(day + "T" + info["close_et"]).replace(tzinfo=ET).astimezone(UTC)
    _require(opened <= now < closed, "market_session_cutoff")
    return dict(session_id="XNYS:" + day, calendar_version=info["version"],
                source_id="XNYS:" + day, opened_at=opened.isoformat(), closed_at=closed.isoformat())


def inspect_stored_row(record, *, now, max_age_seconds):
    """Return source facts and precise gaps without granting admission.

    Size units, currency, standard deliverable/lifecycle, costs, owner approval
    and account-opening evidence never exist in this recorder schema.
    """
    record = _bounded(record)
    _require(isinstance(record, dict) and isinstance(record.get("contract"), dict), "stored_row_schema_invalid")
    row = record["contract"]
    gaps = ["size_unit_unverified", "price_currency_unverified", "lifecycle_unverified",
            "corporate_action_status_unverified", "costs_unverified", "confirmation_unavailable",
            "policy_acceptance_unavailable", "session_open_equity_unverified"]
    if not _multiplier_provenance(row.get("multiplier_source")):
        gaps.append("standard_multiplier_unverified")
    try:
        market_session(now)
    except SourceRefusal as exc:
        gaps.append(str(exc))
    for side in ("bid", "ask"):
        size = row.get(side + "_size")
        if size is None:
            gaps.append(side + "_size_missing")
        elif type(size) is not int or size <= 0:
            gaps.append(side + "_size_nonpositive_or_invalid")
        try:
            stamp = execution.instant(row.get(side + "_ts"))
            receipt = execution.instant(row.get("received_at"))
            checked = execution.instant(now)
            if not stamp <= receipt <= checked:
                gaps.append(side + "_clock_order_invalid")
            elif (checked - stamp).total_seconds() > max_age_seconds:
                gaps.append(side + "_stale")
        except (ValueError, TypeError):
            gaps.append(side + "_clock_missing_or_invalid")
    return dict(admitted=False, source_ref="public-stored:" + digest(record), gaps=gaps,
                quote_source=dict(bid_event_at=row.get("bid_ts"), ask_event_at=row.get("ask_ts"),
                                  received_at=row.get("received_at"), bid_size=row.get("bid_size"),
                                  ask_size=row.get("ask_size")))


def inspect_saved_observations(payload, *, now):
    """Inspect the existing saved-scan read route without refreshing any scan.

    This legacy shape has neither snapshot identities nor executable sizes.
    It is useful for an honest readiness report only, never CapturedInputs.
    """
    try:
        _require(len(canonical(payload).encode()) <= MAX_BYTES, "source_bytes_exceeded")
        _require(isinstance(payload, dict) and payload.get("source") == "public-scan-observations", "saved_source_schema_invalid")
        rows = payload.get("rows")
        _require(isinstance(rows, list) and len(rows) <= MAX_ROWS, "source_rows_exceeded")
        results = []
        def stamp(value):
            if type(value) not in (float, int) or not math.isfinite(value):
                return None
            return datetime.fromtimestamp(value, UTC).isoformat()
        for row in rows:
            _require(isinstance(row, list) and len(row) == 10, "saved_row_schema_invalid")
            key = f"{row[0]}|{row[2]}|{float(row[3]):g}|{row[4]}"
            truth = payload.get("quote_truth", {}).get(key, {})
            observation = payload.get("row_observations", {}).get(key, {})
            _require(isinstance(truth, dict) and isinstance(observation, dict), "saved_row_schema_invalid")
            contract = dict(osi=row[1], ticker=row[0], opt_type=row[2], strike_exact=str(row[3]), expiry=row[4],
                            provider=observation.get("source"), received_at=stamp(observation.get("received_at")),
                            bid_ts=stamp(truth.get("bid_source_time")), ask_ts=stamp(truth.get("ask_source_time")),
                            bid_size=truth.get("bid_size"), ask_size=truth.get("ask_size"),
                            bid=str(truth["bid"]) if truth.get("bid") is not None else None,
                            ask=str(truth["ask"]) if truth.get("ask") is not None else None)
            result = inspect_stored_row(dict(contract=contract), now=now, max_age_seconds=60)
            result["gaps"] += ["immutable_recorder_snapshot_unavailable", "saved_scan_not_execution_source"]
            results.append(dict(contract_id=row[1], **result))
        return dict(admitted=False, source="public-scan-observations", source_digest=digest(payload),
                    checked_at=execution.instant(now).isoformat(), observations=results,
                    gaps=[] if rows else ["saved_observations_empty"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, SourceRefusal):
            raise
        raise SourceRefusal("saved_source_schema_invalid") from None


class PublicPaperSourceAdapter:
    """Constructor-only TrustedPaperAdapter over stored data and signed records.

    Requests select one persisted confirmation ID only. They supply no frame,
    equity, source calendar, metadata, cost schedule or authenticated approval.
    Risk is still calculated by the existing PaperAdmissionService.
    """
    def __init__(self, repository, *, snapshots: StoredPublicSnapshots,
                 evidence: AuthenticatedEvidenceDirectory, clock=None):
        _require(isinstance(snapshots, StoredPublicSnapshots), "stored_source_reader_required")
        _require(isinstance(evidence, AuthenticatedEvidenceDirectory), "authenticated_repository_required")
        self.repository, self.snapshots, self.evidence = repository, snapshots, evidence
        self.clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _stage_intent(current, parameters):
        order_id = current["epoch"] + ":" + str(current["state"]["next_order_sequence"])
        structure = parameters.get("structure_id") if parameters.get("side") == "sell" else order_id
        _require(isinstance(structure, str) and 1 <= len(structure) <= 200, "exact_intent_target_required")
        if parameters.get("side") == "buy":
            _require(parameters.get("structure_id") in (None, order_id), "stage_intent_target_mismatch")
        else:
            _require(structure in current["state"]["positions"], "stage_intent_held_target_missing")
        return dict(kind="stage", order_id=order_id, structure_id=structure)

    async def _stage_lineage(self, current, parameters):
        """Resolve one successful immutable stage and match fixed order identity.

        Remaining quantity, status, fills and book versions legitimately evolve;
        they are not a replacement for immutable parent/order authorization.
        """
        order_id = parameters.get("order_id")
        order = current["state"]["orders"].get(order_id)
        _require(isinstance(order, dict) and order.get("order_id") == order_id
                 and risk.economics(order) == risk.economics(parameters)
                 and all(order.get(key) == parameters.get(key) for key in ("structure_id", "created_at")),
                 "fill_exact_stored_order_required")
        _require(hasattr(self.repository, "admissions"), "fill_stage_lineage_unavailable")
        binding = scope(current["owner"], current["account_id"], "internal")
        query = {**binding, "epoch": current["epoch"], "command.kind": "stage",
                 "confirmation_record.body.intent.order_id": order_id}
        parents = [record async for record in self.repository.admissions.find(query).limit(2)]
        _require(len(parents) == 1, "fill_stage_lineage_missing_or_ambiguous")
        parent = _bounded(parents[0])
        parent_id, parent_digest = parent.get("parent_operation"), parent.get("artifact_digest")
        _require(parent_digest == digest({k: v for k, v in parent.items() if k != "artifact_digest"})
                 and parent.get("_id") == digest([binding, parent_id])
                 and parent.get("starting_version") == operation_version(parent_id)
                 and parent_id.split(":", 1)[0] == current["epoch"]
                 and all(parent.get(key) == value for key, value in binding.items())
                 and parent.get("epoch") == current["epoch"] and parent["command"].get("kind") == "stage"
                 and parent.get("action") == ("entry" if order["side"] == "buy" else "reduce"), "fill_stage_artifact_changed")
        intent = dict(kind="stage", order_id=order_id, structure_id=order["structure_id"])
        stage_confirmation = await self.evidence.read(digest(parent["confirmation_record"]), "confirmation")
        body = stage_confirmation["body"]
        _require(isinstance(body, dict), "stage_confirmation_body_invalid")
        _require(stage_confirmation == parent["confirmation_record"] and body.get("intent") == intent
                 and body.get("binding") == binding_of(current) and body.get("accepted_by") == current["owner"]
                 and body.get("authentication") == "authenticated_owner_session"
                 and body.get("policy_digest") == current["state"]["risk_policy"]["digest"]
                 and body.get("policy_digest") == parent.get("policy_digest")
                 and body.get("account_version") == parent["starting_version"]
                 and body.get("economics") == risk.economics(order)
                 and risk.economics(parent["command"]["parameters"]) == risk.economics(order)
                 and order.get("risk_economics_digest") == digest(risk.economics(order)), "fill_stage_intent_mismatch")
        expected_structure = (order_id if order["side"] == "buy"
                              else parent["command"]["parameters"].get("structure_id"))
        _require(expected_structure == order["structure_id"], "fill_stage_structure_mismatch")
        resolve = parent["resolve_operation"]
        _require(resolve.split(":", 1)[0] == current["epoch"]
                 and operation_version(resolve) == parent["starting_version"] + 1, "fill_stage_resolution_invalid")
        receipt = await self.repository.receipt(current["owner"], current["account_id"], resolve,
            dict(kind="paper_admission_resolve", parent_operation=parent_id, artifact_digest=parent_digest))
        event = (receipt or {}).get("body", {})
        decision = event.get("risk_decision", {})
        _require(receipt is not None and receipt.get("version") == parent["starting_version"] + 2
                 and receipt.get("operation_id") == resolve
                 and receipt["version"] <= current["version"] and event.get("assessment_status") == "pass"
                 and event.get("kind") == "paper_order_staged" and event.get("order_id") == order_id
                 and event.get("structure_id") == order["structure_id"]
                 and decision.get("status") == "pass"
                 and decision.get("evaluated_at") == order.get("created_at")
                 and decision.get("binding") == binding_of(current)
                 and decision.get("policy_digest") == body["policy_digest"], "fill_successful_stage_receipt_required")
        return dict(kind="fill", order_id=order_id, structure_id=order["structure_id"],
                    stage_artifact_digest=parent_digest)

    async def _authority(self, reference, current, parameters, *, capture):
        now = execution.instant(self.clock())
        policy = validate_policy(current["state"].get("risk_policy"), binding_of(current), now=now)
        extra_refs = []
        if "order_id" in parameters:
            intent = await self._stage_lineage(current, parameters)
            version = current["version"]
            if not capture:
                _require(isinstance(reference, dict) and set(reference) == {"confirmation_id"}, "confirmation_selection_only")
                retained = await self.evidence.read(reference["confirmation_id"], "confirmation")
                version = retained["body"].get("account_version")
            selector = dict(binding=binding_of(current), policy_digest=policy["digest"],
                            account_version=version, intent=intent)
            selected, index_ref = await self.evidence.resolve_fill(selector)
            _require(reference is None or reference == selected, "fill_confirmation_selection_mismatch")
            reference = selected
            extra_refs = [index_ref, "stage-artifact:" + intent["stage_artifact_digest"]]
        else:
            intent = self._stage_intent(current, parameters)
        _require(isinstance(reference, dict) and set(reference) == {"confirmation_id"}, "confirmation_selection_only")
        signed = await self.evidence.read(reference["confirmation_id"], "confirmation")
        body = signed["body"]
        _require(isinstance(body, dict), "confirmation_body_invalid")
        _require(body.get("binding") == binding_of(current) and body.get("accepted_by") == current["owner"]
                 and body.get("authentication") == "authenticated_owner_session", "confirmation_owner_mismatch")
        _require(body.get("policy_digest") == policy["digest"], "confirmation_policy_mismatch")
        _require(body.get("intent") == intent, "confirmation_intent_mismatch")
        _require(body.get("economics") == risk.economics(parameters), "confirmation_economics_mismatch")
        version = body.get("account_version")
        _require(type(version) is int and current["version"] in ((version,) if capture else (version, version + 1)),
                 "confirmation_account_version_mismatch")
        _require(execution.instant(body.get("accepted_at")) <= now < execution.instant(body.get("valid_until")),
                 "confirmation_expired_or_future")
        acceptance = (await self.evidence.read(body.get("policy_acceptance_ref"), "policy_acceptance"))["body"]
        _require(acceptance == dict(binding=binding_of(current), policy=policy,
                                    accepted_by=current["owner"], authentication="authenticated_owner_session"),
                 "policy_acceptance_mismatch")
        bundle = (await self.evidence.read(body.get("evidence_ref"), "source_evidence"))["body"]
        _require(isinstance(bundle, dict), "source_evidence_body_invalid")
        _require(bundle.get("binding") == binding_of(current) and bundle.get("policy_digest") == policy["digest"]
                 and bundle.get("economics_digest") == digest(risk.economics(parameters)), "source_evidence_binding_mismatch")
        _require(bundle.get("intent") == intent, "source_evidence_intent_mismatch")
        _require(execution.instant(bundle.get("verified_at")) <= now < execution.instant(bundle.get("valid_until")),
                 "source_evidence_expired_or_future")
        return signed, bundle, policy, extra_refs

    @staticmethod
    def _quote(record, metadata, terms, now):
        row, header = record["contract"], record["snapshot"]
        _require(header.get("data_source") == row.get("provider") == "public_api", "public_source_unverified")
        _require(row.get("snapshot_id") == header.get("snapshot_id")
                 and row.get("ticker") == header.get("ticker"), "snapshot_identity_mismatch")
        contract = row.get("osi")
        match = OSI.fullmatch(contract or "")
        _require(match is not None and contract == metadata.get("contract_id"), "contract_identity_mismatch")
        root, expiry, right, strike = match.groups()
        _require(root == row.get("ticker") == metadata.get("underlying"), "contract_underlying_mismatch")
        _require(row.get("expiry") == "20" + expiry[:2] + "-" + expiry[2:4] + "-" + expiry[4:]
                 and row.get("expiry") == execution.instant(metadata.get("expiry_at")).astimezone(ET).date().isoformat(),
                 "contract_expiry_mismatch")
        _require(row.get("opt_type") == metadata.get("right") == ("call" if right == "C" else "put")
                 and exact(row.get("strike_exact"), positive=True) == exact(metadata.get("strike"), positive=True)
                 == Decimal(int(strike)) / Decimal(1000), "contract_strike_or_right_mismatch")
        _require(metadata.get("size_unit") == "contracts" and metadata.get("price_unit") == "USD_per_share",
                 "source_units_unverified")
        _require(_multiplier_provenance(row.get("multiplier_source"))
                 and exact(str(row.get("multiplier")), positive=True) == exact(metadata.get("premium_factor")) == 100,
                 "standard_multiplier_unverified")
        _require(metadata.get("corporate_action_status") == "clear" and metadata.get("adjusted") is False
                 and metadata.get("lifecycle_status") == "active", "lifecycle_or_corporate_action_unverified")
        valuation._metadata(terms, metadata, now, "USD")
        # This adapter supports standard physically delivered ETF/equity calls
        # and puts only, before all deadlines. Index/adjusted lifecycle differs.
        _require(metadata.get("instrument_class") == "standard_equity_option"
                 and metadata.get("exercise_style") == "american" and metadata.get("settlement_style") == "physical"
                 and metadata.get("deliverable") == dict(kind="shares", quantity="100", currency="USD", symbol=root),
                 "unsupported_instrument_lifecycle")
        times = {}
        try:
            received = execution.instant(row.get("received_at"))
        except ValueError:
            raise SourceRefusal("quote_receipt_missing_or_invalid") from None
        for side in ("bid", "ask"):
            _require(type(row.get(side + "_size")) is int and row[side + "_size"] > 0, side + "_size_missing_or_nonpositive")
            try:
                times[side] = execution.instant(row.get(side + "_ts"))
            except ValueError:
                raise SourceRefusal(side + "_clock_missing_or_invalid") from None
            _require(times[side] <= received <= now, side + "_clock_order_invalid")
            _require(0 <= (now - times[side]).total_seconds() <= terms["max_quote_age_seconds"], side + "_stale")
        side = "ask" if terms["side"] == "buy" else "bid"
        # Snapshot IDs, receipts, opposite-side updates and changed size/price
        # cannot mint new liquidity for an unchanged selected-side event clock.
        event_id = digest(["public_api", contract, side, times[side].isoformat()])
        quote = dict(contract_id=contract, source_id="public-side:" + event_id,
                     bid=str(row["bid"]), ask=str(row["ask"]), bid_size=row["bid_size"], ask_size=row["ask_size"],
                     size_unit="contracts", observed_at=min(times.values()).isoformat(), received_at=received.isoformat(),
                     bid_observed_at=times["bid"].isoformat(), ask_observed_at=times["ask"].isoformat())
        execution._quote(quote, terms, now)
        return quote

    async def _capture(self, current, parameters, reference, *, capture):
        signed, bundle, policy, extra_refs = await self._authority(reference, current, parameters, capture=capture)
        terms = risk.economics(parameters)
        _require(terms["product_kind"] == "option", "unsupported_instrument")
        market_session(self.clock())
        selections = bundle.get("selections")
        records = await self.snapshots.read(selections)
        now = execution.instant(self.clock())
        _require(now < execution.instant(bundle["valid_until"])
                 and now < execution.instant(signed["body"]["valid_until"]), "source_expired_during_read")
        session = market_session(now)
        refs = ["public-stored:" + digest(record) for record in records]
        _require(refs == bundle.get("source_refs"), "immutable_source_changed")
        metadata = bundle.get("metadata")
        _require(isinstance(metadata, list) and 1 <= len(metadata) <= MAX_ROWS, "contract_metadata_unavailable")
        indexed = valuation._index(metadata)
        needed = {terms["contract_id"]}
        needed.update(item["contract_id"] for item in current["state"]["positions"].values())
        needed.update(item["contract_id"] for item in current["state"]["orders"].values() if item["status"] == "working")
        _require(set(indexed) == needed and {r["contract"]["osi"] for r in records} == needed
                 and len(records) == len(needed), "full_book_source_coverage_required")
        quotes, marks = {}, []
        for record in records:
            cid = record["contract"]["osi"]
            item = indexed[cid]
            checked_terms = terms if cid == terms["contract_id"] else dict(
                terms, contract_id=cid, premium_factor=item.get("premium_factor"),
                max_quote_age_seconds=policy["body"]["valuation"]["max_mark_age_seconds"],
                max_spread=policy["body"]["valuation"]["max_spread"])
            quotes[cid] = self._quote(record, item, checked_terms, now)
            marks.append(dict(quotes[cid], currency="USD"))
        frame = _bounded(dict(policy=valuation_policy(policy), session=session, metadata=metadata,
                              marks=marks, session_open=bundle.get("session_open")))
        observed = valuation.observe(current["state"], frame, now=now, binding=binding_of(current),
                                     previous=current["state"].get("valuation"))
        _require(observed["unknown_positions"] == 0 and observed["equity"] is not None
                 and observed["risk"]["status"] == "observed", "full_book_valuation_or_opening_equity_unverified")
        # No passed-limits Boolean is read or emitted here. Existing services
        # calculate entry/reduction risk and retain observations independently.
        trade = None
        if terms["side"] == "buy" and "order_id" not in parameters:
            costs = bundle.get("costs")
            contract_digest, lifecycle_digest = risk.metadata_digests(indexed[terms["contract_id"]])
            _require(isinstance(costs, dict) and costs.get("contract_digest") == contract_digest
                     and costs.get("lifecycle_digest") == lifecycle_digest, "declared_costs_or_lifecycle_unverified")
            trade = risk.create_trade_evidence(binding_of(current), policy, terms, costs,
                      proposal_version=signed["body"].get("proposal_version"),
                      evidence=[signed["body"]["evidence_ref"]], verified_at=bundle["verified_at"],
                      valid_until=min(execution.instant(bundle["valid_until"]), execution.instant(signed["body"]["valid_until"])),
                      verifier_version="persisted-public-source-v1", now=now,
                      verify_evidence=lambda record: record["costs"] == costs and record["economics"] == signed["body"]["economics"])
        refs += extra_refs + ["confirmation:" + digest(signed), "evidence:" + signed["body"]["evidence_ref"],
                 "policy-acceptance:" + signed["body"]["policy_acceptance_ref"]]
        return CapturedInputs(frame, trade, refs, signed, quotes[terms["contract_id"]])

    async def capture_verified_inputs(self, *, binding, expected_version, action,
                                      frozen_parameters, quote, confirmation_ref):
        current = await self.repository.read(binding["owner"], binding["account_id"])
        _require(current is not None and binding_of(current) == binding and current["version"] == expected_version
                 and not current.get("recovery_pending") and not current["state"].get("recovery_pending"), "source_account_changed")
        _require(action == ("entry" if frozen_parameters.get("side") == "buy" else "reduce"), "source_action_mismatch")
        result = await self._capture(current, frozen_parameters, confirmation_ref, capture=True)
        _require(quote is None or quote == result.executable_quote, "request_quote_not_source_truth")
        return result

    async def verify_admission(self, *, owner, current_account, frozen_parameters,
                               confirmation_record, immutable_source_refs):
        _require(owner == current_account["owner"], "confirmation_owner_mismatch")
        reference = dict(confirmation_id=digest(confirmation_record))
        captured = await self._capture(current_account, frozen_parameters, reference, capture=False)
        _require(captured.confirmation_record == confirmation_record
                 and captured.immutable_source_refs == immutable_source_refs, "captured_evidence_mismatch")
        return True
