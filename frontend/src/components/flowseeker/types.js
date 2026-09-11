/**
 * types.js — JSDoc local types for flowseeker lane.
 * No backend dependency; fixture-first.
 */

/**
 * @typedef {Object} PulseRow
 * @property {string} ticker
 * @property {string} under
 * @property {string} type - 'call' | 'put'
 * @property {number} strike
 * @property {string} exp - YYYY-MM-DD
 * @property {string} expiration - alias for exp
 * @property {number} bid
 * @property {number} ask
 * @property {number} last
 * @property {number} premium
 * @property {number} volume
 * @property {number} vol
 * @property {number} oi
 * @property {number} iv
 * @property {number} score
 * @property {number} dte
 * @property {string} side - BID|MID|ASK|NO_QUOTE
 * @property {Array} legs - optional multi-leg
 */

/**
 * @typedef {Object} TabConfig
 * @property {number} schemaVersion
 * @property {string} id
 * @property {string} title
 * @property {Object} filters
 * @property {string[]} columns
 * @property {{sizeGtOI:boolean, volGtOI:boolean}} highlighting
 * @property {string} tickerScope
 * @property {number} resultsCap
 * @property {{key:string, dir:string}} sort
 */

/**
 * @typedef {'loading'|'empty'|'stale'|'error'|'frozen'|'no_quote'|'no_baseline'|'paid_gate'|'ready'} SurfaceState
 */
export const _types = true;
