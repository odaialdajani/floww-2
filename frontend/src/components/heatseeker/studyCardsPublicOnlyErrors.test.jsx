/**
 * @jest-environment jsdom
 *
 * Regression coverage for the Public-only study refusal reporting bug.
 *
 * The backend mounts several older study routes behind
 * `backend/routes/steal_three.py::_require_legacy_market_data()`. When the
 * backend runs on the Public-only feed (FLOWW_MARKET_DATA_PROVIDER=public)
 * those routes answer HTTP 503 with a typed refusal body:
 *
 *   {"error": {"status": "unavailable",
 *              "reason": "PUBLIC_ONLY_STUDY_UNAVAILABLE",
 *              "message": "This study has no Public-only producer; ..."}}
 *
 * Seven study cards collapsed every failure into "backend unreachable"
 * (and two of them told the user to start a sidecar), so a deliberate,
 * reachable refusal masqueraded as a dead backend. These tests pin the
 * honest three-way contract the cards must honor:
 *
 *   1. typed refusal  → "<Card> · study unavailable" + the typed reason,
 *                       never "unreachable", never a start-hint.
 *   2. untyped HTTP error → "<Card> · server error" + the status code.
 *   3. network failure   → "<Card> · offline" + "unreachable" (and the
 *                       start-hint is allowed only here).
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import DualGEXBadge from "./DualGEXBadge";
import IVMidBadge from "./IVMidBadge";
import MaxPainBadge from "./MaxPainBadge";
import StrikeConeBadge from "./StrikeConeBadge";
import OpportunityBadge from "./OpportunityBadge";
import NewsBadge from "./NewsBadge";
import RndDensityPanel from "./RndDensityPanel";

const TYPED_REFUSAL_BODY = {
  error: {
    status: "unavailable",
    reason: "PUBLIC_ONLY_STUDY_UNAVAILABLE",
    message: "This study has no Public-only producer; alternate sources are disabled",
  },
  status_code: 503,
  path: "/api/study/SPY",
};

const CARDS = [
  ["DualGEXBadge", "Dual-GEX", (ticker) => <DualGEXBadge ticker={ticker} />],
  ["IVMidBadge", "IV-Mid", (ticker) => <IVMidBadge ticker={ticker} width={6} />],
  ["MaxPainBadge", "Max-Pain", (ticker) => <MaxPainBadge ticker={ticker} />],
  ["StrikeConeBadge", "Strike Cone", (ticker) => <StrikeConeBadge ticker={ticker} expiries={1} />],
  ["OpportunityBadge", "Opportunity", (ticker) => <OpportunityBadge ticker={ticker} />],
  ["NewsBadge", "Catalyst Pulse", (ticker) => <NewsBadge ticker={ticker} days={14} />],
  ["RndDensityPanel", "Rnd Density", (ticker) => <RndDensityPanel ticker={ticker} expiries={1} />],
];

function mockFetchWith(responder) {
  global.fetch = jest.fn(responder);
}

describe.each(CARDS)("%s reports study failures honestly", (name, title, mount) => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("a typed Public-only refusal is a study limitation, not an outage", async () => {
    mockFetchWith(() =>
      Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve(TYPED_REFUSAL_BODY) })
    );
    render(mount("SPY"));
    expect(await screen.findByText(`${title} · study unavailable`)).toBeInTheDocument();
    expect(screen.getByText("PUBLIC_ONLY_STUDY_UNAVAILABLE")).toBeInTheDocument();
    // The backend answered — calling it unreachable is the original bug.
    expect(screen.queryByText(/unreachable/i)).not.toBeInTheDocument();
    // A deliberate refusal must not prompt the user to start a backend/sidecar.
    expect(screen.queryByText(/steal_three_server/)).not.toBeInTheDocument();
    expect(screen.queryByText(/start :8000/)).not.toBeInTheDocument();
  });

  test("an untyped HTTP error is a server error, not an outage", async () => {
    mockFetchWith(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: "Internal error" }) })
    );
    render(mount("SPY"));
    expect(await screen.findByText(`${title} · server error`)).toBeInTheDocument();
    expect(screen.getByText(/returned HTTP 500/)).toBeInTheDocument();
    expect(screen.queryByText(/unreachable/i)).not.toBeInTheDocument();
  });

  test("a genuine network failure still reports the backend unreachable", async () => {
    mockFetchWith(() => Promise.reject(new TypeError("Failed to fetch")));
    render(mount("SPY"));
    expect(await screen.findByText(`${title} · offline`)).toBeInTheDocument();
    expect(screen.getByText(/unreachable/)).toBeInTheDocument();
  });
});
