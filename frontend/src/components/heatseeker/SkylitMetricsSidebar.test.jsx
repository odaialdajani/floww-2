/** @jest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import SkylitMetricsSidebar from './SkylitMetricsSidebar';

const BASE = {
  ticker: 'SPY',
  exposure_basis: 'OI',
  strikes: [{ strike: 500, gex: 1000000 }],
  nodes: { king: { strike: 500, gex: 1000000 }, floors: [], ceilings: [] },
  metrics: {
    grids: {
      delta: {
        grid: { '2030-01-15': { 500: 250000 } },
        exposure_basis: 'OI_DELTA_WEIGHTED',
      },
    },
  },
};

test('R6-1: sidebar follows the active metric', () => {
  const { unmount } = render(<SkylitMetricsSidebar data={BASE} spot={500} metric="raw" />);
  expect(screen.getByText('Key Levels · GEX · OI')).toBeInTheDocument();
  unmount();
  render(<SkylitMetricsSidebar data={BASE} spot={500} metric="delta" />);
  expect(screen.getByText('Key Levels · GEX · delta · OI_DELTA_WEIGHTED')).toBeInTheDocument();
  // Net 250K renders signed; raw 1M must not leak into the delta summary.
  expect(screen.getByText('+250.0K')).toBeInTheDocument();
});

test('R6-1: missing metric surface renders unavailable, never raw totals', () => {
  render(<SkylitMetricsSidebar data={{ ...BASE, metrics: { grids: {} } }} spot={500} metric="delta" />);
  expect(screen.getByTestId('skylit-sidebar-unavailable')).toBeInTheDocument();
  expect(screen.queryByText('+1.0M')).toBeNull();
});

test('R8: vex view labels structural anchors honestly, never VEX values', () => {
  const data = {
    exposure_basis: 'OI',
    net_gex_total: 1000,
    strikes: [{ strike: 500, gex: 1000 }],
    nodes: { total_gex: 1000, king: { strike: 500 }, floors: [], ceilings: [] },
    grid: { expiries: ['2030-01-15'], strikes: [500], grid: {},
      vex_grid: { '2030-01-15': { 500: 25 } } },
  };
  render(<SkylitMetricsSidebar data={data} spot={500} viewMode="vex" metric="raw" />);
  expect(screen.getByText('Key Levels · GEX structural · OI')).toBeInTheDocument();
});

test("missing readings do not claim a neutral gamma regime", () => {
  const view = render(<SkylitMetricsSidebar />);
  expect(screen.getByText("Gamma reading unavailable")).toBeInTheDocument();
  expect(screen.queryByText("Neutral γ")).not.toBeInTheDocument();
  view.rerender(<SkylitMetricsSidebar regime="neutral" />);
  expect(screen.getByText("Neutral γ")).toBeInTheDocument();
});

function metricValue(label){return screen.getByText(label,{selector:".skylit-metric-label"}).parentElement.querySelector(".skylit-metric-value").textContent;}
test("missing historical structure shows unknown counts, not recorded zeros",()=>{
 render(<SkylitMetricsSidebar data={{replay:true,structure_status:"unknown",nodes:null,strikes:[{strike:100,gex:null}]}}/>);
 expect(metricValue("Floors")).toBe("Unknown");expect(metricValue("Ceilings")).toBe("Unknown");expect(metricValue("Gatekeepers")).toBe("Unknown");expect(metricValue("|GEX|")).toBe("—");expect(metricValue("Net GEX")).toBe("—");
});
test("observed empty structure and live known zero totals retain actual zeros",()=>{
 const data={nodes:{king:{strike:100,gex:0},floors:[],ceilings:[],gatekeepers:[],polarity_level:0,total_gex:0,regime:"neutral"},strikes:[{strike:100,gex:0}],net_gex_total:0,total_abs_gex:0,gamma_flip:{gamma_flip:0},gex_regime:"neutral"};
 const view=render(<SkylitMetricsSidebar data={data}/>);expect(metricValue("Floors")).toBe("0");expect(metricValue("Ceilings")).toBe("0");expect(metricValue("Gatekeepers")).toBe("0");expect(metricValue("|GEX|")).toBe("0");expect(metricValue("Net GEX")).toBe("+0");expect(metricValue("Flip Point")).toBe("$0.0");expect(screen.getByText("Neutral γ")).toBeInTheDocument();
 view.rerender(<SkylitMetricsSidebar data={{...data,replay:true,structure_status:"complete"}}/>);expect(metricValue("Gatekeepers")).toBe("0");expect(metricValue("Net GEX")).toBe("+0");
});

test("partly recorded node groups preserve known counts without filling absent groups",()=>{
 render(<SkylitMetricsSidebar data={{replay:true,structure_status:"partial",nodes:{floors:[],ceilings:null,gatekeepers:undefined}}}/>);
 expect(metricValue("Floors")).toBe("0");expect(metricValue("Ceilings")).toBe("Unknown");expect(metricValue("Gatekeepers")).toBe("Unknown");
 expect(screen.getByRole("status")).toHaveTextContent("unavailable for this saved view");
});

const overlayData=section=>({...BASE,grid:{expiries:["2030-01-15"],strikes:[500]},metrics:{grids:{delta:section}}});
test.each([null,{}, {"2030-01-15":null},{"2030-01-15":{}},{"2030-01-15":[]},{"2030-01-15":{"500":null}},{"2030-01-15":{"500":false}},{"2030-01-15":{"500":"0"}},{"2030-01-15":{"500":NaN}},{"2030-01-15":{"500":Infinity}}])("missing or malformed overlay cannot claim either total: %j",grid=>{
 render(<SkylitMetricsSidebar data={overlayData({grid})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-unavailable")).toBeInTheDocument();expect(metricValue("STRONGEST WALL")).toBe("$500.0");
});
test("a partly missing column or included cell withholds complete totals",()=>{
 const grid={"2030-01-15":{"500":10,"501":null}};const data=overlayData({grid,expiries:["2030-01-15"],strikes:[500,501]});
 const view=render(<SkylitMetricsSidebar data={data} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-partial")).toHaveTextContent("Metric incomplete");
 view.rerender(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":10}},expiries:["2030-01-15","2030-01-22"],strikes:[500]})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-partial")).toBeInTheDocument();
});
test("finite signed overlays and genuine measured all-zero grids stay known",()=>{
 const view=render(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":0}}})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("+0");expect(metricValue("|GEX|")).toBe("0");expect(screen.queryByTestId("skylit-sidebar-unavailable")).toBeNull();expect(screen.queryByTestId("skylit-sidebar-partial")).toBeNull();
 view.rerender(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":10,"501":-10}}})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("+0");expect(metricValue("|GEX|")).toBe("20");
});

test("valid sparse overlay does not invent a full rectangle or lose its signed totals",()=>{
 render(<SkylitMetricsSidebar data={overlayData({expiries:["2030-01-15","2030-01-22"],strikes:[500,501],grid:{"2030-01-15":{"500":10},"2030-01-22":{"501":-4}}})} metric="delta"/>);
 expect(metricValue("Net GEX")).toBe("+6");expect(metricValue("|GEX|")).toBe("14");expect(screen.queryByTestId("skylit-sidebar-partial")).toBeNull();expect(metricValue("STRONGEST WALL")).toBe("$500.0");
});
test("reported excluded inputs and a missing declared strike withhold complete aggregates",()=>{
 const view=render(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":0}},missing_delta:1})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-partial")).toBeInTheDocument();
 view.rerender(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":0}},strikes:[500,501]})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-partial")).toBeInTheDocument();
});
test("an overflowing finite-cell sum is unavailable rather than infinite exposure",()=>{
 render(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":Number.MAX_VALUE,"501":Number.MAX_VALUE}}})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-unavailable")).toBeInTheDocument();
});

test.each(["cell_missing_delta","cell_invalid_delta"])("per-cell exclusions prevent a subset zero from becoming a complete total: %s",key=>{
 render(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":0}},[key]:{"2030-01-15":{"500":1}}})} metric="delta"/>);
 expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-partial")).toBeInTheDocument();
});

test("zero exclusion counts and equivalent decimal strike keys keep real measured zero",()=>{
 render(<SkylitMetricsSidebar data={overlayData({expiries:["2030-01-15"],strikes:[500],grid:{"2030-01-15":{"500.0":0}},cell_missing_delta:{"2030-01-15":{"500.0":0}},cell_invalid_delta:{}})} metric="delta"/>);
 expect(metricValue("Net GEX")).toBe("+0");expect(metricValue("|GEX|")).toBe("0");expect(screen.queryByTestId("skylit-sidebar-partial")).toBeNull();
});

test("explicitly absent usable observations cannot make a zero-looking grid measured",()=>{
 const view=render(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":0}},usable:0})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("—");expect(metricValue("|GEX|")).toBe("—");expect(screen.getByTestId("skylit-sidebar-unavailable")).toBeInTheDocument();
 view.rerender(<SkylitMetricsSidebar data={overlayData({grid:{"2030-01-15":{"500":0}},usable:1})} metric="delta"/>);expect(metricValue("Net GEX")).toBe("+0");expect(metricValue("|GEX|")).toBe("0");
});
