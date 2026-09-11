import React from "react";
import {render, screen, within} from "@testing-library/react";
import AgentPanelAnswer from "./AgentPanelAnswer";

test("answer heading uses the saved expiry scope instead of broad request alias",()=>{
 render(<AgentPanelAnswer turn={{ticker:"SPY",horizon:"all",status:"completed",answer:{snapshots:[{ticker:"SPY",window:{start:"2026-09-18",end:"2026-09-18"}}]}}}/>);
 expect(screen.getByRole("heading").textContent).toBe("SPY · 2026-09-18");
});

// Explicitly synthetic chart fixtures; they test display of saved evidence.
const displayScope = `display:${"a".repeat(64)}`;
const mapScope = `map:${"b".repeat(64)}`;
function reading(metric, value, extra = {}) {
  return {id: metric, metric, value, ticker: "SPY", unit: "display gamma units",
    horizon: displayScope, snapshot_id: "saved-map", source: "public_api",
    status: "degraded", event_time: null, ...extra};
}
function saved(extra = []) {
  return {ticker: "SPY", status: "completed", horizon: "all", answer: {
    summary: "Available readings are shown below.", context: {ticker: "SPY"},
    facts: [reading("Displayed strikes", [100, 105, 110], {unit: "USD"}),
      reading("Displayed expiry dates", ["2026-09-14", "2026-09-18"], {unit: "dates"}),
      reading("Displayed net gamma", [4e6, -9e6, 2e6]),
      reading("Displayed cumulative gamma", [4e6, -5e6, -3e6]),
      reading("Displayed total gamma", -3e6),
      reading("Displayed flip", 103.25, {horizon: mapScope, unit: "USD"}), ...extra],
    gaps: ["Displayed map source observation time is unknown"],
    model_explanations: [{id: "ex1", ticker: "SPY", horizon: mapScope, kind: "source_time",
      text: `SPY (scope ${mapScope}): Saving a reading does not establish its market time.`}],
    model_relationships: ["SPY Displayed flip is present in the saved evidence (degraded)."],
    sections: [],
  }};
}

test("saved desktop chart leads with the actual largest bar, total and whole-map flip", () => {
  render(<AgentPanelAnswer turn={saved()}/>);
  const chart = within(screen.getByRole("region", {name: "Saved chart reading"}));
  expect(chart.getByText(/Largest visible bar:.*105.*-9M/)).toBeInTheDocument();
  expect(chart.getByText(/Visible total: -3M/)).toBeInTheDocument();
  expect(chart.getByText(/Whole-chart flip:.*103\.25/)).toBeInTheDocument();
  expect(chart.getByText(/Market observation time is unknown/)).toBeInTheDocument();
  expect(chart.getByText(/not a price target/)).toBeInTheDocument();
  expect(chart.getByText(/3 strikes.*2 expiries/)).toBeInTheDocument();
  expect(screen.queryByText(new RegExp(mapScope))).not.toBeInTheDocument();
});

test("Solstice selected cell keeps exact decimal strike and expiry in a reloaded answer", () => {
  const turn = saved([reading("Selected display cell", 1250000,
    {contract: "2026-09-18:105:gex"})]);
  const {rerender} = render(<AgentPanelAnswer turn={JSON.parse(JSON.stringify(turn))}/>);
  expect(screen.getByText(/Selected cell: SPY.*105.*2026-09-18.*\+1\.25M/)).toBeInTheDocument();
  rerender(<AgentPanelAnswer turn={{...turn, ticker: "QQQ"}}/>);
  expect(screen.queryByRole("region", {name: "Saved chart reading"})).not.toBeInTheDocument();
});

test("missing bars qualify the largest complete bar and withhold a total", () => {
  const turn = saved();
  turn.answer.facts.find(f => f.metric === "Displayed net gamma").value = [4e6, null, 2e6];
  render(<AgentPanelAnswer turn={turn}/>);
  const chart = within(screen.getByRole("region", {name: "Saved chart reading"}));
  expect(chart.getByText(/Largest complete visible bar:.*100.*\+4M/)).toBeInTheDocument();
  expect(chart.queryByText(/Visible total:/)).not.toBeInTheDocument();
  expect(chart.getByText(/Missing bars could change which level is largest/)).toBeInTheDocument();
});

test("bars from another saved map cannot become this chart's largest level", () => {
  const turn = saved();
  turn.answer.facts.find(f => f.metric === "Displayed net gamma").snapshot_id = "different-map";
  render(<AgentPanelAnswer turn={turn}/>);
  const chart = within(screen.getByRole("region", {name: "Saved chart reading"}));
  expect(chart.queryByText(/Largest.*bar:/)).not.toBeInTheDocument();
  expect(chart.queryByText(/Visible total:/)).not.toBeInTheDocument();
});

test("all-zero bars do not invent a strongest level or a bullish conclusion", () => {
  const turn = saved();
  turn.answer.facts.find(f => f.metric === "Displayed net gamma").value = [0, 0, 0];
  turn.answer.facts.find(f => f.metric === "Displayed total gamma").value = 0;
  render(<AgentPanelAnswer turn={turn}/>);
  const chart = within(screen.getByRole("region", {name: "Saved chart reading"}));
  expect(chart.getByText(/All visible bars are zero/)).toBeInTheDocument();
  expect(chart.queryByText(/Largest.*bar:/)).not.toBeInTheDocument();
});

test("a wrong-scope selected cell is not presented as the selected chart reading", () => {
  render(<AgentPanelAnswer turn={saved([reading("Selected display cell", 1234,
    {contract: "2026-10-16:105:gex"})])}/>);
  const chart = within(screen.getByRole("region", {name: "Saved chart reading"}));
  expect(chart.queryByText(/Selected cell:/)).not.toBeInTheDocument();
});

test("chart facts never hide a substantive saved refusal", () => {
  const turn = saved();
  turn.answer.summary = "No order was sent or staged. A calibrated target probability is unavailable.";
  render(<AgentPanelAnswer turn={turn}/>);
  expect(screen.getByText(turn.answer.summary)).toBeVisible();
  expect(screen.getByRole("region", {name: "Saved chart reading"})).toBeVisible();
});

test("equal opposite bars are both identified without inventing one winner", () => {
  const turn = saved();
  turn.answer.facts.find(f => f.metric === "Displayed net gamma").value = [9e6, -9e6, 2e6];
  render(<AgentPanelAnswer turn={turn}/>);
  expect(screen.getByText(/Largest visible bars \(tied\):.*100 at \+9M.*105 at -9M/)).toBeInTheDocument();
});

test.each([["vex", "vanna"], ["charm", "charm"]])("selected %s cell preserves fractional strike and the measure", (metric, label) => {
  const turn = saved([reading("Selected display cell", -1250000,
    {contract: `2026-09-18:105.125:${metric}`, unit: `display ${metric} units`})]);
  turn.answer.facts.find(f => f.metric === "Displayed strikes").value = [100, 105.125, 110];
  render(<AgentPanelAnswer turn={turn}/>);
  expect(screen.getByText(new RegExp(`Selected cell: SPY.*105\\.125.*-1\\.25M displayed ${label}`))).toBeInTheDocument();
});

test("saved answers without chart evidence keep their original answer", () => {
  const turn = saved();
  turn.answer.facts = [];
  turn.answer.summary = "The cached underlying price is unavailable; no paid refresh was started.";
  render(<AgentPanelAnswer turn={turn}/>);
  expect(screen.getByText(turn.answer.summary)).toBeVisible();
  expect(screen.queryByRole("region", {name: "Saved chart reading"})).not.toBeInTheDocument();
});
