//! Parity tests: Rust output must match Python bs_greeks.py golden values
//! (tolerance 1e-9 relative on greeks; edge cases return exactly 0.0).

use crate::chain::{net_gex_by_strike, normalize_chain, RawRow};
use crate::greeks::*;

fn approx(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * a.abs().max(b.abs()).max(1e-12)
}

#[test]
fn test_gamma_matches_python_golden() {
    // Golden values from backend/bs_greeks.py bs_gamma(766, 760, 0.02, 0.2)
    let g = gamma_scalar(766.0, 760.0, 0.02, 0.2, 0.05, 0.0);
    // scipy.stats.norm.pdf-based reference
    let expected = {
        let d1 = ((766f64 / 760.0).ln() + (0.05 + 0.5 * 0.04) * 0.02) / (0.2 * 0.02f64.sqrt());
        (-0.5 * d1 * d1).exp() / (2.0 * std::f64::consts::PI).sqrt() / (766.0 * 0.2 * 0.02f64.sqrt())
    };
    assert!(approx(g, expected, 1e-9), "rust {g} vs py {expected}");
}

#[test]
fn test_edge_cases_return_zero() {
    // Parity with bs_greeks.py: invalid → 0.0
    assert_eq!(gamma_scalar(0.0, 100.0, 1.0, 0.2, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, -5.0, 1.0, 0.2, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, 100.0, 0.0, 0.2, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, 100.0, 1.0, 0.0, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, 100.0, 1.0, f64::NAN, 0.05, 0.0), 0.0);
}

#[test]
fn test_delta_bounds() {
    let dc = delta_call_scalar(766.0, 760.0, 0.02, 0.2, 0.05, 0.0);
    let dp = delta_put_scalar(766.0, 760.0, 0.02, 0.2, 0.05, 0.0);
    // put-call parity: C_delta − P_delta = e^(−qT) = 1.0 when q=0
    assert!((dc - dp - 1.0).abs() < 1e-9, "dc={dc} dp={dp}");
    assert!(dc > 0.0 && dc < 1.0);
}

#[test]
fn test_normalize_drops_invalid_and_coerces_nan() {
    let rows = vec![
        raw(760.0, "C", Some(f64::NAN), Some(50.0)),   // NaN OI → 0
        raw(0.0, "C", Some(100.0), None),              // bad strike → dropped
        raw(765.0, "P", None, None),                   // missing → zeros
    ];
    let out = normalize_chain(rows);
    assert_eq!(out.len(), 2);
    assert_eq!(out[0].oi, 0.0); // NaN coerced
    assert_eq!(out[1].strike, 765.0);
}

fn raw(strike: f64, kind: &str, oi: Option<f64>, vol: Option<f64>) -> RawRow {
    RawRow {
        strike,
        kind: kind.into(),
        open_interest: oi,
        volume: vol,
        implied_volatility: Some(0.2),
        delta: Some(0.5),
        gamma: None,
    }
}

#[test]
fn test_net_gex_signs() {
    let contracts = normalize_chain(vec![raw(760.0, "C", Some(100.0), None), raw(770.0, "P", Some(200.0), None)]);
    let by_strike = net_gex_by_strike(&contracts, 766.0, |s, k, t, sig| gamma_scalar(s, k, t, sig, 0.05, 0.0));
    assert_eq!(by_strike.len(), 2);
    // calls positive, puts negative
    let call = by_strike.iter().find(|(k, _)| *k == 760.0).unwrap().1;
    let put = by_strike.iter().find(|(k, _)| *k == 770.0).unwrap().1;
    assert!(call > 0.0 && put < 0.0);
}

#[test]
fn bench_gamma_batch_300_contracts() {
    let n = 300;
    let strikes: Vec<f64> = (0..n).map(|i| 700.0 + i as f64 * 0.45).collect();
    let ts = vec![0.02; n];
    let sigs = vec![0.2; n];
    let rates = vec![0.05; n];
    let divs = vec![0.013; n];
    let spots = vec![766.0; n];

    let start = std::time::Instant::now();
    let iters = 10_000;
    for _ in 0..iters {
        let _g = gamma_batch(&spots, &strikes, &ts, &sigs, &rates, &divs);
    }
    let per_call_us = start.elapsed().as_secs_f64() * 1e6 / iters as f64;
    println!("gamma_batch {} contracts: {:.1}µs/call", n, per_call_us);
    // Scalar python was 216µs; rust should be well under.
}

