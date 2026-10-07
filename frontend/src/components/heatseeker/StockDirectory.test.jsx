import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import StockDirectory from "./StockDirectory";

jest.mock("axios", () => ({ get: jest.fn() }));

test("browse loads all-provider counts and selecting a result opens that ticker", async () => {
  axios.get.mockResolvedValue({ data: { total: 13135, optionable_total: 8786, matches: 13135,
    complete_provider_catalog: true, has_more: true, instruments: [{ symbol: "BRK.B", options: true }] } });
  const select = jest.fn();
  render(<StockDirectory onSelect={select} />);
  fireEvent.click(screen.getByRole("button", { name: "Browse all stocks" }));
  expect(await screen.findByRole("button", { name: "BRK.B" })).toBeInTheDocument();
  expect(screen.getByText(/13,135 available/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "BRK.B" }));
  expect(select).toHaveBeenCalledWith("BRK.B");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("paging and options search are sent to the full directory", async () => {
  axios.get.mockResolvedValue({ data: { total: 15000, optionable_total: 9000, matches: 15000,
    complete_provider_catalog: true, has_more: true, instruments: [{ symbol: "A", options: true }] } });
  render(<StockDirectory />);
  fireEvent.click(screen.getByRole("button", { name: "Browse all stocks" }));
  fireEvent.click(await screen.findByRole("button", { name: "Next", exact: true }));
  await waitFor(() => expect(axios.get.mock.calls.at(-1)[1].params.page).toBe(2));
  await screen.findByRole("button", { name: "A", exact: true });
  fireEvent.change(screen.getByLabelText("Search full stock list"), { target: { value: "ZZZ" } });
  fireEvent.click(screen.getByLabelText("Options enabled"));
  await waitFor(() => expect(axios.get.mock.calls.at(-1)[1].params).toMatchObject({ page: 1, q: "ZZZ", options_only: true }));
});

test("provider failure is visible and can be retried", async () => {
  axios.get.mockRejectedValue(new Error("offline"));
  render(<StockDirectory />);
  fireEvent.click(screen.getByRole("button", { name: "Browse all stocks" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});


test("a controlled directory has no duplicate trigger and reports selection and close",async()=>{
 axios.get.mockResolvedValue({data:{total:1,optionable_total:1,matches:1,complete_provider_catalog:true,has_more:false,instruments:[{symbol:"BRK.B",options:true}],asof:null}});
 const select=jest.fn(),changed=jest.fn();const view=render(<StockDirectory open={true} onOpenChange={changed} showTrigger={false} onSelect={select}/>);
 expect(screen.queryByRole("button",{name:"Browse all stocks"})).toBeNull();
 fireEvent.click(await screen.findByRole("button",{name:"BRK.B",exact:true}));
 expect(select).toHaveBeenCalledWith("BRK.B");expect(changed).toHaveBeenCalledWith(false);
 view.rerender(<StockDirectory open={false} onOpenChange={changed} showTrigger={false} onSelect={select}/>);expect(screen.queryByRole("dialog")).toBeNull();
});

test("invalid provider rows cannot select an invented stock",async()=>{
 axios.get.mockResolvedValue({data:{total:1,optionable_total:1,matches:1,complete_provider_catalog:true,has_more:false,instruments:[{symbol:"BAD / STOCK",options:true}]}});const select=jest.fn();
 render(<StockDirectory onSelect={select}/>);fireEvent.click(screen.getByRole("button",{name:"Browse all stocks"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");expect(screen.queryByRole("button",{name:"BAD / STOCK"})).toBeNull();expect(select).not.toHaveBeenCalled();
});


test("an unavailable saved directory keeps counts unknown and cannot claim no matches",async()=>{
 axios.get.mockResolvedValue({data:{total:null,optionable_total:null,matches:0,complete_provider_catalog:false,has_more:false,stale:true,instruments:[],asof:null}});
 render(<StockDirectory/>);fireEvent.click(screen.getByRole("button",{name:"Browse all stocks"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("full provider list is unavailable");
 expect(screen.getByRole("dialog")).toHaveTextContent("Stock count unknown");expect(screen.getByRole("dialog")).toHaveTextContent("Options count unknown");
 expect(screen.queryByText("No matching stocks.")).toBeNull();
});


test.each(["2026-02-30T14:00:00Z","2999-01-01T14:00:00Z","2026-10-07T14:00:00"])("an impossible, future or unzoned list date stays unknown: %s",async(asof)=>{
 axios.get.mockResolvedValue({data:{total:1,optionable_total:1,matches:1,complete_provider_catalog:true,has_more:false,instruments:[{symbol:"SPY",options:true}],asof}});
 render(<StockDirectory/>);fireEvent.click(screen.getByRole("button",{name:"Browse all stocks"}));
 await screen.findByRole("button",{name:"SPY",exact:true});expect(screen.getByRole("dialog")).toHaveTextContent("List time unknown");expect(screen.getByRole("dialog")).not.toHaveTextContent("3/2/2026");
});

test.each([undefined,"false",false])("wrong or missing paging details cannot hide the later stock pages: %s",async(has_more)=>{
 axios.get.mockResolvedValue({data:{total:101,optionable_total:1,matches:101,complete_provider_catalog:true,has_more,instruments:[{symbol:"SPY",options:true}]}});
 render(<StockDirectory/>);fireEvent.click(screen.getByRole("button",{name:"Browse all stocks"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");expect(screen.queryByRole("button",{name:"SPY",exact:true})).toBeNull();expect(screen.getByRole("button",{name:"Retry"})).toBeEnabled();
});
