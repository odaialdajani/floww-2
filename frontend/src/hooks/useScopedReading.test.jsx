import { act, renderHook } from "@testing-library/react";
import { useScopedReading } from "./useScopedReading";

test("a changed selection cannot display or accept the old selection's reading", () => {
  const { result, rerender } = renderHook(({ scope }) => useScopedReading(scope), { initialProps: { scope: "SPY:4:day" } });
  const saveSpy = result.current[1];
  act(() => saveSpy({ spot: 764 }));
  expect(result.current[0]).toEqual({ spot: 764 });
  rerender({ scope: "GOLD:4:day" });
  expect(result.current[0]).toBeNull();
  act(() => saveSpy({ spot: 765 }));
  expect(result.current[0]).toBeNull();
  act(() => result.current[1]({ spot: 30 }));
  act(() => saveSpy({ spot: 766 }));
  expect(result.current[0]).toEqual({ spot: 30 });
  rerender({ scope: "GOLD:6:swing" });
  expect(result.current[0]).toBeNull();
  rerender({ scope: "SPY:4:day" });
  act(() => saveSpy({ spot: 767 }));
  expect(result.current[0]).toBeNull();
});