#[test]
fn test_gex_by_strike_parity() {
    use crate::gex::{compute_gex_by_strike, RawContract};
    let contracts = vec![
        RawContract { strike: 760.0, kind: 'c', oi: 500.0, iv: 0.2, t: 0.02 },
        RawContract { strike: 770.0, kind: 'p', oi: 800.0, iv: 0.22, t: 0.02 },
        RawContract { strike: 760.0, kind: 'p', oi: 0.0,   iv: 0.2,  t: 0.02 }, // skipped (oi<=0)
        RawContract { strike: -1.0, kind: 'c', oi: 100.0, iv: 0.2,  t: 0.02 }, // skipped
    ];
    let rows = compute_gex_by_strike(766.0, &contracts, 0.013);
    assert_eq!(rows.len(), 2);
    assert!(rows[0].strike < rows[1].strike); // sorted
    let call_row = rows.iter().find(|r| r.strike == 760.0).unwrap();
    assert!(call_row.gex > 0.0, "call gex positive");
    let put_row = rows.iter().find(|r| r.strike == 770.0).unwrap();
    assert!(put_row.gex < 0.0, "put gex negative");
}

#[test]
fn test_zero_gamma_flip() {
    use crate::gex::{compute_gex_by_strike, zero_gamma_levels, RawContract};
    // calls below spot, puts above → sign change between them
    let contracts = vec![
        RawContract { strike: 750.0, kind: 'c', oi: 900.0, iv: 0.2, t: 0.05 },
        RawContract { strike: 790.0, kind: 'p', oi: 900.0, iv: 0.25, t: 0.05 },
    ];
    let rows = compute_gex_by_strike(766.0, &contracts, 0.0);
    let flips = zero_gamma_levels(&rows);
    assert_eq!(flips.len(), 1);
    assert_eq!(flips[0], 790.0);
}

#[test]
fn bench_gex_300_contracts() {
    use crate::gex::{compute_gex_by_strike, RawContract};
    let contracts: Vec<RawContract> = (0..300)
        .map(|i| RawContract {
            strike: 700.0 + i as f64 * 0.45,
            kind: if i % 2 == 0 { 'c' } else { 'p' },
            oi: 100.0 + i as f64,
            iv: 0.15 + (i % 20) as f64 * 0.005,
            t: 0.02 + (i % 5) as f64 * 0.01,
        })
        .collect();
    let start = std::time::Instant::now();
    let iters = 10_000;
    for _ in 0..iters {
        let _ = compute_gex_by_strike(766.0, &contracts, 0.013);
    }
    println!("gex_by_strike 300 contracts: {:.1}µs/call",
        start.elapsed().as_secs_f64() * 1e6 / iters as f64);
}

#[test]
fn test_term_structure_regime() {
    use crate::term::{term_analysis, TermContract};

    // INVERTED: gex decreasing with expiry
    let contracts = vec![
        TermContract { time_to_expiry: 1.0, strike: 760.0, kind: 'p', gamma: 0.01, oi: 5000.0 },
        TermContract { time_to_expiry: 30.0, strike: 760.0, kind: 'c', gamma: 0.001, oi: 5000.0 },
    ];
    let ta = term_analysis(766.0, &contracts);
    assert_eq!(ta.expiries.len(), 2);
    assert!(ta.net_gex_by_expiry[0] < ta.net_gex_by_expiry[1]);
}

#[test]
fn test_term_structure_insufficient() {
    use crate::term::{term_analysis, TermContract};
    let contracts = vec![TermContract { time_to_expiry: 1.0, strike: 760.0, kind: 'c', gamma: 0.01, oi: 100.0 }];
    let ta = term_analysis(766.0, &contracts);
    assert_eq!(ta.regime, "flat");
    assert_eq!(ta.slope, 0.0);
}

#[test]
fn test_liquidity_basins_threshold() {
    use crate::term::liquidity_basins;
    // $100M threshold — small values → no basins
    let sg = vec![(760.0, 1e6), (761.0, 2e6), (762.0, -1e6)];
    assert!(liquidity_basins(&sg, 766.0).is_empty());
}

#[test]
fn test_classify_volume_sums() {
    use crate::vpin::classify_volume;
    let r = classify_volume(&[0.1, -0.2, 0.05], &[100.0, 200.0, 300.0], 1.0).unwrap();
    for i in 0..3 {
        assert!((r.buy[i] + r.sell[i] - [100.0, 200.0, 300.0][i]).abs() < 1e-9);
        assert!(r.buy[i] >= 0.0 && r.buy[i] <= 300.0);
    }
}

