import {render,screen,fireEvent} from "@testing-library/react";
import AgentCommandBar from "./AgentCommandBar";
let mockSettingsOpen=false;
const mockSetOpen=jest.fn();
jest.mock("./AgentProvider",()=>({useAgent:()=>({setOpen:mockSetOpen,settingsOpen:mockSettingsOpen})}));
beforeEach(()=>{mockSettingsOpen=false;mockSetOpen.mockReset();});
test("the compact Assistant entry opens chat and the shortcut toggles it",()=>{
 render(<AgentCommandBar/>);
 fireEvent.click(screen.getByRole('button',{name:'Open Ask FLOWW'}));expect(mockSetOpen).toHaveBeenCalledWith(true);
 fireEvent.keyDown(window,{key:'k',ctrlKey:true});
 const toggle=mockSetOpen.mock.calls[1][0];expect(toggle(false)).toBe(true);expect(toggle(true)).toBe(false);
 expect(screen.queryByText(/Lodestar/)).toBeNull();
});
test("the chat shortcut leaves an open settings popup alone",()=>{
 mockSettingsOpen=true;render(<AgentCommandBar/>);
 fireEvent.keyDown(window,{key:'k',ctrlKey:true});expect(mockSetOpen).not.toHaveBeenCalled();
});
