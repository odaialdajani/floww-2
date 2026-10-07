/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent, act, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import axios from "axios";
import OptionsDashboard from "./SkylitDashboard";
// These contracts exercise the options desk; the stock route now opens price first.
const SkylitDashboard = props => <OptionsDashboard defaultStudy="options" {...props}/>;

jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock("./SkylitTickerBar", () => ({ __esModule: true, default: () => null, TICKER_SETS: { popular: ["SPY", "QQQ"] } }));
jest.mock("./StockDirectory", () => () => null);
jest.mock("./PriceNodeHistory", () => () => null);
jest.mock("./ExposureStrip", () => () => null);
jest.mock("../flowseeker/AlertEngineStrip", () => () => null);
jest.mock("./SkylitMetricsSidebar", () => () => null);
const E1 = "2031-01-17", E2 = "2031-01-24";
const fixture = () => ({ ticker: "SPY", spot: 100.25, asof: "2031-01-16T15:00:00Z", snapshotId: "r11-canvas",
  strikes: [{ strike: 101 }, { strike: 100 }, { strike: 99 }],
  grid: { expiries: [E1, E2], strikes: [101, 100, 99], grid: { [E1]: { 101: -20000, 100: 100000, 99: 0 }, [E2]: { 100: 20000 } },
    vex_grid: { [E1]: { 101: -300, 100: 400 } }, charm_grid: { [E1]: { 101: 50, 100: -80 } } },
  metrics: { walls: [{ wall_id: "w", low: 100, high: 101, mid: 100.5, members: [100, 101], gross: 140000, net: 100000 }],
    grids: { delta: { expiries: [E1, E2], strikes: [101, 100, 99], grid: { [E1]: { 101: -10000, 100: 50000 }, [E2]: { 100: 10000 } } },
      session_delta_volume: { expiries: [E1], strikes: [101, 100, 99], grid: { [E1]: { 100: 5000 } } } },
    surface_coverage: { raw: { status: "ok" }, delta: { status: "ok" }, session_delta_volume: { status: "partial" }, window: { status: "unavailable", reason: "NO_BASELINE" } } },
  quality: { state: "usable", setupEligible: false, reasonCodes: ["PRICE_HISTORY_MISSING"] } });
beforeEach(() => { sessionStorage.clear(); axios.get.mockResolvedValue({ data: { snapshots: [], decisions: [] } }); });
const mount = async () => { await act(async () => render(<SkylitDashboard ticker="SPY" spot={100.25} data={fixture()} />)); };

test("Matrix + Profile is the default and local view changes preserve the owning selection",async()=>{
 let view;
 await act(async()=>{view=render(<SkylitDashboard ticker="SPY" spot={100.25} data={fixture()} localView="profile"/>);});
 expect(screen.getByLabelText("Canvas layout")).toHaveValue("profile");
 fireEvent.click(screen.getByRole("gridcell",{name:/^100 by 2031-01-17,/}));
 await act(async()=>view.rerender(<SkylitDashboard ticker="SPY" spot={100.25} data={fixture()} localView="grid"/>));
 expect(screen.getByLabelText("Canvas layout")).toHaveValue("focus");
 expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("100000.0");
});

test("profile layout sums the exact loaded scope, aligns selection, and does not fetch a new exposure", async () => {
  await mount();
  const calls = axios.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText("Canvas layout"), { target: { value: "profile" } });
  const header = screen.getByTestId("skylit-profile-header");
  expect(header).toHaveTextContent("All loaded · 2 expiries");
  const row = screen.getAllByTestId("skylit-profile-cell").find(e => e.dataset.strike === "100");
  expect(row.querySelector(".trin-prof").title).toContain("Raw $120.0K");
  fireEvent.click(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ }));
  expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("100000.0");
  expect(row.parentElement).toHaveClass("trin-row-selected");
  expect(axios.get.mock.calls.length).toBe(calls);
});

test("calendar shows only loaded dates and keeps basis switching on the same snapshot", async () => {
  await mount();
  const calls = axios.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText("Canvas layout"), { target: { value: "calendar" } });
  expect(screen.getByTestId("skylit-loaded-scope")).toHaveTextContent(`${E1}, ${E2}`);
  fireEvent.change(screen.getByTestId("skylit-basis-select"), { target: { value: "session_delta_volume" } });
  expect(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ })).toHaveTextContent("$5.0K");
  expect(screen.getByTestId("skylit-grid-basis")).toHaveTextContent("VOLUME");
  expect(axios.get.mock.calls.length).toBe(calls);
});

test("multi-map uses one packet with disclosed independent metric scales and one active selection", async () => {
  await mount();
  const calls = axios.get.mock.calls.length;
  fireEvent.change(screen.getByLabelText("Canvas layout"), { target: { value: "multi" } });
  expect(screen.getAllByRole("grid")).toHaveLength(4);
  const vex = screen.getByTestId("skylit-pane-vex");
  fireEvent.click(within(vex).getByRole("gridcell", { name: /^100 by 2031-01-17,/ }));
  expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("400.0");
  expect(screen.getByTestId("skylit-selected-cell").title).toContain("VEX");
  expect(axios.get.mock.calls.length).toBe(calls);
});

