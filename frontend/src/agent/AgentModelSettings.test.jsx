import React from "react";
import {act,render,screen,fireEvent,waitFor} from "@testing-library/react";
import AgentModelSettings from "./AgentModelSettings";

const models=[
 {id:"first",label:"First model",efforts:["low","medium","high"],default_effort:"medium",speeds:["default","priority"]},
 {id:"second",label:"Second model",efforts:["low","high"],default_effort:"high",speeds:["default"]},
];
let selected;
beforeEach(()=>{
 selected={model:"first",effort:"medium",speed:"default"};
 global.fetch=jest.fn(async(url,opts)=>{
  if(String(url).endsWith("/prefs")){selected=JSON.parse(opts.body).ai_settings;return {ok:true};}
  return {ok:true,json:async()=>({models,selected,usage:{calls:2,daily_limit:40}})};
 });
});

test("loads supported choices and saves them for the next question",async()=>{
 const saving=jest.fn();const view=render(<AgentModelSettings onSaving={saving}/>);
 fireEvent.click(screen.getByRole("button",{name:/AI choices/}));
 await screen.findByLabelText("Model");
 fireEvent.change(screen.getByLabelText("Thinking depth"),{target:{value:"high"}});
 fireEvent.change(screen.getByLabelText("Speed"),{target:{value:"priority"}});
 fireEvent.change(screen.getByLabelText("Model"),{target:{value:"second"}});
 expect(screen.getByLabelText("Speed").value).toBe("default");
 expect(screen.getByLabelText("Thinking depth").value).toBe("high");
 fireEvent.click(screen.getByRole("button",{name:"Save AI choice"}));
 await screen.findByText("Saved for your next question.");
 expect(selected).toEqual({model:"second",effort:"high",speed:"default"});
 expect(saving.mock.calls).toEqual([[true],[false],[true],[false]]);
 view.unmount();render(<AgentModelSettings/>);
 fireEvent.click(screen.getByRole("button",{name:/AI choices/}));
 await waitFor(()=>expect(screen.getByLabelText("Model").value).toBe("second"));
});

test("failed save never claims the choice was saved",async()=>{
 render(<AgentModelSettings/>);fireEvent.click(screen.getByRole("button",{name:/AI choices/}));
 await screen.findByLabelText("Thinking depth");
 fireEvent.change(screen.getByLabelText("Thinking depth"),{target:{value:"low"}});
 global.fetch.mockResolvedValue({ok:false});
 fireEvent.click(screen.getByRole("button",{name:"Save AI choice"}));
 await screen.findByText(/choice was not confirmed/);
 expect(screen.queryByText("Saved for your next question.")).toBeNull();
 expect(screen.getByText(/Unsaved choice/)).toBeTruthy();
});

test("an unavailable saved model can be replaced",async()=>{
 selected={model:"removed",effort:"medium",speed:"default"};
 render(<AgentModelSettings/>);fireEvent.click(screen.getByRole("button",{name:/AI choices/}));
 await screen.findByText(/Choose and save a replacement/);
 expect(screen.getByLabelText("Model").value).toBe("first");
 fireEvent.change(screen.getByLabelText("Model"),{target:{value:"second"}});
 fireEvent.click(screen.getByRole("button",{name:"Save AI choice"}));
 await screen.findByText("Saved for your next question.");
 expect(selected.model).toBe("second");
});

test("logout clears choices and rejects a late reply",async()=>{
 let release;
 global.fetch.mockImplementation(async url=>String(url).endsWith("/models")?await new Promise(resolve=>{release=resolve;}):{ok:true});
 render(<AgentModelSettings/>);fireEvent.click(screen.getByRole("button",{name:/AI choices/}));
 await waitFor(()=>expect(release).toBeTruthy());
 act(()=>window.dispatchEvent(new Event("floww-research-session-ended")));
 await act(async()=>release({ok:true,json:async()=>({models,selected})}));
 expect(screen.queryByLabelText("Model")).toBeNull();
 expect(screen.getByRole("button",{name:/AI choices/}).getAttribute("aria-expanded")).toBe("false");
});
test("a removed thinking depth needs a supported replacement",async()=>{
 selected={model:"first",effort:"removed",speed:"default"};
 render(<AgentModelSettings/>);fireEvent.click(screen.getByRole("button",{name:/AI choices/}));
 await screen.findByText(/saved depth or speed is unavailable/);
 expect(screen.getByLabelText("Thinking depth").value).not.toBe("removed");
 expect(screen.getByRole("button",{name:"Save AI choice"})).not.toBeDisabled();
});
