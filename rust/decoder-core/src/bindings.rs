//! PyO3 0.22 bindings — expose decoder-core to the FastAPI backend.
//!
//! Uses Bound<'_, T> API throughout (PyO3 ≥ 0.21 style).

use crate::gex::{self, RawContract, StrikeRow};
use crate::curve;
use crate::greeks;
use crate::grid;
use crate::nodes;
use crate::probdist;
use crate::iv;
use crate::term;
use crate::vpin;
use crate::rvol;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;

/// bs_gamma(S, K, T, sigma, r=0.05, q=0.0) — parity with backend/bs_greeks.py
#[pyfunction]
#[pyo3(signature = (s, k, t, sigma, r=0.05, q=0.0))]
fn bs_gamma(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64) -> f64 {
    greeks::gamma_scalar(s, k, t, sigma, r, q)
}

/// Batch gamma over parallel slices at one spot. Parallel via rayon.
#[pyfunction]
#[pyo3(signature = (spot, strikes, ts, sigmas, r=0.05, q=0.0))]
fn gamma_batch(
    spot: f64,
    strikes: Vec<f64>,
    ts: Vec<f64>,
    sigmas: Vec<f64>,
    r: f64,
    q: f64,
) -> PyResult<Vec<f64>> {
    if strikes.len() != ts.len() || strikes.len() != sigmas.len() {
        return Err(PyValueError::new_err("strikes/ts/sigmas length mismatch"));
    }
    let n = strikes.len();
    // Rayon spawn overhead dominates small batches (~65µs at n=300 vs ~15µs
    // sequential). Dispatch: sequential under 64, parallel above.
    if n < 64 {
        return Ok((0..n)
            .map(|i| greeks::gamma_scalar(spot, strikes[i], ts[i], sigmas[i], r, q))
            .collect());
    }
    Ok((0..n)
        .into_par_iter()
        .map(|i| greeks::gamma_scalar(spot, strikes[i], ts[i], sigmas[i], r, q))
        .collect())
}

/// Normalize raw chain rows (list of dicts from yfinance/cvforge) into clean
/// contract dicts. Drops invalid strikes/kinds; coerces NaN→0.
#[pyfunction]
fn normalize_chain(
    py: Python<'_>,
    rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
) -> PyResult<PyObject> {
    use pyo3::types::{PyAny, PyDict, PyDictMethods, PyList, PyListMethods};

    fn get_f64(map: &std::collections::HashMap<String, Bound<'_, PyAny>>, name: &str) -> Option<f64> {
        map.get(name).and_then(|v| v.extract::<f64>().ok())
    }
    fn get_str<'a>(map: &'a std::collections::HashMap<String, Bound<'a, PyAny>>, name: &str) -> Option<String> {
        map.get(name).and_then(|v| v.extract::<String>().ok())
    }

    let mut out = Vec::with_capacity(rows.len());
    for map in &rows {
        let strike = get_f64(map, "strike").unwrap_or(0.0);
        if !(strike > 0.0) {
            continue;
        }
        let kind = match get_str(map, "type").unwrap_or_default().to_uppercase().as_str() {
            "C" | "CALL" => "C",
            "P" | "PUT" => "P",
            _ => continue,
        };
        let coerce = |v: Option<f64>| match v {
            Some(x) if x.is_finite() && x > 0.0 => x,
            _ => 0.0,
        };
        let oi = get_f64(map, "oi")
            .or_else(|| get_f64(map, "openInterest"))
            .or_else(|| get_f64(map, "open_interest"));
        let iv = coerce(get_f64(map, "iv").or_else(|| get_f64(map, "impliedVolatility")));

        let d = PyDict::new_bound(py);
        d.set_item("strike", strike)?;
        d.set_item("type", kind)?;
        d.set_item("oi", coerce(oi))?;
        d.set_item("volume", coerce(get_f64(map, "volume")))?;
        d.set_item("iv", iv)?;
        // delta may legitimately be negative — keep sign, drop NaN only
        d.set_item(
            "delta",
            get_f64(map, "delta").filter(|x| x.is_finite()).unwrap_or(0.0),
        )?;
        d.set_item(
            "gamma",
            get_f64(map, "gamma").filter(|x| x.is_finite()).unwrap_or(0.0),
        )?;
        out.push(d);
    }
    Ok(PyList::new_bound(py, &out).into_any().unbind())
}

