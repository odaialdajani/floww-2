/**
 * HeroSection data contract.
 *
 * The hero strip reads King Node / Net GEX / Flip Point. It used to read
 * `data.nodes.find(n => n.type === "king")`, `data.net_gex_total` and
 * `data.flip_zones[0].price` -- none of which the API emits. Against a real
 * /api/data/{ticker} payload every one of them was undefined, so all three
 * tiles rendered the em-dash placeholder while the rest of the page showed
 * real numbers. This pins the actual response shape:
 *
 *   nodes.king.strike        king node strike
 *   metrics.gex_net_v1       net GEX (dollar scale, per default_basis)
 *   gamma_flip.gamma_flip   zero-gamma flip level
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { HeroSection } from "./HeatseekerDashboard";

/** Shape captured from a live /api/data/SPY?expiries=4&mode=day response. */
const realPayload = {
  ticker: "SPY",
  spot: 764.63,
  nodes: {
    king: { strike: 761, gex: -1604527391.14, total_oi: 60437 },
    floors: [{ strike: 728, gex: 1580468.7 }],
    ceilings: [{ strike: 770, gex: 331779025.35 }],
    regime: "negative",
  },
  metrics: { default_basis: "OI", gex_net_v1: -3678612929.168 },
  gamma_flip: { gamma_flip: 725.91, call_wall: 770, put_wall: 761 },
};

function renderHero(overrides = {}) {
  const data = { ...realPayload, ...overrides };
  return render(
    <HeroSection ticker="SPY" spot={data.spot} data={data} dataAge={1} dataFallback={false} />
  );
}

test("hero renders king node, net GEX and flip point from the real API shape", () => {
  renderHero();

  // King node: $761 (from nodes.king.strike)
  expect(screen.getByText("$761")).toBeInTheDocument();
  // Net GEX: -3678.6M (from metrics.gex_net_v1, dollar scale / 1e6)
  expect(screen.getByText(/-3678\.6M/)).toBeInTheDocument();
  // Flip point: $726 (from gamma_flip.gamma_flip)
  expect(screen.getByText("$726")).toBeInTheDocument();

  // No tile may fall back to the placeholder now that data is present.
  expect(screen.queryByText("—")).not.toBeInTheDocument();
});

test("hero still shows the placeholder when the payload genuinely lacks the inputs", () => {
  renderHero({ nodes: {}, metrics: {}, gamma_flip: {} });
  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
});

test("net GEX sign drives the positive/negative styling", () => {
  const { unmount } = renderHero();
  expect(screen.getByText(/-3678\.6M/).className).toContain("text-rose-400");
  unmount();

  renderHero({ metrics: { default_basis: "OI", gex_net_v1: 2500000000 } });
  expect(screen.getByText(/\+2500\.0M/).className).toContain("text-emerald-400");
});
