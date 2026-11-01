/**
 * @jest-environment jsdom
 */
import React from "react";
import {act,fireEvent,render,screen} from "@testing-library/react";
import ProblemStatus from "./ProblemStatus";
import {reportProblem,startProblemTracking,flushProblems} from "./problemTracking";

test("the phone neither retries local-only reports nor promises a saved queue",async()=>{
 const location=jest.spyOn(window,"location","get").mockReturnValue(new URL("http://192.168.0.18:3000/"));
 jest.useFakeTimers();window.fetch=jest.fn();localStorage.clear();
 const stop=startProblemTracking();reportProblem({kind:"browser_error",name:"TypeError"});
 render(<ProblemStatus/>);fireEvent.click(screen.getByRole("button",{name:"App health"}));
 await act(async()=>{await flushProblems();jest.advanceTimersByTime(60000);});
 expect(window.fetch).not.toHaveBeenCalled();
 expect(localStorage.getItem("floww.problemQueue")).toBeNull();
 expect(screen.getByText(/does not upload or queue screen reports/)).toBeInTheDocument();
 stop();location.mockRestore();jest.useRealTimers();
});