fn parse_contracts(
    rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
) -> Vec<RawContract> {
    rows.into_iter()
        .map(|m| {
            let gf = |name: &str| -> f64 {
                m.get(name).and_then(|v| v.extract::<f64>().ok()).unwrap_or(f64::NAN)
            };
            let kind = m
                .get("type")
                .and_then(|v| v.extract::<String>().ok())
                .map(|s| s.to_ascii_lowercase())
                .unwrap_or_default();
            RawContract {
                strike: gf("strike"),
                kind: if kind.starts_with('c') { 'c' } else { 'p' },
                oi: gf("oi"),
                iv: gf("iv"),
                t: gf("T"),
            }
        })
        .collect()
}

fn row_to_dict<'py>(py: Python<'py>, r: &StrikeRow) -> PyResult<pyo3::Bound<'py, pyo3::types::PyDict>> {
    use pyo3::types::PyDict;
    use pyo3::types::PyDictMethods;
    let d = PyDict::new_bound(py);
    d.set_item("strike", r.strike)?;
    d.set_item("gex", r.gex)?;
    d.set_item("call_gex", r.call_gex)?;
    d.set_item("put_gex", r.put_gex)?;
    d.set_item("call_oi", r.call_oi)?;
    d.set_item("put_oi", r.put_oi)?;
    d.set_item("total_oi", r.total_oi)?;
    d.set_item("vex", r.vex)?;
    d.set_item("vega", r.vega)?;
    d.set_item("charm", r.charm)?;
    d.set_item("vomma", r.vomma)?;
    d.set_item("zomma", r.zomma)?;
    Ok(d)
}

/// Per-strike GEX — parity with services/gex_core.compute_gex_by_strike.
/// contracts: list of dicts with keys strike/type/oi/iv/T. div_yield: e.g. 0.013 for SPY.
#[pyfunction]
#[pyo3(signature = (spot, contracts, div_yield=0.0))]
fn compute_gex_by_strike(
    py: Python<'_>,
    spot: f64,
    contracts: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
    div_yield: f64,
) -> PyResult<PyObject> {
    use pyo3::types::PyList;
    let raw = parse_contracts(contracts);
    let rows = gex::compute_gex_by_strike(spot, &raw, div_yield);
    let dicts: Vec<_> = rows.iter().map(|r| row_to_dict(py, r)).collect::<PyResult<_>>()?;
    Ok(PyList::new_bound(py, &dicts).into_any().unbind())
}

/// Zero-gamma flip levels from per-strike GEX rows.
#[pyfunction]
fn zero_gamma_levels(py: Python<'_>, rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;
    let parsed: Vec<StrikeRow> = rows
        .iter()
        .map(|m| StrikeRow {
            strike: m.get("strike").and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0),
            gex: m.get("gex").and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0),
            ..Default::default()
        })
        .collect();
    let levels = gex::zero_gamma_levels(&parsed);
    Ok(PyList::new_bound(py, &levels).into_any().unbind())
}


/// Term-structure analysis — parity with gex_term_structure.compute_gex_term_structure
/// (analysis fields; paper_metrics computed Python-side).
///
/// Columnar input: parallel lists strike/gamma/oi/kind/tte ("T"TE). Columnar
/// avoids 6×N dict lookups — ~10x binding overhead win vs the dict version.
#[pyfunction]
#[pyo3(signature = (spot, strikes, gammas, ois, kinds, ttes))]
fn term_structure_columns(
    py: Python<'_>,
    spot: f64,
    strikes: Vec<f64>,
    gammas: Vec<f64>,
    ois: Vec<f64>,
    kinds: Vec<String>,
    ttes: Vec<f64>,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;

    let n = strikes.len();
    let raw: Vec<term::TermContract> = (0..n)
        .map(|i| term::TermContract {
            time_to_expiry: ttes[i],
            strike: strikes[i],
            kind: if kinds[i].to_uppercase().starts_with('P') { 'p' } else { 'c' },
            gamma: gammas[i],
            oi: ois[i],
        })
        .collect();
    let ta = term::term_analysis(spot, &raw);

    let d = PyDict::new_bound(py);
    d.set_item("regime", ta.regime)?;
    d.set_item("interpretation", ta.interpretation)?;
    d.set_item("expiries", PyList::new_bound(py, &ta.expiries))?;
    d.set_item(
        "net_gex_by_expiry",
        PyList::new_bound(py, &ta.net_gex_by_expiry),
    )?;
    d.set_item("term_structure_slope", ta.slope)?;
    d.set_item("calendar_spread_impact", ta.calendar_spread_impact)?;
    d.set_item("slope_ratio", ta.slope_ratio)?;
    Ok(d.into_any().unbind())
}