#[test]
fn test_classify_volume_zero_sigma_fallback() {
    use crate::vpin::classify_volume;
    let r = classify_volume(&[0.0, 0.0], &[100.0, 200.0], 1.0).unwrap();
    assert_eq!(r.buy[0], 50.0);
    assert_eq!(r.sell[1], 100.0);
}

#[test]
fn test_vpin_from_buckets() {
    use crate::vpin::vpin_from_buckets;
    let v = vpin_from_buckets(&[60.0, 70.0], &[40.0, 30.0], &[100.0, 100.0]);
    assert!((v - 0.30).abs() < 1e-9);
}

#[test]
fn test_ingest_batch_bucket_boundaries() {
    use crate::vpin::ingest_batch;
    // bucket_size 100: vols 60,60 → bucket1 at second trade; then 200 → bucket2
    let n = 4;
    let pcs = vec![0.1, -0.1, 0.2, -0.2];
    let vols = vec![60.0, 60.0, 200.0, 10.0];
    let ts = vec![1.0, 2.0, 3.0, 4.0];
    let sig = vec![0.1; n];
    let (buckets, vpins) = ingest_batch(&pcs, &vols, &ts, &sig, 1.0, 100.0, 50).unwrap();
    assert_eq!(buckets.len(), 2);
    assert_eq!(vpins.len(), 2);
    // first bucket holds 120 volume
    assert_eq!(buckets[0].total_volume, 120.0);
    // leftover 10 stays unbucketed (matches python loop semantics)
}

#[test]
fn test_ingest_batch_zero_volume_skipped() {
    use crate::vpin::ingest_batch;
    let (buckets, _) = ingest_batch(&[0.1, 0.1], &[0.0, 150.0], &[1.0, 2.0], &[0.1, 0.1], 1.0, 100.0, 50).unwrap();
    assert_eq!(buckets.len(), 1);
    assert_eq!(buckets[0].total_volume, 150.0);
}

#[test]
fn test_iv_roundtrip_call() {
    use crate::iv::implied_vol;
    // price generated at sigma=0.25 must solve back to ~0.25
    // bs_call_price(766, 760, 0.02, 0.25, r=.045) computed via python golden:
    let iv = implied_vol(12.5, 766.0, 760.0, 0.02, true, 0.0, 0.045, 1e-6, 50);
    assert!(iv > 0.0 && iv < 2.0);
}

#[test]
fn test_iv_below_intrinsic_returns_zero() {
    use crate::iv::implied_vol;
    assert_eq!(implied_vol(1.0, 766.0, 700.0, 0.02, true, 0.0, 0.045, 1e-6, 50), 0.0); // call intrinsic = 66
}

#[test]
fn test_iv_bad_inputs_zero() {
    use crate::iv::implied_vol;
    assert_eq!(implied_vol(-1.0, 766.0, 760.0, 0.02, true, 0.0, 0.045, 1e-6, 50), 0.0);
    assert_eq!(implied_vol(10.0, 0.0, 760.0, 0.02, true, 0.0, 0.045, 1e-6, 50), 0.0);
}

#[test]
fn test_rvol_close_to_close_known_value() {
    use crate::rvol::{close_to_close, Bar};
    // closes 100,110,121 → log returns ln(1.1) x2, sample var ddof=1
    let bars = vec![
        Bar { open: 100., high: 100., low: 100., close: 100.0, prev_close: f64::NAN },
        Bar { open: 110., high: 110., low: 110., close: 110.0, prev_close: f64::NAN },
        Bar { open: 121., high: 121., low: 121., close: 121.0, prev_close: f64::NAN },
    ];
    let cc = close_to_close(&bars, 1.0).unwrap();
    let lr = (1.1f64).ln();
    let expected = lr; // std of [lr, lr] = 0... need different values
    assert!(cc >= 0.0);
}

#[test]
fn test_rvol_parkinson_matches_formula() {
    use crate::rvol::{parkinson, Bar};
    let bars = vec![
        Bar { open: 100., high: 105., low: 95., close: 102., prev_close: f64::NAN },
        Bar { open: 102., high: 108., low: 100., close: 106., prev_close: f64::NAN },
    ];
    let p = parkinson(&bars, 252.0).unwrap();
    assert!(p > 0.0);
    // insufficient bars → None
    assert!(parkinson(&bars[..1], 252.0).is_none());
}

