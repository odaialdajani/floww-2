import { inspectorAvailableHeight } from "./inspectorGeometry";

test("the inspector clears controls before and after its sticky position changes", () => {
  expect(inspectorAvailableHeight(700, 240, [588, 649])).toBe(332);
  expect(inspectorAvailableHeight(700, 6, [588, 649])).toBe(566);
});

test("a short viewport never produces a negative available height", () => {
  expect(inspectorAvailableHeight(350, 240, [206, 253])).toBe(0);
});