/// Dict-based variant retained for compatibility.
#[pyfunction]
fn term_structure(
    py: Python<'_>,
    spot: f64,
    contracts: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;

    let raw: Vec<term::TermContract> = contracts
        .iter()
        .map(|m| {
            let gf = |name: &str| -> f64 {
                m.get(name).and_then(|v| v.extract::<f64>().ok()).unwrap_or(f64::NAN)
            };
            let kind = m
                .get("type")
                .and_then(|v| v.extract::<String>().ok())
                .map(|s| {
                    let c = s.trim().to_ascii_uppercase();
                    if c.starts_with("P") { 'p' } else { 'c' }
                })
                .unwrap_or('c');
            term::TermContract {
                time_to_expiry: gf("time_to_expiry"),
                strike: gf("strike"),
                kind,
                gamma: gf("gamma"),
                oi: gf("oi"),
            }
        })
        .collect();
    let ta = term::term_analysis(spot, &raw);

    let d = PyDict::new_bound(py);
    d.set_item("regime", ta.regime)?;
    d.set_item("interpretation", ta.interpretation)?;
    d.set_item("expiries", PyList::new_bound(py, &ta.expiries))?;
    d.set_item(
        "net_gex_by_expiry",
        PyList::new_bound(py, &ta.net_gex_by_expiry),
    )?;
    d.set_item("term_structure_slope", ta.slope)?;
    d.set_item("calendar_spread_impact", ta.calendar_spread_impact)?;
    d.set_item("slope_ratio", ta.slope_ratio)?;
    Ok(d.into_any().unbind())
}

/// Liquidity basins from (strike, gex) pairs.
#[pyfunction]
fn liquidity_basins(
    py: Python<'_>,
    spot: f64,
    strike_gex: Vec<(f64, f64)>,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;
    let basins = term::liquidity_basins(&strike_gex, spot);
    let dicts: Vec<_> = basins
        .iter()
        .map(|b| {
            let d = PyDict::new_bound(py);
            for (k, v) in b {
                d.set_item(k, v)?;
            }
            Ok(d)
        })
        .collect::<PyResult<_>>()?;
    Ok(PyList::new_bound(py, &dicts).into_any().unbind())
}


/// Bulk Volume Classification over a trade batch — parity with
/// VpinEngine.classify_volume. Returns (buy[], sell[]).
#[pyfunction]
#[pyo3(signature = (price_changes, volumes, dt=1.0))]
fn classify_volume(
    price_changes: Vec<f64>,
    volumes: Vec<f64>,
    dt: f64,
) -> PyResult<(Vec<f64>, Vec<f64>)> {
    match vpin::classify_volume(&price_changes, &volumes, dt) {
        Ok(c) => Ok((c.buy, c.sell)),
        Err(e) => Err(PyValueError::new_err(e)),
    }
}

/// Rolling VPIN from finalized buckets — parity with _recompute_vpin.
#[pyfunction]
fn vpin_from_buckets(buy: Vec<f64>, sell: Vec<f64>, total: Vec<f64>) -> f64 {
    vpin::vpin_from_buckets(&buy, &sell, &total)
}


/// Batch ingestion: full trade stream → (bucket dicts, vpin series).
/// Parity with the per-trade VpinEngine.update() loop, minus Mongo/prometheus.
#[pyfunction]
#[pyo3(signature = (price_changes, volumes, timestamps, sigmas, dt=1.0, bucket_size=50000.0, window=50))]
fn ingest_batch(
    py: Python<'_>,
    price_changes: Vec<f64>,
    volumes: Vec<f64>,
    timestamps: Vec<f64>,
    sigmas: Vec<f64>,
    dt: f64,
    bucket_size: f64,
    window: usize,
) -> PyResult<(PyObject, Vec<f64>)> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;
    match vpin::ingest_batch(&price_changes, &volumes, &timestamps, &sigmas, dt, bucket_size, window) {
        Err(e) => Err(PyValueError::new_err(e)),
        Ok((buckets, vpins)) => {
            let dicts: Vec<_> = buckets
                .iter()
                .map(|b| {
                    let d = PyDict::new_bound(py);
                    d.set_item("bucket_id", b.bucket_id)?;
                    d.set_item("start_time", b.start_time)?;
                    d.set_item("end_time", b.end_time)?;
                    d.set_item("total_volume", b.total_volume)?;
                    d.set_item("buy_volume", b.buy_volume)?;
                    d.set_item("sell_volume", b.sell_volume)?;
                    Ok(d)
                })
                .collect::<PyResult<_>>()?;
            Ok((PyList::new_bound(py, &dicts).into_any().unbind(), vpins))
        }
    }
}


