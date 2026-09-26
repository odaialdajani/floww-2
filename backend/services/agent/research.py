"""Bounded durable research jobs; observers never own or start execution."""

from __future__ import annotations

import asyncio
import contextlib
import re
from datetime import UTC, datetime, timedelta

from services.agent.access.horizon import horizon_window
from services.agent.answer_sections import build_answer_sections, merge_history_section
from services.agent.contracts import INTERPRETATIONS, finite, validate_model_answer
from services.agent.narrative import request_limit
from services.agent.saved_history import history_facts


def deterministic_answer(snapshots, spec):
    facts = [f for s in snapshots for f in s["facts"]]
    gaps = list(dict.fromkeys(g for s in snapshots for g in s["gaps"]))
    sections = build_answer_sections(snapshots, spec)
    if spec.get("context_conflict"):
        gaps.append("The question names a different ticker from the selected screen; screen contract was not reused")
    if spec.get("question_scope") is not None:
        gaps.append("Expiry scope follows the question; the original chart selection is retained as context only")
    summary = "Available readings are shown below. Exposure estimates do not establish trade direction."
    if not any(finite(f["value"]) and f["metric"] == "Underlying price" for f in facts):
        summary = "There is not enough cached market data to answer reliably. Open the market view and try again."
    limits = request_limit(spec.get("question", ""))
    if limits:
        summary = limits
    elif re.search(r"\bputs?\b", spec.get("question", ""), re.IGNORECASE):
        summary = "Put contract type alone does not establish trade direction; buyer versus seller activity and the wider position matter."
    if spec.get("price_only"):
        price = next((f for f in facts if f["metric"] == "Underlying price"), None)
        summary = (
            f"{price['ticker']} cached underlying price: {price['value']:,.6g} USD "
            f"({price['status']}; observed {price['event_time'] or 'time unknown'})."
            if price
            else "The cached underlying price is unavailable; no paid refresh was started."
        )
    return dict(
        summary=summary,
        sections=sections,
        facts=facts,
        gaps=gaps,
        mode="deterministic",
        model_status="Not requested: factual lookup"
        if spec.get("price_only")
        else "Not requested: paid model policy is not yet verified",
        claim_status="non-gradeable",
        claim_reason="Descriptive research has no testable prediction",
        snapshots=snapshots,
        context=spec["screen"],
        requested_tickers=spec["tickers"],
    )


