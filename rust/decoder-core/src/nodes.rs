//! GEX node classification — Rust port of
//! `backend/services/gex_core.py::classify_nodes` (1728µs Python on ~200 rows).
//!
//! Parity contract: same king/floors/ceilings/gatekeepers/air_pockets/
//! stacked/tug-of-war/max-pain/risk-metric logic, thresholds (0.15, 0.08,
//! 0.2/0.2, 0.02, 0.03), rounding to 4dp, and the exact output key set.

use crate::gex::StrikeRow;
use rayon::prelude::*;

#[derive(Debug, Clone)]
pub struct NodesOut {
    pub king_strike: f64,
    pub king_gex: f64,
    pub floors: Vec<(f64, f64)>,    // (strike, gex)
    pub ceilings: Vec<(f64, f64)>,
    pub gatekeepers: Vec<f64>,      // strikes
    pub air_pockets: Vec<(f64, f64, usize)>, // low, high, width (mid derived)
    pub polarity_level: f64,
    pub regime: &'static str,
    pub total_gex: f64,
    pub near_gex: f64,
    pub vex_flip: f64,
    pub stacked: Vec<(f64, f64, f64)>, // strike, call_pct, put_pct
    pub tug_of_war: Vec<(f64, f64, f64, f64)>, // low, high, pos, neg
    pub total_vega: f64,
    pub total_charm: f64,
    pub total_vomma: f64,
    pub total_zomma: f64,
    pub charm_flip: f64,
    pub max_pain: Option<f64>,
    pub put_call_ratio: Option<f64>,
    pub gci: f64,
    pub pgr: f64,
    pub gdw: f64,
}

fn round4(x: f64) -> f64 {
    (x * 10000.0).round() / 10000.0
}

fn finite_or_zero(x: f64) -> f64 {
    if x.is_finite() { x } else { 0.0 }
}