/// Implied vol solver — parity with bs_greeks.implied_vol_from_price.
#[pyfunction]
#[pyo3(signature = (market_price, s, k, t, kind="call", q=0.0, r=0.045, tol=1e-6, max_iter=50))]
fn implied_vol_from_price(
    market_price: f64, s: f64, k: f64, t: f64,
    kind: &str, q: f64, r: f64, tol: f64, max_iter: u32,
) -> f64 {
    let is_call = !kind.to_ascii_lowercase().starts_with('p');
    iv::implied_vol(market_price, s, k, t, is_call, q, r, tol, max_iter)
}

/// Batch IV surface — columnar inputs, parallel above 64 rows.
#[pyfunction]
#[pyo3(signature = (market_prices, spots, strikes, ts, kinds, qs=None, rs=None, tol=1e-6, max_iter=50))]
fn implied_vol_surface(
    market_prices: Vec<f64>, spots: Vec<f64>, strikes: Vec<f64>, ts: Vec<f64>,
    kinds: Vec<bool>,
    qs: Option<Vec<f64>>, rs: Option<Vec<f64>>,
    tol: f64, max_iter: u32,
) -> PyResult<Vec<f64>> {
    let n = market_prices.len();
    let qs = qs.unwrap_or_else(|| vec![0.0; n]);
    let rs = rs.unwrap_or_else(|| vec![0.045; n]);
    if spots.len() != n || strikes.len() != n || ts.len() != n || kinds.len() != n
        || qs.len() != n || rs.len() != n {
        return Err(PyValueError::new_err("column length mismatch"));
    }
    Ok(iv::implied_vol_surface(&market_prices, &spots, &strikes, &ts, &kinds, &qs, &rs, tol, max_iter))
}


/// Realized-volatility estimators over OHLC+prev_close bars.
/// Columnar inputs; NaN = invalid field (mirrors _safe_positive_float filter).
/// Returns dict with cc/parkinson/garman_klass/rogers_satchell/yang_zhang
/// (None where insufficient bars).
#[pyfunction]
#[pyo3(signature = (opens, highs, lows, closes, prev_closes, annual_factor=252.0))]
fn realized_volatility(
    py: Python<'_>,
    opens: Vec<f64>, highs: Vec<f64>, lows: Vec<f64>, closes: Vec<f64>,
    prev_closes: Vec<f64>, annual_factor: f64,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict};
    use pyo3::types::PyDictMethods;
    let n = opens.len();
    if highs.len() != n || lows.len() != n || closes.len() != n {
        return Err(PyValueError::new_err("column length mismatch"));
    }
    // prev_closes may be empty or shorter → treat missing as NaN
    let pc = |i: usize| -> f64 {
        prev_closes.get(i).copied().unwrap_or(f64::NAN)
    };
    let bars: Vec<rvol::Bar> = (0..n)
        .map(|i| rvol::Bar {
            open: opens[i], high: highs[i], low: lows[i],
            close: closes[i], prev_close: pc(i),
        })
        .collect();
    let [cc, park, gk, rs, yz] = rvol::realized_vol_all(&bars, annual_factor);
    let d = PyDict::new_bound(py);
    for (name, v) in [
        ("close_to_close", cc), ("parkinson", park), ("garman_klass", gk),
        ("rogers_satchell", rs), ("yang_zhang", yz),
    ] {
        match v {
            Some(x) => d.set_item(name, x)?,
            None => d.set_item(name, py.None())?,
        }
    }
    Ok(d.into_any().unbind())
}


