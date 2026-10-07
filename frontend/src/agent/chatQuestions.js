export const SECTION_LABELS={Structure:"Price and exposure",Flow:"Options activity",Levels:"Price levels",Vol:"Volatility",Company:"Company","What changed":"What changed",Confluence:"Readings together",Verdict:"Summary",Invalidation:"What would change this",Trade:"Trade notes"};
export const sectionLabel=name=>SECTION_LABELS[name] || name;
export function starterQuestions(context){
 const ticker=context?.ticker;if(!ticker)return [];
 return [
  {label:"Explain this reading",question:"Explain the selected "+ticker+" reading in plain English. What do the important levels mean, and which parts are estimates?"},
  {label:"What stands out?",question:"What stands out in the selected "+ticker+" data? Separate measured facts, estimates and missing information."},
  {label:"What is missing?",question:"What is missing from the selected "+ticker+" data, and which checks would make the reading more useful?"},
  {label:"Compare saved readings",question:"Show "+ticker+" saved history. What changed between compatible saved readings, and what remains unknown?"},
 ];
}
export function followUpQuestions(ticker){
 if(!ticker)return [];
 return [
  {label:"What could change this?",question:"For "+ticker+", which missing inputs or changes in the saved readings would change this assessment? Use the currently selected observations and explain the limits."},
  {label:"Explain the uncertainty",question:"For "+ticker+", explain why the currently selected reading is uncertain and what evidence would be needed for a stronger conclusion."},
  {label:"Compare with earlier",question:"Show "+ticker+" saved history and compare compatible earlier readings with the currently selected observations. Do not compare mismatched or time-unknown values."},
 ];
}
export function readableGap(text){
 if(/displayed map source observation time is unknown/i.test(text))return "The chart's market time is missing, so its freshness cannot be checked.";
 if(/chain observation time is unknown/i.test(text) && !/unavailable:/i.test(text))return "The option-chain's market time is missing, so its freshness cannot be checked.";
 if(/no eligible fresh directional alerts/i.test(text))return "No checked, current directional signal is available.";
 if(/^Implied move is unavailable/i.test(text))return "Expected price movement cannot be checked from the available option prices, times and volatility.";
 if(/^Realized volatility is unavailable/i.test(text))return "Recent price variation cannot be checked without usable, dated price bars.";
 if(/^Combined gamma, vanna and charm estimates are unavailable/i.test(text))return "Some exposure measures cannot be checked with the available data.";
 return String(text).length>220?String(text).slice(0,220)+"…":String(text);
}
