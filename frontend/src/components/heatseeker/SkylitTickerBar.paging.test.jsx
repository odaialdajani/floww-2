import React from "react";
import {render,screen,fireEvent} from "@testing-library/react";
import SkylitTickerBar from "./SkylitTickerBar";
beforeEach(()=>localStorage.clear());
const names=Array.from({length:65},(_,i)=>"T"+String(i).padStart(4,"0"));
test("vertical dropdown pages through every loaded name",()=>{
 render(<SkylitTickerBar activeTicker="T0000" tickers={names}/>);fireEvent.focus(screen.getByRole("combobox"));
 expect(screen.getByRole("button",{name:"Previous",exact:true})).toBeDisabled();expect(screen.getByRole("option",{name:"T0000"})).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"Next",exact:true}));expect(screen.getByRole("option",{name:"T0030"})).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"Next",exact:true}));expect(screen.getByRole("option",{name:"T0064"})).toBeInTheDocument();
 expect(screen.getByRole("button",{name:"Next",exact:true})).toBeDisabled();fireEvent.click(screen.getByRole("button",{name:"Previous",exact:true}));
 expect(screen.getByRole("option",{name:"T0030"})).toBeInTheDocument();
});
test("keyboard moves across vertical pages and Enter selects the owning option",()=>{
 const change=jest.fn();render(<SkylitTickerBar activeTicker="T0000" onTickerChange={change} tickers={names}/>);const input=screen.getByRole("combobox");fireEvent.focus(input);
 for(let i=0;i<31;i++)fireEvent.keyDown(input,{key:"ArrowDown"});
 expect(screen.getByRole("option",{name:"T0030"})).toHaveAttribute("aria-selected","true");fireEvent.keyDown(input,{key:"Enter"});expect(change).toHaveBeenCalledWith("T0030");
});
test("small lists need no paging controls",()=>{
 render(<SkylitTickerBar activeTicker="SPY" tickers={["SPY","QQQ"]}/>);fireEvent.focus(screen.getByRole("combobox"));expect(screen.queryByRole("button",{name:"Next",exact:true})).toBeNull();
});
test("a shrinking universe clamps browsing without losing current selection",()=>{
 const view=render(<SkylitTickerBar activeTicker="NOTLISTED" tickers={names}/>);fireEvent.focus(screen.getByRole("combobox"));
 fireEvent.click(screen.getByRole("button",{name:"Next",exact:true}));fireEvent.click(screen.getByRole("button",{name:"Next",exact:true}));
 view.rerender(<SkylitTickerBar activeTicker="NOTLISTED" tickers={["SPY","QQQ"]}/>);
 expect(screen.getByRole("option",{name:"SPY"})).toBeInTheDocument();expect(screen.getByText("Selected NOTLISTED")).toBeInTheDocument();expect(screen.queryByRole("button",{name:"Next",exact:true})).toBeNull();
});
