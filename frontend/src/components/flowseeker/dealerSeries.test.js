import { dealerSeries } from "./dealerSeries";
const heat = { spot: 178.4, grid: { strikes: [180, 175, 177.5], expiries: ["a", "b"], grid: { a: {175: 10, 177.5: -20, 180: 30}, b: {175: 5, 177.5: -10, 180: 10} } } };
test("sums displayed expiries in numeric strike order with real flip interpolation", () => {
 const s = dealerSeries(heat, 176);
 expect(s.strikes).toEqual([175, 177.5, 180]);
 expect(s.net).toEqual([15, -30, 40]);
 expect(s.cumulative).toEqual([15, -15, 25]);
 expect(s.total).toBe(25);
 expect(s.maxMagnitude).toBe(40);
 expect(s.flipFraction).toBeCloseTo(0.2);
});
test("missing cells cannot become zero or a complete total", () => {
 const s = dealerSeries({grid:{strikes:[1,2],expiries:["a"],grid:{a:{1:0}}}}, 4);
 expect(s.net).toEqual([0,null]); expect(s.total).toBeNull(); expect(s.flipFraction).toBeNull();
});
test.each([0, -12, 12])("one strike has finite coordinates and retains value %s", value => {
 const s=dealerSeries({grid:{strikes:[1],expiries:["a"],grid:{a:{1:value}}}},1);
 expect(s.net).toEqual([value]);expect(s.flipFraction).toBe(0.5);expect(s.xFraction(1)).toBe(0.5);
});
test("rejects nonnumeric and nonfinite cells and strikes", () => {
 const s=dealerSeries({grid:{strikes:["no",NaN,1],expiries:["a"],grid:{a:{1:Infinity}}}},null);
 expect(s.strikes).toEqual([1]);expect(s.net).toEqual([null]);expect(s.total).toBeNull();
});
