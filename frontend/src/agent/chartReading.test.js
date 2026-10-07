
import {savedChartReading} from './chartReading';
// Synthetic bounded fixtures use the literal fact names produced by display_map.
const scope='display:'+ 'a'.repeat(64);
const reading=(metric,value,extra={})=>({id:'saved-'+metric,metric,value,ticker:'SPY',unit:'display gamma units',horizon:scope,snapshot_id:'recorded-desktop-map',source:'public_api',status:'degraded',event_time:null,...extra});
function profileAnswer(values=[4e6,-9e6,2e6],counts){
 const facts=[reading('Displayed strikes',[100,105,110],{unit:'USD'}),reading('Displayed expiry dates',['2026-10-09','2026-10-16'],{unit:'dates'}),reading('Display basis','Raw OI',{unit:'basis'}),reading('Displayed signed profile',values),reading('Displayed profile missing delta',[0,0,0],{unit:'excluded contracts'}),reading('Displayed profile invalid delta',[0,0,0],{unit:'excluded contracts'})];
 if(counts!==undefined)facts.push(reading('Displayed profile contributing expiries',counts,{unit:'expiry counts'}));
 return {facts,gaps:['Displayed map source observation time is unknown']};
}
const lines=answer=>savedChartReading(answer,'SPY');
const words=answer=>lines(answer).map(line=>line.text).join('\n');

test('existing desktop signed-profile facts show the largest saved contribution without pretending the full bar is known',()=>{
 const answer=profileAnswer();const original=JSON.stringify(answer);const text=words(answer);
 expect(text).toMatch(/Largest saved profile contribution:.*105.*-9M/i);expect(text).toMatch(/missing.*expiry contributions|expiry contributions.*unknown/i);
 expect(text).not.toMatch(/Largest visible bar:|Visible total:|All visible bars are zero/);expect(text).toMatch(/Market observation time is unknown/);
 expect(JSON.stringify(answer)).toBe(original);const explanation=lines(answer).find(line=>/Largest saved profile contribution/i.test(line.text));expect(explanation.factIds).toContain('saved-Displayed signed profile');
});

test('explicit complete raw-GEX expiry counts reveal the actual visible bar and total with the original supporting facts',()=>{
 const answer=profileAnswer(undefined,[2,2,2]);const original=JSON.stringify(answer);const text=words(answer);
 expect(text).toMatch(/Largest visible bar:.*105.*-9M/);expect(text).toMatch(/Visible total: -3M/);expect(text).toMatch(/not a price target|not.*direction forecast/);
 expect(text).toMatch(/Market observation time is unknown/);expect(JSON.stringify(answer)).toBe(original);
 const largest=lines(answer).find(line=>/Largest visible bar:/.test(line.text));expect(largest.factIds).toEqual(expect.arrayContaining(['saved-Displayed strikes','saved-Displayed signed profile','saved-Displayed profile contributing expiries']));
 const total=lines(answer).find(line=>/Visible total:/.test(line.text));expect(total.factIds).toContain('saved-Displayed profile contributing expiries');
});

test('a finite partial-expiry sum stays a saved contribution and cannot become a complete bar or total',()=>{
 const answer=profileAnswer([4e6,-9e6,2e6],[2,1,2]);const text=words(answer);
 expect(text).toMatch(/Largest saved profile contribution:.*105.*-9M/i);expect(text).toMatch(/missing.*expiry contributions|expiry contributions.*unknown/i);
 expect(text).not.toMatch(/Largest visible bar:|Visible total:/);
});

test.each([undefined,[0,1,2]])('zero saved contributions with incomplete or absent counts remain unknown beyond the supplied cells: %j',counts=>{
 const text=words(profileAnswer([0,0,0],counts));expect(text).toMatch(/saved profile contributions.*zero/i);expect(text).toMatch(/missing.*expiry contributions|expiry contributions.*unknown/i);
 expect(text).not.toMatch(/All visible bars are zero|Visible total:|Largest visible bar:/);
});

test('all-zero complete raw-GEX bars are stated only when every shown expiry is explicitly present',()=>{
 const text=words(profileAnswer([0,0,0],[2,2,2]));expect(text).toMatch(/All visible bars are zero/);expect(text).toMatch(/Visible total: 0/);expect(text).not.toMatch(/Largest.*bar:/);
});

test.each([
 {snapshot_id:'another-map'},
 {horizon:'display:another-scope'},
 {unit:'contracts'},
 {value:[2,2]},
 {value:[2,3,2]},
 {value:[2,-1,2]},
 {value:[2,1.5,2]},
 {value:[2,'2',2]},
])('unmatched or invalid expiry-count evidence cannot qualify a complete profile: %j',change=>{
 const answer=profileAnswer(undefined,[2,2,2]);Object.assign(answer.facts.find(fact=>fact.metric==='Displayed profile contributing expiries'),change);const text=words(answer);
 expect(text).toMatch(/Largest saved profile contribution/i);expect(text).not.toMatch(/Largest visible bar:|Visible total:|All visible bars are zero/);
});

test.each([
 ['wrong profile snapshot',answer=>{answer.facts.find(fact=>fact.metric==='Displayed signed profile').snapshot_id='other';}],
 ['wrong profile horizon',answer=>{answer.facts.find(fact=>fact.metric==='Displayed signed profile').horizon='display:other';}],
 ['different units',answer=>{answer.facts.find(fact=>fact.metric==='Displayed signed profile').unit='display vex units';}],
 ['adjusted basis',answer=>{answer.facts.find(fact=>fact.metric==='Display basis').value='Delta-adjusted';}],
])('raw-GEX profile insight cannot cross the saved scope or measure: %s',(_,change)=>{
 const answer=profileAnswer(undefined,[2,2,2]);change(answer);const text=words(answer);expect(text).not.toMatch(/Largest.*profile contribution|Largest.*bar:|Visible total:/);
});

test('null profile values stay missing even when a corrupt count claims every expiry',()=>{
 const text=words(profileAnswer([4e6,null,2e6],[2,2,2]));expect(text).toMatch(/Largest saved profile contribution:.*100.*\+4M/i);expect(text).not.toMatch(/Largest visible bar:|Visible total:/);
});


test('missing legacy horizons cannot qualify a complete raw profile even when all expiry counts are present',()=>{
 for(const values of [[4e6,-9e6,2e6],[0,0,0]]){
  const answer=profileAnswer(values,[2,2,2]);for(const fact of answer.facts)delete fact.horizon;
  const original=JSON.stringify(answer);const text=words(answer);
  expect(text).not.toMatch(/Largest visible bar:|Visible total:|All visible bars are zero/);expect(JSON.stringify(answer)).toBe(original);
 }
});
