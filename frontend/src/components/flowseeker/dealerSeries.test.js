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
test("selected expiry scope uses its cells and never substitutes another expiry",()=>{
 const s=dealerSeries(heat,176,14,["b"]);
 expect(s.expiries).toEqual(["b"]);expect(s.net).toEqual([5,-10,10]);expect(s.total).toBe(5);
 const absent=dealerSeries(heat,176,14,["missing"]);
 expect(absent.expiries).toEqual([]);expect(absent.hasData).toBe(false);expect(absent.total).toBeNull();
});
test.each([[[0,0,0]],[[1,2,3]],[[-1,-2,-3]]])("keeps one signed total across multi-strike data %p",values=>{
 const s=dealerSeries({grid:{strikes:[1,2,3],expiries:["a"],grid:{a:Object.fromEntries(values.map((v,i)=>[i+1,v]))}}},2);
 expect(s.net).toEqual(values);expect(s.total).toBe(values.reduce((a,b)=>a+b,0));
 expect(s.strikes.map(s.xFraction)).toEqual([0,0.5,1]);
});