/// GEX node classification — parity with gex_core.classify_nodes.
/// rows: list of dicts with strike/gex/vex/vega/charm/vomma/zomma/
/// call_gex/put_gex/call_oi/put_oi/total_oi.
#[pyfunction]
fn classify_nodes(
    py: Python<'_>,
    rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
    spot: f64,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;

    let gf = |m: &std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>, name: &str| -> f64 {
        m.get(name).and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0)
    };
    let parsed: Vec<gex::StrikeRow> = rows
        .iter()
        .map(|m| gex::StrikeRow {
            strike: gf(m, "strike"),
            gex: gf(m, "gex"),
            call_gex: gf(m, "call_gex"),
            put_gex: gf(m, "put_gex"),
            call_oi: gf(m, "call_oi"),
            put_oi: gf(m, "put_oi"),
            total_oi: gf(m, "total_oi"),
            call_vex: gf(m, "call_vex"),
            put_vex: gf(m, "put_vex"),
            vex: gf(m, "vex"),
            vega: gf(m, "vega"),
            charm: gf(m, "charm"),
            vomma: gf(m, "vomma"),
            zomma: gf(m, "zomma"),
        })
        .collect();

    let n = match nodes::classify_nodes(&parsed, spot) {
        Some(n) => n,
        None => return Ok(py.None()),
    };

    let d = PyDict::new_bound(py);
    // king
    let king = PyDict::new_bound(py);
    king.set_item("strike", n.king_strike)?;
    king.set_item("gex", n.king_gex)?;
    d.set_item("king", king)?;

    let pairs_list = |py: Python<'_>, v: &[(f64, f64)]| -> PyResult<PyObject> {
        let items: Vec<_> = v
            .iter()
            .map(|(s, g)| {
                let x = PyDict::new_bound(py);
                x.set_item("strike", s)?;
                x.set_item("gex", g)?;
                Ok(x)
            })
            .collect::<PyResult<_>>()?;
        Ok(PyList::new_bound(py, &items).into_any().unbind())
    };
    d.set_item("floors", pairs_list(py, &n.floors)?)?;
    d.set_item("ceilings", pairs_list(py, &n.ceilings)?)?;
    d.set_item("gatekeepers", PyList::new_bound(py, &n.gatekeepers))?;

    let aps: Vec<_> = n
        .air_pockets
        .iter()
        .map(|(lo, hi, w)| {
            let x = PyDict::new_bound(py);
            x.set_item("low", lo)?;
            x.set_item("high", hi)?;
            x.set_item("width", w)?;
            x.set_item("mid", (lo + hi) / 2.0)?;
            Ok(x)
        })
        .collect::<PyResult<_>>()?;
    d.set_item("air_pockets", PyList::new_bound(py, &aps))?;

    d.set_item("polarity_level", n.polarity_level)?;
    d.set_item("regime", n.regime)?;
    d.set_item("total_gex", n.total_gex)?;
    d.set_item("near_gex", n.near_gex)?;
    d.set_item("vex_flip", n.vex_flip)?;

    let stacked: Vec<_> = n
        .stacked
        .iter()
        .map(|(s, cp, pp)| {
            let x = PyDict::new_bound(py);
            x.set_item("strike", s)?;
            x.set_item("call_pct", (cp * 100.0).round() / 100.0)?;
            x.set_item("put_pct", (pp * 100.0).round() / 100.0)?;
            Ok(x)
        })
        .collect::<PyResult<_>>()?;
    d.set_item("stacked_nodes", PyList::new_bound(py, &stacked))?;

    let tows: Vec<_> = n
        .tug_of_war
        .iter()
        .map(|(lo, hi, pos, neg)| {
            let x = PyDict::new_bound(py);
            x.set_item("low", lo)?;
            x.set_item("high", hi)?;
            x.set_item("positive", pos)?;
            x.set_item("negative", neg)?;
            Ok(x)
        })
        .collect::<PyResult<_>>()?;
    d.set_item("tug_of_war", PyList::new_bound(py, &tows))?;

    for (k, v) in [
        ("total_vega", n.total_vega), ("total_charm", n.total_charm),
        ("total_vomma", n.total_vomma), ("total_zomma", n.total_zomma),
        ("charm_flip", n.charm_flip),
    ] {
        d.set_item(k, v)?;
    }
    match n.max_pain {
        Some(mp) => d.set_item("max_pain", mp)?,
        None => d.set_item("max_pain", py.None())?,
    }
    match n.max_pain {
        Some(_) => d.set_item("max_pain_basis", "call_put_intrinsic_expiry_scoped")?,
        None => d.set_item("max_pain_basis", "unavailable")?,
    }
    match n.put_call_ratio {
        Some(r) => d.set_item("put_call_ratio", (r * 10000.0).round() / 10000.0)?,
        None => d.set_item("put_call_ratio", py.None())?,
    }
    d.set_item("_spot", (spot * 100.0).round() / 100.0)?;

    let rm = PyDict::new_bound(py);
    rm.set_item("gci", n.gci)?;
    rm.set_item("pgr", n.pgr)?;
    rm.set_item("gdw", n.gdw)?;
    let car_net = if n.total_gex < 0.0 { -1.0 } else { 1.0 }
        * (0.6 * n.total_zomma + 0.4 * n.total_vomma);
    let car_gross = 0.6 * n.total_zomma.abs() + 0.4 * n.total_vomma.abs();
    rm.set_item("car_net", (car_net * 10000.0).round() / 10000.0)?;
    rm.set_item("car_gross", (car_gross * 10000.0).round() / 10000.0)?;
    rm.set_item("charm_risk", (n.total_charm * 10000.0).round() / 10000.0)?;
    d.set_item("risk_metrics", rm)?;

    Ok(d.into_any().unbind())
}


