import {savedDailyPriceReading} from './chartReading';
// Actual returned SPY daily-price facts; no provider/model work in these tests.
const actualFacts=[
  {
    "metric": "Realized volatility observation dates",
    "value": [
      "2026-09-08",
      "2026-09-09",
      "2026-09-10",
      "2026-09-11",
      "2026-09-14",
      "2026-09-15",
      "2026-09-16",
      "2026-09-17",
      "2026-09-18",
      "2026-09-21",
      "2026-09-22",
      "2026-09-23",
      "2026-09-24",
      "2026-09-25",
      "2026-09-28",
      "2026-09-29",
      "2026-09-30",
      "2026-10-01",
      "2026-10-02",
      "2026-10-05",
      "2026-10-06"
    ],
    "unit": "dates",
    "ticker": "SPY",
    "source": "public_api",
    "snapshot_id": "32a8537b90ae180b0b0ab32aea752a4bd1ffcf267d48c9518c505513261eaa40",
    "event_time": "2026-10-06T20:00:00+00:00",
    "received_at": "2026-10-07T07:25:31.137852+00:00",
    "horizon": "all",
    "contract": null,
    "status": "degraded",
    "reason": "Completed daily bars; provider_reported prices; provider adjustment policy is unknown",
    "version": "research-1",
    "parents": [],
    "id": "evde0da73184a6a175a99c69ba1cf34ccf702ac967a79d6bc5f71dd0d4564417d7"
  },
  {
    "metric": "Realized volatility close prices",
    "value": [
      765.96,
      762.4,
      757.83,
      764.29,
      760.88,
      757.39,
      754.05,
      762.6,
      761.69,
      773.5,
      773.38,
      767.81,
      767.18,
      771.35,
      765.61,
      764.2,
      762.63,
      763.99,
      769.64,
      774.83,
      779.09
    ],
    "unit": "USD",
    "ticker": "SPY",
    "source": "public_api",
    "snapshot_id": "32a8537b90ae180b0b0ab32aea752a4bd1ffcf267d48c9518c505513261eaa40",
    "event_time": "2026-10-06T20:00:00+00:00",
    "received_at": "2026-10-07T07:25:31.137852+00:00",
    "horizon": "all",
    "contract": null,
    "status": "degraded",
    "reason": "Completed daily bars; provider_reported prices; provider adjustment policy is unknown",
    "version": "research-1",
    "parents": [],
    "id": "evfa82863851db4a69f345391bfa108a3b05aec956fd375fae9a2f93773edf2b36"
  },
  {
    "metric": "Realized daily close volatility",
    "value": 0.10427710271385104,
    "unit": "annualized fraction",
    "ticker": "SPY",
    "source": "public_api",
    "snapshot_id": "32a8537b90ae180b0b0ab32aea752a4bd1ffcf267d48c9518c505513261eaa40",
    "event_time": "2026-10-06T20:00:00+00:00",
    "received_at": "2026-10-07T07:25:31.137852+00:00",
    "horizon": "all",
    "contract": null,
    "status": "degraded",
    "reason": "Sample standard deviation of daily log returns times sqrt(252); historical window only",
    "version": "research-1",
    "parents": [
      "evde0da73184a6a175a99c69ba1cf34ccf702ac967a79d6bc5f71dd0d4564417d7",
      "evfa82863851db4a69f345391bfa108a3b05aec956fd375fae9a2f93773edf2b36"
    ],
    "id": "ev108a8585ab6154f528869cbecff306a0b06aa8e9b6cd7dbb6c8f3cccf37d547e"
  }
];
const answer=()=>({facts:JSON.parse(JSON.stringify(actualFacts))});
const independentVol=closes=>{const returns=closes.slice(1).map((price,i)=>Math.log(price/closes[i]));const mean=returns.reduce((sum,value)=>sum+value,0)/returns.length;return Math.sqrt(returns.reduce((sum,value)=>sum+(value-mean)**2,0)/(returns.length-1))*Math.sqrt(252);};