/// Classify GEX nodes from per-strike rows. `rows` must be sorted by strike.
pub fn classify_nodes(rows: &[StrikeRow], spot: f64) -> Option<NodesOut> {
    if rows.is_empty() || spot <= 0.0 || !spot.is_finite() {
        return None;
    }

    // King = max |gex|
    let king = rows.iter().fold(rows[0].clone(), |a, b| {
        if b.gex.abs() > a.gex.abs() { b.clone() } else { a }
    });
    let max_abs = king.gex.abs().max(1e-12);

    let mut floors: Vec<(f64, f64)> = rows
        .iter()
        .filter(|s| s.strike < spot && s.gex > 0.0)
        .map(|s| (s.strike, s.gex))
        .collect();
    floors.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    floors.truncate(5); // parity: python returns floors[:5]

    let mut ceilings: Vec<(f64, f64)> = rows
        .iter()
        .filter(|s| s.strike > spot && s.gex > 0.0)
        .map(|s| (s.strike, s.gex))
        .collect();
    ceilings.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    ceilings.truncate(5); // parity: python returns ceilings[:5]

    let gk_threshold = 0.15 * max_abs;
    let gatekeepers: Vec<f64> = if (king.strike - spot).abs() > f64::EPSILON {
        let (lo, hi) = if spot < king.strike { (spot, king.strike) } else { (king.strike, spot) };
        let mut gks: Vec<(f64, f64)> = rows
            .iter()
            .filter(|s| s.strike > lo && s.strike < hi && s.strike != king.strike)
            .filter(|s| s.gex.abs() >= gk_threshold)
            .map(|s| (s.strike, s.gex.abs()))
            .collect();
        gks.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        gks.into_iter().map(|(s, _)| s).collect()
    } else {
        vec![]
    };

    // Air pockets: runs of ≥3 consecutive weak rows (< 8% of max_abs)
    let ap_threshold = 0.08 * max_abs;
    let mut air_pockets: Vec<(f64, f64, usize)> = vec![];
    let mut run_strikes: Vec<f64> = vec![];
    for s in rows {
        if s.gex.abs() < ap_threshold {
            run_strikes.push(s.strike);
        } else if !run_strikes.is_empty() {
            if run_strikes.len() >= 3 {
                let lo = run_strikes.iter().cloned().fold(f64::INFINITY, f64::min);
                let hi = run_strikes.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
                air_pockets.push((lo, hi, run_strikes.len()));
            }
            run_strikes.clear();
        }
    }
    if !run_strikes.is_empty() && run_strikes.len() >= 3 {
        let lo = run_strikes.iter().cloned().fold(f64::INFINITY, f64::min);
        let hi = run_strikes.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        air_pockets.push((lo, hi, run_strikes.len()));
    }

    let total_gex: f64 = rows.iter().map(|s| s.gex).sum();
    let near_gex: f64 = rows
        .iter()
        .filter(|s| ((s.strike - spot).abs()) / spot < 0.02)
        .map(|s| s.gex)
        .sum();
    let regime = if total_gex > 0.0 { "positive" } else if total_gex < 0.0 { "negative" } else { "neutral" };

    let total_abs_gex: f64 = rows.iter().map(|s| s.gex.abs()).sum();
    let polarity = if total_abs_gex > 0.0 {
        rows.iter().map(|s| s.strike * s.gex.abs()).sum::<f64>() / total_abs_gex
    } else {
        spot
    };

    let total_abs_vex: f64 = rows.iter().map(|s| s.vex.abs()).sum();
    let vex_flip = if total_abs_vex > 0.0 {
        rows.iter().map(|s| s.strike * s.vex.abs()).sum::<f64>() / total_abs_vex
    } else {
        spot
    };

    // Stacked nodes: within 3% of spot, both-side participation 20/20
    let stacked: Vec<(f64, f64, f64)> = rows
        .iter()
        .filter(|s| (s.strike - spot).abs() / spot <= 0.03)
        .filter_map(|s| {
            let total = s.call_gex.abs() + s.put_gex.abs();
            if total > 0.0 {
                let call_pct = s.call_gex.abs() / total;
                let put_pct = s.put_gex.abs() / total;
                if call_pct > 0.2 && put_pct > 0.2 {
                    return Some((s.strike, call_pct, put_pct));
                }
            }
            None
        })
        .collect();

    // Tug of war: adjacent near-spot strikes with opposite sign
    let mut near: Vec<&StrikeRow> = rows
        .iter()
        .filter(|s| (s.strike - spot).abs() / spot < 0.03)
        .collect();
    near.sort_by(|a, b| a.strike.partial_cmp(&b.strike).unwrap_or(std::cmp::Ordering::Equal));
    let mut tug_of_war: Vec<(f64, f64, f64, f64)> = vec![];
    for i in 1..near.len() {
        let a = near[i - 1];
        let bb = near[i];
        if (a.gex > 0.0 && bb.gex < 0.0) || (a.gex < 0.0 && bb.gex > 0.0) {
            tug_of_war.push((
                a.strike,
                bb.strike,
                if a.gex > 0.0 { a.gex } else { bb.gex },
                if a.gex < 0.0 { a.gex } else { bb.gex },
            ));
        }
    }

    let total_vega = finite_or_zero(rows.iter().map(|s| s.vega).sum());
    let total_charm = finite_or_zero(rows.iter().map(|s| s.charm).sum());
    let total_vomma = finite_or_zero(rows.iter().map(|s| s.vomma).sum());
    let total_zomma = finite_or_zero(rows.iter().map(|s| s.zomma).sum());

    let total_abs_charm: f64 = rows.iter().map(|s| s.charm.abs()).sum();
    let charm_flip = if total_abs_charm > 0.0 {
        rows.iter().map(|s| s.strike * s.charm.abs()).sum::<f64>() / total_abs_charm
    } else {
        spot
    };

    // Max pain (parity with Python classify_nodes): expiry-scoped call/put
    // intrinsic payoff — call OI * max(test - strike, 0) + put OI *
    // max(strike - test, 0), minimized over candidate settle strikes.
    // The old total-OI * |distance| statistic is NOT max pain. O(n²).
    let strike_set: Vec<f64> = {
        let mut v: Vec<f64> = rows.iter().map(|s| s.strike).collect();
        v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        v.dedup();
        v
    };
    let max_pain: Option<f64> = if !strike_set.is_empty() {
        let best = strike_set
            .par_iter()
            .map(|&test| {
                let pain: f64 = rows
                    .iter()
                    .map(|s| {
                        s.call_oi * (test - s.strike).max(0.0)
                            + s.put_oi * (s.strike - test).max(0.0)
                    })
                    .sum();
                (pain, test)
            })
            .min_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
        best.map(|(_, t)| t)
    } else {
        None
    };

    let total_call_oi: f64 = rows.iter().map(|s| s.call_oi).sum();
    let total_put_oi: f64 = rows.iter().map(|s| s.put_oi).sum();
    let put_call_ratio = if total_call_oi > 0.0 { Some(total_put_oi / total_call_oi) } else { None };

    let total_abs = rows.iter().map(|s| s.gex.abs()).sum::<f64>().max(1e-12);
    let gamma_shares: Vec<f64> = rows.iter().map(|s| s.gex.abs() / total_abs).collect();
    let gci: f64 = gamma_shares.iter().map(|s| s * s).sum();

    let gdw_decay = 20.0;
    let near_spot = 20.0;
    let gamma_near: f64 = rows
        .iter()
        .filter(|s| (s.strike - spot).abs() <= near_spot)
        .map(|s| s.gex.abs())
        .sum();
    let pgr = if total_abs > 0.0 { gamma_near / total_abs } else { 0.0 };

    let gdw: f64 = rows
        .iter()
        .map(|s| s.gex.abs() * (-(s.strike - spot).abs() / gdw_decay).exp())
        .sum();

    Some(NodesOut {
        king_strike: king.strike,
        king_gex: king.gex,
        floors,
        ceilings,
        gatekeepers,
        air_pockets,
        polarity_level: round4(polarity),
        regime,
        total_gex: round4(total_gex),
        near_gex: round4(near_gex),
        vex_flip: round4(vex_flip),
        stacked,
        tug_of_war,
        total_vega: round4(total_vega),
        total_charm: round4(total_charm),
        total_vomma: round4(total_vomma),
        total_zomma: round4(total_zomma),
        charm_flip: round4(charm_flip),
        max_pain,
        put_call_ratio,
        gci: round4(gci),
        pgr: round4(pgr),
        gdw: round4(gdw),
    })
}
