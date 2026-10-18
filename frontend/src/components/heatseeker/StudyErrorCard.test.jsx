/**
 * @jest-environment jsdom
 *
 * Unit coverage for the shared StudyErrorCard presentation — the three
 * honest verdicts and the hint rule (start-hints only for genuine
 * offline failures, never for deliberate Public-only refusals).
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import StudyErrorCard from "./StudyErrorCard";

const typedRefusal = { reason: "PUBLIC_ONLY_STUDY_UNAVAILABLE", httpStatus: 503, message: "This study has no Public-only producer; alternate sources are disabled" };
const serverError = { httpStatus: 500, message: "HTTP 500" };
const networkError = new TypeError("Failed to fetch");

const hint = <>start :8000, or sidecar: <code>cd backend && python -m services.steal_three_server</code></>;

describe("StudyErrorCard", () => {
  test("typed refusal → study unavailable with the reason, no unreachable, no hint", () => {
    render(<StudyErrorCard title="Wheel" base="http://b" error={typedRefusal} hint={hint} />);
    expect(screen.getByText("Wheel · study unavailable")).toBeInTheDocument();
    expect(screen.getByText("PUBLIC_ONLY_STUDY_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.queryByText(/unreachable/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/steal_three_server/)).not.toBeInTheDocument();
  });

  test("untyped HTTP error → server error with the status", () => {
    render(<StudyErrorCard title="Dual-GEX" base="http://b" error={serverError} />);
    expect(screen.getByText("Dual-GEX · server error")).toBeInTheDocument();
    expect(screen.getByText(/returned HTTP 500/)).toBeInTheDocument();
    expect(screen.queryByText(/unreachable/i)).not.toBeInTheDocument();
  });

  test("network failure → offline, unreachable, and the start hint", () => {
    render(<StudyErrorCard title="Max-Pain" base="http://b" error={networkError} hint={hint} />);
    expect(screen.getByText("Max-Pain · offline")).toBeInTheDocument();
    expect(screen.getByText(/unreachable/)).toBeInTheDocument();
    expect(screen.getByText(/start :8000/)).toBeInTheDocument();
    expect(screen.getByText(/steal_three_server/)).toBeInTheDocument();
  });

  test("no hint rendered for offline when none is supplied", () => {
    render(<StudyErrorCard title="IV-Mid" base="http://b" error={networkError} />);
    expect(screen.getByText("IV-Mid · offline")).toBeInTheDocument();
    expect(screen.queryByText(/start :8000/)).not.toBeInTheDocument();
  });

  test("footer content renders (news card context line)", () => {
    render(
      <StudyErrorCard
        title="Catalyst Pulse"
        base="http://b"
        error={typedRefusal}
        footer={<div className="text-[9px]">SPY · 14d window</div>}
      />
    );
    expect(screen.getByText("SPY · 14d window")).toBeInTheDocument();
  });

  test("test id and class name pass through", () => {
    const { container } = render(
      <StudyErrorCard
        title="Rnd Density"
        base="http://b"
        error={typedRefusal}
        testId="hs-rnd-density"
        className="rnd-offline-card"
      />
    );
    expect(container.querySelector('[data-testid="hs-rnd-density"]')).toBeInTheDocument();
    expect(container.firstChild.className).toContain("rnd-offline-card");
  });
});