test('the actual degraded SPY evidence is available as dated historical price variation without losing adjustment limits',()=>{
 const saved=answer(),before=JSON.stringify(saved);const reading=savedDailyPriceReading(saved,'SPY');
 expect(reading).not.toBeNull();expect(reading.value).toBeCloseTo(0.10427710271385104,14);expect(reading.value).toBeCloseTo(independentVol(actualFacts[1].value),14);expect(reading.annualizedPercent).toBeCloseTo(10.427710271385104,12);
 expect(reading.dates).toEqual(actualFacts[0].value);expect(reading.closes).toEqual(actualFacts[1].value);expect(reading.returnCount).toBe(20);expect(reading.source).toBe('public_api');expect(reading.status).toBe('degraded');expect(reading.reason).toMatch(/adjustment policy is unknown/);
 expect(reading.factIds).toEqual(expect.arrayContaining(actualFacts.map(fact=>fact.id)));expect(JSON.stringify(saved)).toBe(before);
});

test('the same saved price window can preserve an honest stale state',()=>{
 const saved=answer();saved.facts.forEach(fact=>fact.status='stale');const reading=savedDailyPriceReading(saved,'SPY');expect(reading.status).toBe('stale');expect(reading.value).toBe(actualFacts[2].value);
});

test('a derived scalar cannot upgrade degraded parent prices into checked healthy evidence',()=>{
 const saved=answer();saved.facts[2].status='ok';const reading=savedDailyPriceReading(saved,'SPY');expect(reading.status).toBe('degraded');expect(reading.reason).toMatch(/adjustment policy is unknown/);
});

test('a genuinely flat matched daily price window is zero without becoming missing',()=>{
 const saved=answer();saved.facts[1].value=Array(saved.facts[0].value.length).fill(100);saved.facts[2].value=0;const reading=savedDailyPriceReading(saved,'SPY');expect(reading.value).toBe(0);expect(reading.annualizedPercent).toBe(0);expect(reading.returnCount).toBe(20);
});

test('a different selected stock cannot borrow the SPY daily-price reading',()=>{
 expect(savedDailyPriceReading(answer(),'QQQ')).toBeNull();
});

test.each([
 ['missing scalar',saved=>saved.facts.pop()],
 ['duplicate dates',saved=>saved.facts.push({...saved.facts[0],id:'different-dates'})],
 ['duplicate scalar',saved=>saved.facts.push({...saved.facts[2],id:'different-scalar'})],
 ['mixed ticker',saved=>saved.facts[1].ticker='QQQ'],
 ['mixed source',saved=>saved.facts[1].source='another-provider'],
 ['missing source',saved=>delete saved.facts[1].source],
 ['mixed snapshot',saved=>saved.facts[2].snapshot_id='other-snapshot'],
 ['missing snapshot',saved=>saved.facts.forEach(fact=>delete fact.snapshot_id)],
 ['mixed horizon',saved=>saved.facts[1].horizon='days:1'],
 ['missing horizon',saved=>saved.facts.forEach(fact=>delete fact.horizon)],
 ['missing market time',saved=>saved.facts.forEach(fact=>fact.event_time=null)],
 ['different market time',saved=>saved.facts[2].event_time='2026-10-06T19:00:00Z'],
 ['wrong date unit',saved=>saved.facts[0].unit='UTC instant'],
 ['wrong price unit',saved=>saved.facts[1].unit='percent'],
 ['wrong scalar unit',saved=>saved.facts[2].unit='percent'],
 ['unknown quality',saved=>saved.facts[1].status='unknown'],
 ['missing parent link',saved=>saved.facts[2].parents=[saved.facts[0].id]],
 ['unknown extra parent',saved=>saved.facts[2].parents.push('unavailable-parent')],
 ['mismatched lengths',saved=>saved.facts[1].value.pop()],
 ['nonpositive price',saved=>saved.facts[1].value[4]=0],
 ['nonnumeric price',saved=>saved.facts[1].value[4]='760.88'],
 ['invalid price',saved=>saved.facts[1].value[4]=Infinity],
 ['unordered dates',saved=>{const dates=saved.facts[0].value;[dates[0],dates[1]]=[dates[1],dates[0]];}],
 ['repeated dates',saved=>saved.facts[0].value[1]=saved.facts[0].value[0]],
 ['invalid calendar date',saved=>saved.facts[0].value[0]='2026-02-30'],
 ['non-date label',saved=>saved.facts[0].value[0]='Sep 8'],
 ['inconsistent scalar',saved=>saved.facts[2].value=0.2],
 ['negative scalar',saved=>saved.facts[2].value=-0.1],
])('unverified or contradictory daily price evidence is refused: %s',(_,change)=>{
 const saved=answer();change(saved);expect(savedDailyPriceReading(saved,'SPY')).toBeNull();
});