/// Aggregate GEX curve — parity with gex_core.calc_aggregate_gex_curve.
/// Columnar input; returns list of {price, gex} dicts (gex in billions).
#[pyfunction]
#[pyo3(signature = (spot, strikes, ois, ivs, ts, kinds, div_yield=0.0))]
fn aggregate_gex_curve(
    py: Python<'_>,
    spot: f64,
    strikes: Vec<f64>, ois: Vec<f64>, ivs: Vec<f64>, ts: Vec<f64>,
    kinds: Vec<String>, div_yield: f64,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;
    let n = strikes.len();
    let raw: Vec<curve::CurveContract> = (0..n)
        .map(|i| curve::CurveContract {
            strike: strikes[i], oi: ois[i], iv: ivs[i], t: ts[i],
            is_call: !kinds[i].to_ascii_lowercase().starts_with('p'),
        })
        .collect();
    let curve = curve::aggregate_gex_curve(spot, &raw, div_yield);
    let items: Vec<_> = curve
        .iter()
        .map(|(price, gex)| {
            let x = PyDict::new_bound(py);
            x.set_item("price", price)?;
            x.set_item("gex", gex)?;
            Ok(x)
        })
        .collect::<PyResult<_>>()?;
    Ok(PyList::new_bound(py, &items).into_any().unbind())
}