class ResearchService:
    def __init__(self, repository, reads, *, model=None, concurrent=2, queued=8, timeout=120):
        self.repository, self.reads = repository, reads
        self.model = model
        self._slots = asyncio.Semaphore(concurrent)
        self._admission = asyncio.Lock()
        self.tasks = {}
        self.capacity = concurrent + queued
        self.timeout = timeout
        self._maintenance_lock = asyncio.Lock()
        self._maintenance_task = None

    async def ask(self, owner, request_id, spec):
        async with self._admission:
            # Existing requests must remain replayable even when new-work slots are full.
            existing = await self.repository.turns.find_one({"owner": owner, "request_id": request_id})
            if existing is None and len(self.tasks) >= self.capacity:
                raise OverflowError("Research queue is full")
            if (existing is None and not spec.get("price_only") and self.model is not None
                    and hasattr(self.model, "settings_for")):
                spec = {**spec, "ai_settings": await self.model.settings_for(owner)}
            elif existing is not None and "ai_settings" in existing.get("spec", {}):
                spec = {**spec, "ai_settings": existing["spec"]["ai_settings"]}
            doc, created = await self.repository.admit(owner, request_id, spec)
            if created:
                task = asyncio.create_task(self._work(owner, doc["turn_id"], spec))
                self.tasks[doc["turn_id"]] = task
                task.add_done_callback(lambda completed, key=doc["turn_id"]: self.tasks.pop(key, None))
            return doc

    async def _work(self, owner, turn_id, spec):
        try:
            async with asyncio.timeout(self.timeout):
                async with self._slots:
                    if not await self.repository.progress(owner, turn_id, "Reading available market observations"):
                        return
                    snapshots = []
                    for ticker in spec["tickers"]:
                        if not await self.repository.progress(owner, turn_id, f"Checking {ticker} coverage"):
                            return
                        screen = (
                            spec["screen"]
                            if not spec["context_conflict"] and spec["screen"].get("ticker") == ticker
                            else {}
                        )
                        selected_expiry = (
                            spec["question_scope"]["selected_expiry"]
                            if spec.get("question_scope") is not None
                            else screen.get("selectedExpiry")
                        )
                        snapshots.append(
                            await self.reads.snapshot(
                                ticker,
                                spec["horizon"],
                                selected_expiry=selected_expiry,
                                screen=screen,
                                **({"price_only": True} if spec.get("price_only") else {}),
                            )
                        )
                        if not spec.get("price_only"):
                            await self.repository.save_anchor(owner, snapshots[-1])
                            await self.repository.watch_observations(owner, ticker, spec["horizon"], selected_expiry)
                    answer = deterministic_answer(snapshots, spec)
                    if re.search(
                        r"\b(?:changed?|since|earlier|previously|previous|prior|yesterday|closing|last close)\b",
                        spec["question"],
                        re.IGNORECASE,
                    ):
                        answer["history_closing_only"] = bool(
                            re.search(r"\b(?:closing|close|yesterday)\b", spec["question"], re.IGNORECASE)
                        )
                        answer["history_previous_session"] = bool(
                            re.search(r"\b(?:yesterday|previous|prior)\b", spec["question"], re.IGNORECASE)
                        )
                        for snapshot in snapshots:
                            more, note = await history_facts(
                                self.repository,
                                owner,
                                snapshot,
                                closing_only=answer["history_closing_only"],
                                previous_session=answer["history_previous_session"],
                            )
                            existing = {item["id"] for item in answer["facts"]}
                            answer["facts"].extend(item for item in more if item["id"] not in existing)
                            text = note
                            if more:
                                change = more[-1]
                                text += f". Price change: {change['value']:+,.4g} {change['unit']}."
                            else:
                                answer["gaps"].append(note)
                            merge_history_section(answer, snapshot["ticker"], text, more, snapshot.get("horizon", "all"))
                    if (
                        not spec.get("price_only")
                        and self.model is not None
                        and any(f["metric"] == "Underlying price" for f in answer["facts"])
                    ):
                        try:
                            await self._interpret(owner, turn_id, spec, answer, snapshots)
                        except Exception:
                            answer["model_status"] = "Interpretation unavailable; showing saved market readings"
                    await self.repository.finish(owner, turn_id, "completed", answer=answer)
        except asyncio.CancelledError:
            # Cancellation is saved first by cancel(); shutdown is interrupted.
            await self.repository.finish(owner, turn_id, "interrupted", error="Work stopped; no automatic retry")
            raise
        except Exception:
            # Never publish exception text containing provider URLs or secrets.
            # Persistent running state is recovered as interrupted at startup.
            with contextlib.suppress(Exception):
                await self.repository.finish(owner, turn_id, "failed", error="Research could not finish or be saved")

    async def _interpret(self, owner, turn_id, spec, answer, snapshots):
        inspected = False
        repaired = False
        history_note = None
        answer["usage"] = []
        for _ in range(1 if getattr(self.model, "single_attempt", False) else 3):
            if not await self.repository.progress(
                owner, turn_id, "Checking an interpretation against the saved evidence"
            ):
                return
            result = await self.model.once(
                spec["question"],
                answer["facts"],
                turn_id,
                allow_inspect=not inspected,
                history_note=history_note,
                repair=repaired,
                **({"owner": owner, "settings": spec["ai_settings"]} if "ai_settings" in spec else {}),
            )
            answer["usage"].append(
                {
                    k: result[k]
                    for k in (
                        "reservation_id",
                        "generation_id",
                        "accounting",
                        "actual_cost",
                        "model",
                        "provider",
                        "policy_version",
                        "effort", "speed", "tokens",
                    )
                    if k in result
                }
            )
            if result["status"] == "ok":
                if result["name"] == "inspect_history":
                    requested = result["data"]
                    if (
                        inspected
                        or not isinstance(requested, dict)
                        or set(requested) != {"ticker"}
                        or requested["ticker"] not in spec["tickers"]
                    ):
                        result = {"status": "invalid", "reason": "Model requested unsupported history"}
                    else:
                        inspected = True
                        snapshot = next(s for s in snapshots if s["ticker"] == requested["ticker"])
                        more, history_note = await history_facts(
                            self.repository,
                            owner,
                            snapshot,
                            closing_only=answer.get("history_closing_only", False),
                            previous_session=answer.get("history_previous_session", False),
                        )
                        existing = {f["id"] for f in answer["facts"]}
                        answer["facts"].extend(f for f in more if f["id"] not in existing)
                        text = history_note
                        if more:
                            change = more[-1]
                            text += f". Price change: {change['value']:+,.4g} {change['unit']}."
                        if not more:
                            answer["gaps"].append(history_note)
                        merge_history_section(answer, snapshot["ticker"], text, more, snapshot.get("horizon", "all"))
                        continue
                else:
                    try:
                        ledger = {f["id"]: f for f in answer["facts"]}
                        checked = validate_model_answer(result["data"], ledger)
                        answer["model_sections"] = [
                            {
                                "name": section["name"],
                                "fact_ids": section["fact_ids"],
                                "text": INTERPRETATIONS[section["interpretation"]],
                            }
                            for section in checked["sections"]
                        ]
                        answer["mode"] = "model-assisted"
                        answer["model_relationships"] = checked["relationship_text"]
                        answer["model_explanations"] = checked["explanations"]
                        answer["model_status"] = (
                            "Checked interpretation; quantitative readings remain the saved evidence"
                        )
                        return
                    except (ValueError, TypeError, KeyError):
                        result = {"status": "invalid", "reason": "Model interpretation was not supported by the facts"}
            answer["model_status"] = result.get("reason", "Model interpretation unavailable")
            if result["status"] != "invalid" or repaired:
                return
            repaired = True
        # Preserve the actual refusal reason on single-attempt providers. A
        # rejected comparison is not a quota exhaustion or transport failure.
        answer.setdefault("model_status", "Model work limit reached; showing the deterministic reading")

    async def cancel(self, owner, turn_id):
        won = await self.repository.finish(owner, turn_id, "cancelled", error="Cancelled by you")
        if won and turn_id in self.tasks:
            self.tasks[turn_id].cancel()
        return await self.repository.read(owner, turn_id)

    async def close(self):
        tasks = list(self.tasks.values())
        if self._maintenance_task is not None:
            tasks.append(self._maintenance_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def schedule_maintenance(self):
        """One tracked task keeps slow reconciliation off the market scheduler."""
        if self._maintenance_task is None or self._maintenance_task.done():
            self._maintenance_task = asyncio.create_task(self._safe_maintenance())
        return self._maintenance_task

    async def _safe_maintenance(self):
        try:
            await self.maintenance()
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Research maintenance failed")

    async def maintenance(self, now=None):
        """Existing app scheduler calls this; cache-only and idle-priority."""
        if self._maintenance_lock.locked():
            return
        async with self._maintenance_lock:
            async with asyncio.timeout(50):
                await self.repository.project_claims()
                await self.repository.collect_claim_paths(now or datetime.now(UTC))
                if self.model is not None:
                    await self.model.reconcile()
                now = now or datetime.now(UTC)
                window = horizon_window("all", now=now)
                # After-close checks preserve actual producer time; they never
                # label a stale intraday cache as a closing observation.
                if (
                    not window["is_session"]
                    or window["session_state"] == "pre-open"
                    or now > datetime.fromisoformat(window["session_close"]) + timedelta(hours=1)
                ):
                    return
                for job in await self.repository.due_jobs(now):
                    if self.tasks:
                        break
                    if not await self.repository.claim_job(job["_id"], now):
                        continue
                    error = None
                    try:
                        snapshot = await self.reads.snapshot(
                            job["ticker"], job["horizon"], selected_expiry=job.get("selected_expiry"), now=now
                        )
                        await self.repository.save_anchor(job["owner"], snapshot)
                    except Exception:
                        error = "Available observation could not be collected; no backfill was invented"
                    await self.repository.finish_job(job["_id"], now, error)
