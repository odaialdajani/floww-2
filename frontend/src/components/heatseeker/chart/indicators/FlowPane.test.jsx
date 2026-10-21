// B20 flow bucket tests: synthetic only; sides are feed-classified only.
import React from "react";
import { render, screen } from "@testing-library/react";
import FlowPane, {
  bucketHash,
  bucketUnits,
  bucketize,
  groupLegs,
} from "./FlowPane";

test("call premium sums up, put premium renders down, unknown stays explicit", () => {
  const trades = [
    { side: "call", premium: 100 },
    { side: "put", premium: 40 },
    { side: "?", premium: 5 },
  ];
  const buckets = bucketize(trades);
  expect(buckets.call_premium).toBe(100);
  expect(buckets.put_premium).toBe(-40);
  expect(buckets.unknown).toBe(1);
  expect(buckets.count).toBe(3);
  expect(buckets.top[0].premium).toBe(100);
  render(<FlowPane trades={trades} barId="bar-1" windowKey="1m" />);
  expect(screen.getByTestId("flow-call-premium")).toHaveTextContent("100");
  expect(screen.getByTestId("flow-put-premium")).toHaveTextContent("-40");
  expect(screen.getByTestId("flow-unknown")).toHaveTextContent("Unknown 1 of 3");
  expect(screen.getByTestId("flow-unknown-note")).toHaveTextContent("never guesses a side from an ask tick");
});

test("equal filter and cursor hash makes drilldown identical to totals", () => {
  const trades = [{ side: "call", premium: 100 }, { side: "put", premium: 40 }, { side: "?", premium: 5 }];
  const hash = bucketHash("bar-1", "1m", { min: 0 });
  const { rerender } = render(
    <FlowPane trades={trades} barId="bar-1" windowKey="1m" filters={{ min: 0 }} cursorHash={hash} />
  );
  expect(screen.getByTestId("flow-drilldown-call").textContent).toBe(screen.getByTestId("flow-call-premium").textContent);
  expect(screen.getByTestId("flow-drilldown-put").textContent).toBe(screen.getByTestId("flow-put-premium").textContent);
  expect(screen.getByTestId("flow-drilldown-unknown").textContent).toContain("Unknown 1 of 3");
  // a different cursor bucket is not merged into the totals bucket
  rerender(<FlowPane trades={trades} barId="bar-1" windowKey="1m" filters={{ min: 0 }} cursorHash={bucketHash("bar-2", "1m", { min: 0 })} />);
  expect(screen.getByTestId("flow-drilldown-scope-note")).toHaveTextContent("not merged");
  // deterministic: same inputs produce the same identity, different inputs differ
  expect(bucketHash("bar-1", "1m", { x: 1 })).toBe(bucketHash("bar-1", "1m", { x: 1 }));
  expect(bucketHash("bar-1", "1m", { x: 1 })).not.toBe(bucketHash("bar-1", "1m", { x: 2 }));
  expect(bucketHash("bar-1", "1m", {}, "server-echo")).toBe("server-echo");
});

test("unknown classifications stay out of call and put numbers", () => {
  const buckets = bucketize([
    { side: "CALL", premium: 50 },   // case is not the classified tag
    { side: "call", premium: 30 },
    { side: "put", premium: 20 },
    { premium: 10 },                  // no side at all
    null,
  ]);
  expect(buckets.call_premium).toBe(30);
  expect(buckets.put_premium).toBe(-20);
  expect(buckets.unknown).toBe(3);
  const { tickets, singles } = groupLegs([{ side: "call", premium: 30 }, { premium: 10 }]);
  expect(tickets).toHaveLength(0);
  expect(singles).toHaveLength(2);
});

test("economic multi-leg grouping keeps mixed tickets explicit", () => {
  const trades = [
    { side: "call", premium: 100, group_id: "t1" },
    { side: "put", premium: 40, group_id: "t1" },
    { side: "put", premium: 20, group_id: "t2" },
  ];
  const { tickets, singles } = groupLegs(trades);
  expect(tickets).toHaveLength(2);
  const mixed = tickets.find((t) => t.group_id === "t1");
  expect(mixed.side).toBe("mixed");
  expect(mixed.leg_count).toBe(2);
  expect(mixed.net_premium).toBe(60); // +100 call leg, -40 put leg
  const sameSide = tickets.find((t) => t.group_id === "t2");
  expect(sameSide.side).toBe("put");
  expect(singles).toHaveLength(0);
  // a same-side ticket acts as one economic unit in the buckets
  const units = bucketUnits(trades);
  const buckets = bucketize(units);
  expect(buckets.unknown).toBe(1);      // the mixed ticket, explicitly
  expect(buckets.put_premium).toBe(-20);
  expect(buckets.count).toBe(2);
});