/// 2D GEX grid — parity with gex_core.compute_gex_grid.
/// Columnar; returns {expiries, strikes, grid, charm_grid, vex_grid, strike_totals}.
#[pyfunction]
#[pyo3(signature = (spot, strikes, ts, ois, ivs, kinds, expiries, div_yield=0.0, weight_volume=false))]
fn compute_gex_grid(
    py: Python<'_>,
    spot: f64,
    strikes: Vec<f64>, ts: Vec<f64>, ois: Vec<f64>, ivs: Vec<f64>,
    kinds: Vec<bool>, expiries: Vec<String>, div_yield: f64,
    weight_volume: bool,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;

    let out = match grid::compute_gex_grid(spot, &strikes, &ts, &ois, &ivs, &kinds, &expiries, div_yield, weight_volume) {
        Some(g) => g,
        None => {
            let d = PyDict::new_bound(py);
            d.set_item("expiries", PyList::empty_bound(py))?;
            d.set_item("strikes", PyList::empty_bound(py))?;
            d.set_item("grid", PyDict::new_bound(py))?;
            d.set_item("charm_grid", PyDict::new_bound(py))?;
            d.set_item("vex_grid", PyDict::new_bound(py))?;
            d.set_item("strike_totals", PyList::empty_bound(py))?;
            return Ok(d.into_any().unbind());
        }
    };

    let fmt_key = |k: f64| -> String {
        if k.fract() == 0.0 { format!("{}", k as i64) } else { format!("{}", k) }
    };

    // build nested dicts: expiry → strike-key → value
    let build_grid = |py: Python<'_>,
                      pick: fn(&(usize, usize), f64, f64, f64) -> f64|
     -> PyResult<PyObject> {
        let outer = PyDict::new_bound(py);
        for (e_idx, e_name) in out.expiries.iter().enumerate() {
            let inner = PyDict::new_bound(py);
            for ((ce, cs), gex, charm, vex) in &out.cells {
                if *ce != e_idx { continue; }
                let skey = fmt_key(out.strikes[*cs]);
                // merge: multiple contracts share a strike key; sum values
                let existing = inner.get_item(skey.as_str()).ok().flatten()
                    .and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
                let key = (*ce, *cs);
                let val = existing + pick(&key, *gex, *charm, *vex);
                inner.set_item(skey, val)?;
            }
            outer.set_item(e_name, inner)?;
        }
        Ok(outer.into_any().unbind())
    };

    let grid_d = build_grid(py, |_, gex, _, _| gex)?;
    let charm_d = build_grid(py, |_, _, charm, _| charm)?;
    let vex_d = build_grid(py, |_, _, _, vex| vex)?;

    let d = PyDict::new_bound(py);
    d.set_item("expiries", PyList::new_bound(py, &out.expiries))?;
    d.set_item("strikes", PyList::new_bound(py, &out.strikes))?;
    d.set_item("grid", grid_d)?;
    d.set_item("charm_grid", charm_d)?;
    d.set_item("vex_grid", vex_d)?;
    let st: Vec<_> = out
        .strike_totals
        .iter()
        .map(|(s, g)| {
            let x = PyDict::new_bound(py);
            x.set_item("strike", s)?;
            x.set_item("gex", g)?;
            Ok(x)
        })
        .collect::<PyResult<_>>()?;
    d.set_item("strike_totals", PyList::new_bound(py, &st))?;
    Ok(d.into_any().unbind())
}


/// Risk-neutral probability distribution — parity with
/// gex_core.calc_probability_distribution. Columnar input.
#[pyfunction]
#[pyo3(signature = (spot, strikes, kinds, ivs, ts, risk_free_rate=0.05))]
fn probability_distribution(
    py: Python<'_>,
    spot: f64,
    strikes: Vec<f64>,
    kinds: Vec<bool>,
    ivs: Vec<f64>,
    ts: Vec<f64>,
    risk_free_rate: f64,
) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;
    let rows = probdist::probability_distribution(spot, &strikes, &kinds, &ivs, &ts, risk_free_rate);
    let dicts: Vec<_> = rows
        .iter()
        .map(|r| {
            let d = PyDict::new_bound(py);
            d.set_item("strike", r.strike)?;
            d.set_item("prob_above", r.prob_above)?;
            d.set_item("prob_below", r.prob_below)?;
            d.set_item("delta", r.delta)?;
            d.set_item("iv", r.iv)?;
            Ok(d)
        })
        .collect::<PyResult<_>>()?;
    Ok(PyList::new_bound(py, &dicts).into_any().unbind())
}

#[pymodule]
fn decoder_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(bs_gamma, m)?)?;
    m.add_function(wrap_pyfunction!(gamma_batch, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_chain, m)?)?;
    m.add_function(wrap_pyfunction!(compute_gex_by_strike, m)?)?;
    m.add_function(wrap_pyfunction!(zero_gamma_levels, m)?)?;
    m.add_function(wrap_pyfunction!(term_structure, m)?)?;
    m.add_function(wrap_pyfunction!(liquidity_basins, m)?)?;
    m.add_function(wrap_pyfunction!(term_structure_columns, m)?);
    m.add_function(wrap_pyfunction!(classify_volume, m)?);
    m.add_function(wrap_pyfunction!(vpin_from_buckets, m)?);
    m.add_function(wrap_pyfunction!(ingest_batch, m)?);
    m.add_function(wrap_pyfunction!(implied_vol_from_price, m)?);
    m.add_function(wrap_pyfunction!(implied_vol_surface, m)?);
    m.add_function(wrap_pyfunction!(realized_volatility, m)?);
    m.add_function(wrap_pyfunction!(classify_nodes, m)?);
    m.add_function(wrap_pyfunction!(aggregate_gex_curve, m)?);
    m.add_function(wrap_pyfunction!(compute_gex_grid, m)?);
    m.add_function(wrap_pyfunction!(probability_distribution, m)?);
    Ok(())
}
