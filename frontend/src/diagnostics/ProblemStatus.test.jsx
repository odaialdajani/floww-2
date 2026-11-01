import React from "react";
import {act,fireEvent,render,screen} from "@testing-library/react";
import ProblemStatus from "./ProblemStatus";
const reply=(status,data={total_events:2,recurring:1,issues:[],recoveries:[]})=>({ok:status===200,status,json:async()=>data});
const advance=async ms=>{await act(async()=>{jest.advanceTimersByTime(ms);});};
const open=async()=>{render(<ProblemStatus/>);await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"App health"}));});};
beforeEach(()=>{jest.useFakeTimers();window.fetch=jest.fn();});
afterEach(()=>{jest.useRealTimers();});

test("summary failures back off, recovery resets the cadence and old values are labelled",async()=>{
 window.fetch.mockResolvedValueOnce(reply(200)).mockResolvedValueOnce(reply(503))
  .mockResolvedValueOnce(reply(503)).mockResolvedValue(reply(200));
 await open();expect(window.fetch).toHaveBeenCalledTimes(1);
 await advance(15000);expect(window.fetch).toHaveBeenCalledTimes(2);
 expect(screen.getByText(/Last received summary/)).toBeInTheDocument();
 await advance(15000);expect(window.fetch).toHaveBeenCalledTimes(3);
 await advance(15000);expect(window.fetch).toHaveBeenCalledTimes(3);
 await advance(15000);expect(window.fetch).toHaveBeenCalledTimes(4);
 await advance(15000);expect(window.fetch).toHaveBeenCalledTimes(5);
});

test("an origin refusal stops periodic reconnect attempts",async()=>{
 window.fetch.mockResolvedValue(reply(403));await open();
 await advance(60000);expect(window.fetch).toHaveBeenCalledTimes(1);
 expect(screen.getByRole("status")).not.toHaveTextContent(/reconnecting/i);
});

test("summary Retry-After is honored",async()=>{
 window.fetch.mockResolvedValueOnce({...reply(429),headers:{get:()=>"120"}}).mockResolvedValue(reply(200));
 await open();await advance(119999);expect(window.fetch).toHaveBeenCalledTimes(1);
 await advance(1);expect(window.fetch).toHaveBeenCalledTimes(2);
});

test("closing the panel aborts a pending read without starting another",async()=>{
 let signal;
 window.fetch.mockImplementation((url,options)=>new Promise((resolve,reject)=>{
  signal=options.signal;signal.addEventListener("abort",()=>reject(new DOMException("Stopped","AbortError")));
 }));
 await open();fireEvent.click(screen.getByRole("button",{name:"App health"}));
 await advance(60000);expect(signal.aborted).toBe(true);expect(window.fetch).toHaveBeenCalledTimes(1);
});
