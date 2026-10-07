let stop,tracker,socketBefore;
beforeEach(()=>{
 socketBefore=window.WebSocket;localStorage.clear();jest.resetModules();jest.useFakeTimers();jest.setSystemTime(new Date("2026-10-06T17:00:00Z"));
 window.fetch=jest.fn();tracker=require("./problemTracking");
});
afterEach(()=>{stop?.();window.WebSocket=socketBefore;jest.useRealTimers();});
const reply=(status)=>({ok:status>=200 && status<300,status});
const api=require("../config/api").API;

test("a cached failed GET retries once and records its result",async()=>{
 jest.useRealTimers();
 const native=window.fetch.mockResolvedValueOnce(reply(503)).mockResolvedValueOnce(reply(200));
 stop=tracker.startProblemTracking();
 const pending=window.fetch(api+"/agent/models");

 expect((await pending).ok).toBe(true);
 expect(native).toHaveBeenCalledTimes(2);
 const events=JSON.parse(localStorage.getItem("floww.problemQueue"));
 expect(events.map(x=>x.kind)).toEqual(["read_error","recovery","recovery"]);
 expect(events[2].result).toBe("succeeded");
});

test.each(["/agent/ask","/agent/session","/alpaca/order"])("POST %s is never replayed",async route=>{
 const native=window.fetch.mockResolvedValue(reply(503));stop=tracker.startProblemTracking();
 expect((await window.fetch(api+route,{method:"POST",body:"private question"})).status).toBe(503);
 expect(native).toHaveBeenCalledTimes(1);
 expect(localStorage.getItem("floww.problemQueue")).not.toContain("private question");
});

test("rate limits and unrelated GET reads are not retried",async()=>{
 const native=window.fetch.mockResolvedValue(reply(429));stop=tracker.startProblemTracking();
 await window.fetch(api+"/agent/models");
 native.mockResolvedValue(reply(503));await window.fetch(api+"/public/chain/SPY");
 expect(native).toHaveBeenCalledTimes(2);
});

test("cancelled reads are not reported as failures",async()=>{
 const native=window.fetch.mockRejectedValue(new DOMException("cancelled","AbortError"));stop=tracker.startProblemTracking();
 await expect(window.fetch(api+"/agent/models")).rejects.toHaveProperty("name","AbortError");
 expect(native).toHaveBeenCalledTimes(1);expect(localStorage.getItem("floww.problemQueue")).toBeNull();
});

test("browser errors record their class without private text",()=>{
 stop=tracker.startProblemTracking();
 window.dispatchEvent(new ErrorEvent("error",{error:new TypeError("private credentials and question")}));
 const text=localStorage.getItem("floww.problemQueue");
 expect(text).toContain("TypeError");expect(text).not.toContain("private");
});

test("a new report during upload survives and overlapping uploads are skipped",async()=>{
 jest.useRealTimers();let finish;
 const native=window.fetch.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
 stop=tracker.startProblemTracking();
 for(let i=0;i<30;i++)tracker.reportProblem({kind:"browser_error",name:"TypeError"});
 const pending=tracker.flushProblems();
 tracker.reportProblem({kind:"screen_lag",duration_ms:1500});
 await tracker.flushProblems();expect(native).toHaveBeenCalledTimes(1);
 finish(reply(200));await pending;
 const queue=JSON.parse(localStorage.getItem("floww.problemQueue"));
 expect(queue).toHaveLength(1);expect(queue[0].kind).toBe("screen_lag");
});

test("connection failures are reported once without token queries",()=>{
 class FakeSocket extends EventTarget {static OPEN=1;}
 window.WebSocket=FakeSocket;stop=tracker.startProblemTracking();
 const socket=new window.WebSocket(api.replace(/^http/,"ws")+"/stream?token=private-token");
 expect(socket instanceof FakeSocket).toBe(true);expect(window.WebSocket.OPEN).toBe(1);
 socket.dispatchEvent(new Event("error"));socket.dispatchEvent(new CloseEvent("close",{wasClean:false}));
 const events=JSON.parse(localStorage.getItem("floww.problemQueue"));
 expect(events).toHaveLength(1);expect(events[0].kind).toBe("socket_error");
 expect(JSON.stringify(events)).not.toContain("private-token");
});
