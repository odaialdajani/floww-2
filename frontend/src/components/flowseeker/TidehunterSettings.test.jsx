import {loadTide, saveSettings, SETTINGS_KEY} from "./TidehunterSettings";
import {applyScreenToScans} from "./tideFeed";

beforeEach(()=>localStorage.clear());
test("saved fractional OI rules retain their behavior through nested groups and repeated saves",()=>{
 const original={theme:"dark",tidehunter:{screens:[{id:"old",custom:true,conditions:[{join:"OR",conditions:[{fact:"oiChgPct",op:"≥",value:"0.29"},{fact:"oiChgPct",op:"between",value:"0.10,0.20"}]}]}]}};
 localStorage.setItem(SETTINGS_KEY,JSON.stringify(original));
 const migrated=loadTide().screens[0];
 expect(migrated.ruleUnitsVersion).toBe(2);
 expect(migrated.conditions[0].conditions.map(c=>c.value)).toEqual(["29","10,20"]);
 expect(applyScreenToScans([{under:"SPY",oiChgPct:0.29},{under:"QQQ",oiChgPct:0.15},{under:"IWM",oiChgPct:0.25}],migrated,{}).map(r=>r.under)).toEqual(["SPY","QQQ"]);
 expect(JSON.parse(localStorage.getItem(SETTINGS_KEY))).toEqual(original);
 expect(saveSettings({mode:"monitor"})).toBe(true);
 expect(saveSettings({mode:"research"})).toBe(true);
 expect(loadTide().screens[0]).toEqual(migrated);
 expect(JSON.parse(localStorage.getItem(SETTINGS_KEY)).theme).toBe("dark");
});
test("new percent rules are not migrated twice",()=>{
 const screen={id:"new",custom:true,ruleUnitsVersion:2,conditions:[{fact:"oiChgPct",op:"≥",value:"20"}]};
 expect(saveSettings({screens:[screen]})).toBe(true);
 expect(loadTide().screens[0]).toEqual(screen);
});