test('equivalent explicit UTC labels identify the same stored market instant without changing source fields',()=>{
 const saved=answer();saved.facts[1].event_time='2026-10-06T20:00:00Z';const before=JSON.stringify(saved);expect(savedDailyPriceReading(saved,'SPY')).not.toBeNull();expect(JSON.stringify(saved)).toBe(before);
});

test.each([null,{}, {facts:null},{facts:{}},{facts:[null]}])('incomplete stored bodies safely have no verified daily price reading: %j',saved=>{
 expect(savedDailyPriceReading(saved,'SPY')).toBeNull();
});


test('a shorter coherent saved daily history retains its own observation and return counts',()=>{
 const saved=answer();saved.facts[0].value=saved.facts[0].value.slice(0,3);saved.facts[1].value=saved.facts[1].value.slice(0,3);saved.facts[2].value=independentVol(saved.facts[1].value);saved.facts.forEach(fact=>fact.event_time='2026-09-10T20:00:00Z');
 const reading=savedDailyPriceReading(saved,'SPY');expect(reading.returnCount).toBe(2);expect(reading.dates).toEqual(saved.facts[0].value);expect(reading.value).toBe(saved.facts[2].value);
});

test('returned date and price arrays do not allow changing the original saved evidence',()=>{
 const saved=answer(),before=JSON.stringify(saved);const reading=savedDailyPriceReading(saved,'SPY');reading.dates[0]='2000-01-01';reading.closes[0]=1;expect(JSON.stringify(saved)).toBe(before);
});

test.each([
 ['blank source',saved=>saved.facts.forEach(fact=>fact.source=' ')],
 ['blank snapshot',saved=>saved.facts.forEach(fact=>fact.snapshot_id=' ')],
 ['blank horizon',saved=>saved.facts.forEach(fact=>fact.horizon=' ')],
 ['blank evidence ID',saved=>saved.facts[0].id=' '],
 ['reused evidence ID',saved=>saved.facts[1].id=saved.facts[0].id],
 ['unparseable market clock',saved=>saved.facts.forEach(fact=>fact.event_time='not-a-clock')],
 ['timezone-less market clock',saved=>saved.facts.forEach(fact=>fact.event_time='2026-10-06T20:00:00')],
 ['invalid market date',saved=>saved.facts.forEach(fact=>fact.event_time='2026-02-30T20:00:00Z')],
 ['market clock predates last observation',saved=>saved.facts.forEach(fact=>fact.event_time='2026-10-05T20:00:00Z')],
 ['daily facts attached to an option contract',saved=>saved.facts[1].contract='option-contract'],
 ['missing status',saved=>delete saved.facts[1].status],
 ['missing parent array',saved=>saved.facts[2].parents=null],
 ['insufficient observations',saved=>{saved.facts[0].value=saved.facts[0].value.slice(-2);saved.facts[1].value=saved.facts[1].value.slice(-2);saved.facts[2].value=0;}],
])('unsafe stored daily evidence is refused: %s',(_,change)=>{
 const saved=answer();change(saved);expect(savedDailyPriceReading(saved,'SPY')).toBeNull();
});

test('an empty stock selection cannot match empty labels in saved evidence',()=>{
 const saved=answer();saved.facts.forEach(fact=>fact.ticker='');expect(savedDailyPriceReading(saved,'')).toBeNull();
});