test("paused-follow selection and research scope stay on the displayed rows through spot polling", async () => {
  const data = fixture();
  data.grid.strikes = Array.from({ length: 100 }, (_, i) => i + 50);
  data.strikes = data.grid.strikes.map(strike => ({ strike }));
  data.grid.grid[E1] = Object.fromEntries(data.grid.strikes.map(s => [s, 1000]));
  let mounted;
  await act(async () => { mounted = render(<SkylitDashboard ticker="SPY" spot={100.25} data={data} />); });
  fireEvent.scroll(document.querySelector(".skylit-heatmap-container"));
  fireEvent.click(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ }));
  await act(async () => { mounted.rerender(<SkylitDashboard ticker="SPY" spot={149} data={data} />); });
  expect(screen.getByTestId("skylit-selected-cell")).toHaveTextContent("1000.0");
  expect(screen.getByRole("gridcell", { name: /^100 by 2031-01-17,/ })).toBeInTheDocument();
});


test("pruning an unavailable cell must not reopen a dismissed inspector", async () => {
  await mount();
  fireEvent.click(screen.getByRole("gridcell", { name: /^101 by 2031-01-17,/ }));
  expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("skylit-drawer-close"));
  expect(screen.queryByTestId("skylit-inspector-drawer")).not.toBeInTheDocument();
  // Same pruning seam as a responsive row-window change: this pane no longer
  // has the selected cell, but the structural wall remains selected.
  await act(async () => { fireEvent.change(screen.getByTestId("skylit-basis-select"), { target: { value: "session_delta_volume" } }); });
  expect(screen.queryByTestId("skylit-inspector-drawer")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(screen.getByTestId("skylit-inspector-drawer")).toBeInTheDocument();
});

test("manual scrolling pauses follow spot; resume is explicit", async () => {
  await mount();
  fireEvent.scroll(document.querySelector(".skylit-heatmap-container"));
  expect(screen.getByTestId("skylit-follow-spot-toggle")).toHaveTextContent("Resume spot");
  fireEvent.click(screen.getByTestId("skylit-follow-spot-toggle"));
  expect(screen.getByTestId("skylit-follow-spot-toggle")).toHaveTextContent("Follow spot");
});


test('opening the inspector keeps an available edge cell selected, while a later external resize still prunes it',async()=>{
 const priorObserver=global.ResizeObserver;
 const priorHeight=Object.getOwnPropertyDescriptor(HTMLElement.prototype,'clientHeight');
 const observers=[];let externalHeight=null,view;const onCellClick=jest.fn();
 global.ResizeObserver=class{constructor(callback){this.callback=callback;observers.push(this);}observe(box){this.box=box;}disconnect(){}};
 Object.defineProperty(HTMLElement.prototype,'clientHeight',{configurable:true,get(){
  if(!this.classList.contains('skylit-main-area'))return 0;
  return externalHeight ?? ((document.querySelector('[data-testid="skylit-inspector-drawer"]')?13:18)*23+64);
 }});
 try{
  const data=fixture();data.grid.strikes=Array.from({length:100},(_,i)=>i+50);data.strikes=data.grid.strikes.map(strike=>({strike}));
  data.grid.grid[E1]=Object.fromEntries(data.grid.strikes.map(strike=>[strike,1000]));
  await act(async()=>{view=render(<SkylitDashboard ticker="SPY" spot={100.25} data={data} onCellClick={onCellClick}/>);});
  const cell=screen.getAllByRole('gridcell')[0];const strike=cell.getAttribute('aria-label').split(' by ')[0];
  fireEvent.click(cell);expect(screen.getByTestId('skylit-selected-cell')).toHaveTextContent(strike+' · '+E1+' · 1000.0');
  expect(screen.getByTestId('skylit-inspector-drawer')).toBeInTheDocument();
  const observer=observers.find(item=>item.box===document.querySelector('.skylit-main-area'));
  act(()=>observer.callback());
  expect(screen.getByTestId('skylit-selected-cell')).toHaveTextContent(strike+' · '+E1+' · 1000.0');
  expect(screen.getByTestId('skylit-inspector-drawer')).toBeInTheDocument();expect(onCellClick).not.toHaveBeenCalled();
  externalHeight=10*23+64;act(()=>observer.callback());
  expect(screen.queryByTestId('skylit-selected-cell')).toBeNull();expect(screen.queryByTestId('skylit-inspector-drawer')).toBeNull();expect(onCellClick).not.toHaveBeenCalled();
 }finally{
  view?.unmount();if(priorObserver===undefined)delete global.ResizeObserver;else global.ResizeObserver=priorObserver;
  if(priorHeight)Object.defineProperty(HTMLElement.prototype,'clientHeight',priorHeight);else delete HTMLElement.prototype.clientHeight;
 }
});