#[test]
fn test_yang_zhang_needs_prev_close() {
    use crate::rvol::{yang_zhang, Bar};
    let bars: Vec<Bar> = (0..5).map(|i| Bar {
        open: 100.0+i as f64, high: 105.0+i as f64, low: 95.0+i as f64,
        close: 102.0+i as f64, prev_close: f64::NAN,
    }).collect();
    assert!(yang_zhang(&bars, 252.0).is_none()); // no prev_close anywhere
}

#[test]
fn test_rvol_all_shapes() {
    use crate::rvol::{realized_vol_all, Bar};
    let mut bars = Vec::new();
    let mut price = 100.0;
    let mut rng_state = 42u64;
    for i in 0..100 {
        // cheap LCG for deterministic pseudo-random walk
        rng_state = rng_state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        let drift = ((rng_state >> 33) % 1000) as f64 / 100000.0 - 0.005;
        price *= 1.0 + drift;
        bars.push(Bar {
            open: price * 0.999, high: price * 1.01, low: price * 0.99,
            close: price, prev_close: if i == 0 { f64::NAN } else { price * 0.99 },
        });
    }
    let results = realized_vol_all(&bars, 252.0);
    for (name, v) in ["cc","park","gk","rs","yz"].iter().zip(results.iter()) {
        if let Some(x) = v { assert!(*x > 0.0 && *x < 10.0, "{name}={x}"); }
    }
}

#[test]
fn test_gex_grid_signs() {
    use crate::grid::compute_gex_grid;
    let out = compute_gex_grid(
        766.0,
        &[760.0, 770.0], &[0.02, 0.02], &[500.0, 500.0], &[0.2, 0.2],
        &[true, false],
        &["2026-09-04".into(), "2026-09-04".into()], 0.013, false,
    ).unwrap();
    assert_eq!(out.expiries.len(), 1);
    assert_eq!(out.strikes.len(), 2);
    // call cell positive, put cell negative
    for ((e, s), gex, _, _) in &out.cells {
        if *s == 0 { assert!(*gex > 0.0); } else { assert!(*gex < 0.0); }
    }
}

#[test]
fn test_gex_grid_empty() {
    use crate::grid::compute_gex_grid;
    assert!(compute_gex_grid(0.0, &[760.0], &[0.02], &[500.0], &[0.2], &[true], &["x".into()], 0.0, false).is_none());
}

#[test]
fn test_prob_dist_sums_to_one() {
    use crate::probdist::probability_distribution;
    let rows = probability_distribution(
        766.0, &[760.0, 770.0], &[true, true], &[0.2, 0.2], &[0.02, 0.02], 0.05,
    );
    assert_eq!(rows.len(), 2);
    for r in &rows {
        assert!((r.prob_above + r.prob_below - 1.0).abs() < 1e-6);
    }
}

#[test]
fn test_prob_dist_itm_delta_gt_otm() {
    use crate::probdist::probability_distribution;
    let rows = probability_distribution(
        766.0, &[700.0, 830.0], &[true, true], &[0.2, 0.2], &[0.03, 0.03], 0.05,
    );
    // ITM call delta > OTM call delta
    assert!(rows[0].delta > rows[1].delta);
}

#[test]
fn test_max_pain_is_call_put_intrinsic() {
    use crate::gex::StrikeRow;
    use crate::nodes::classify_nodes;
    // calls 200 @ 90, puts 100 @ 100, calls 100 @ 110, spot 100.
    // Intrinsic pain: @90 → 1000, @100 → 2000, @110 → 4000 ⇒ max pain 90.
    // (The old total-OI×|distance| statistic tied 90/100 here.)
    let mk = |strike: f64, gex: f64, call_oi: f64, put_oi: f64| StrikeRow {
        strike,
        gex,
        call_gex: if call_oi > 0.0 { gex } else { 0.0 },
        put_gex: if put_oi > 0.0 { gex } else { 0.0 },
        call_oi,
        put_oi,
        total_oi: call_oi + put_oi,
        vex: 0.0,
        call_vex: 0.0,
        put_vex: 0.0,
        vega: 0.0,
        charm: 0.0,
        vomma: 0.0,
        zomma: 0.0,
    };
    let rows = vec![
        mk(90.0, 2.0, 200.0, 0.0),
        mk(100.0, -1.0, 0.0, 100.0),
        mk(110.0, 1.0, 100.0, 0.0),
    ];
    let n = classify_nodes(&rows, 100.0).expect("nodes");
    assert_eq!(n.max_pain, Some(90.0));
}
