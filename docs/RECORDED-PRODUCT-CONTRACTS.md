# Recorded wall curves and second-order displays

Numeric/display baseline reviewed November 1, 2026 against backend tree `65950f82bb4794cb3bffe067c8849315064e33e8`.
Status: the raw stored same-wall curve is implemented and mounted; the adjusted/window curve and the DUO/DVO displays remain display/read contract design. Producer/storage/consumer implementation for those remains unclaimed. Capture and commissioning remain off.

## Existing engineering and the remaining gap

`services/heatmap_history.py` records full versioned grids, observation identity, contracts and selected display context. `compare_snapshots` performs a bounded comparison between comparable stored observations. Its coarse wall added/removed/retained summary is not a retained-wall activity curve.

The coarse comparison separately exposes `volume_comparisons` for every recorded strike and `volume_coverage` counts for comparable, increased, unchanged, missing, invalid and decreased volume. Its existing `volume_deltas` remains the positive-only top20 ranking; ranking length is not total coverage. Missing/invalid inputs and decreases return null deltas with explicit reasons. These are stored cumulative option-contract volume differences, not positioning or adjusted wall activity. Replay shows the coverage; older or inconsistent responses remain coverage-unknown.

`services/solstice_window.py` already checks declared ticker/provider/scope/formula/session identity, observation order, availability order and complete baseline population. Its recorded-window producer uses stored baseline inputs and refuses volume retractions. A new curve must consume those established semantics.

`domain/second_order_exposure.py` has independent numeric DUO/DVO helpers, mirrored metadata in `domain/exposure_metrics.py`, and finite-difference oracle tests. Those helpers currently have no mounted production display caller. Their inherited registry text is not a sufficient display contract: the DUO derivative variable is dollar spot, although the label names percent moves; the prose also says per-contract while the helper already multiplies supplied OI. DVO needs both its dollar-vega numerator convention and sigma scale stated explicitly. Existing IDs and arithmetic must not be silently relabeled or rescaled.

The older `unified/RECORDED-CURVE-SPEC.md` describes a separate aggregate GEX recording product. Its resolutions and activation checklist do not make the wall product implemented, and its old scope is not permission to activate collection.

## Wall curve: `recorded-wall-curve.v1`

One series owns one raw structural wall, selected scope and metric. Its key includes ticker, canonical query key, provider, session, formula version, raw wall ID and wall-definition version. An adjusted weighting never replaces the raw-wall anchor. A representative strike or a matching screen position is insufficient identity.

Each point needs:

- Observation ID and snapshot content digest separately; unchanged content can have distinct observation times.
- Exact loaded expiry dates and requested scope, raw wall ID/bounds and the recorded membership/definition identity.
- Metric ID, exposure basis, formula/model versions, numerator/denominator units and any declared scaling.
- Event, receipt and availability clocks. All must be eligible for the replay decision cutoff; later receipt is not retroactive knowledge.
- Typed value/status, source, quality and population coverage. Preserve measured zero, missing, invalid, unavailable and partial as distinct states.
- For a window point: both observation IDs and clocks, interval, comparison identity, requested/returned/eligible populations, exclusions and retraction policy.

Read only the stored same-wall value or a documented projection of admitted stored values. Do not fetch a current chain, refresh spot, recompute historical Greeks or borrow another symbol/scope to fill a point. Missing older fields produce an unavailable point with its reason. A sparse point is not a complete wall measurement.

Wall creation/removal, definition changes, session/scope/provider changes and incomparable observations break the line. Do not connect points across a gap, forward-fill removed walls or silently follow whichever wall is strongest now. Any explicit wall handoff creates a separately identified series.

Window activity must reuse `recorded_window_activity` comparability and frozen producer inputs. A difference in session volume alone is insufficient. A negative cumulative-volume change remains a retraction; no clamp to zero. An unavailable or partial interval must expose its baseline, coverage and reason instead of presenting one precise full-population value.

Resampling may select admitted stored observations under a declared policy. It must retain gaps and identity, and must not invent missing intervals. Aggregate GEX, same-wall adjusted exposure and window activity keep separate axes and units.

## DUO: derivative and move contribution

Keep the existing numeric definition:

`G(S) = C * S² * gamma(S)`, with `C = OI * multiplier * 0.01` fixed during spot differentiation.

`G''(S) = C * (S² * gamma''(S) + 4S * gamma'(S) + 2gamma(S))`.

A raw display must say **second spot derivative of dollar GEX**, with denominator **spot-dollar squared** and the existing dollar-GEX numerator convention stated. It is not automatically a derivative with respect to percent moves. It also already incorporates the supplied OI and multiplier; do not multiply those again or describe the result as one contract.

A requested move in spot dollars, `dS`, has second-order contribution `0.5 * G''(S) * dS²`. If the UI accepts whole percentage points `p`, first convert `dS = S * p / 100` using that record's eligible spot. A percent-normalized coefficient would be `G''(S) * (0.01S)²`; it requires a different declared display ID/scale. Keep the factor one-half in the contribution, not in the derivative.

Do not restore the old shortcut containing only `gamma'' * OI * multiplier * (0.01S)²`. The oracle specifically checks the missing product-rule terms. A contribution is a local modeled change in the GEX observable, not an observed option return or a trade outcome.

## DVO: numerator and volatility scale

Keep the existing numeric definition `W(sigma) = bs_vega(sigma) * OI * multiplier` and `W'(sigma) = vomma * OI * multiplier`, with decimal sigma as the derivative variable. The canonical `bs_vega` oracle uses unscaled unit-sigma vega.

The display must name the numerator **dollar vega under the unit-sigma convention**, rather than reuse an ambiguous bare dollar label. Differentiating that vega quantity gives a derivative per additional unit sigma; in option-value derivative bookkeeping this is option dollars per sigma squared. Record both the numerator convention and derivative variable in machine-readable fields.

A whole volatility-point input `v` means `dSigma = v / 100`. The local change in dollar vega is `W'(sigma) * dSigma`. A second-order option-value contribution is a different quantity, `0.5 * W'(sigma) * dSigma²`; it must have a separate ID and label. Do not confuse either with canonical VEX, apply an extra spot factor, or treat a unit-sigma move as one volatility point.

## Admission and compatibility

New displays require a versioned display descriptor with observable, derivative variable/order, raw units, move units and scale, contribution formula, OI/multiplier conventions, model version and source clocks. Legacy registry entries stay compatible; they do not by themselves admit a new display. A consumer without this descriptor stays unavailable.

Inputs must be finite and record-owned, with valid multiplier provenance, explicit OI/Greek availability and exact scope. Older helpers returning zero for invalid or expired inputs do not prove a measured zero; admission occurs before numeric evaluation. Missing stored second-order inputs cannot be repaired with today's model outputs.

## Implementation acceptance boundary

Before any implementation can be marked delivered, independently verify:

1. Same content at different observation times retains both observations; duplicates do not duplicate one observation.
2. Wall lifecycle/definition changes and partial or mismatched scope create explicit gaps.
3. Late receipts and unavailable-at-cutoff observations are excluded without live substitutes.
4. Retractions, missing baselines and incomplete populations keep their distinct refusals.
5. DUO raw/Taylor/percent conversions and DVO raw/volatility-point/contribution conversions match independent lower-order numerical differences with nonstandard valid multipliers.
6. Missing/invalid input cannot become measured zero, and the raw/adjusted/window/second-order axes cannot be substituted for one another.
7. A mounted consumer preserves the same IDs, clocks, units and gaps end to end. Numeric helper tests alone do not establish this.

The November1 focused run passed15 existing derivative/registry checks. It confirms the current numerical oracle/registry behavior, including the legacy labels pinned by those tests; it does not certify the future display descriptor or wall-curve implementation above.

## Verified raw same-wall curve slice (November 2, 2026)

The raw stored same-wall curve above is implemented as `recorded-wall-curve.v1` in `backend/services/solstice_wall_curve.py` and mounted at `GET /api/solstice/wall-curve/{ticker}` (commit `97f89dbb`). It reads stored observations only.

What the implementation does:

- Keys the series by ticker, canonical query key, scope id, provider, session date, formula version, raw wall ID, wall-definition version and metric ID.
- Requires a declared `query_key`. An undeclared scope is refused with `SCOPE_UNVERIFIED`; it is never widened to the newest scope of the day.
- Carries the observation ID and the content digest separately, so the same content observed twice is two points.
- Derives the session day from the stored event clock in New York time, not from the UTC day.
- Enforces event ≤ receipt ≤ availability. A later receipt is not retroactive knowledge: an observation outside the cutoff is excluded.
- Breaks the line and records an explicit gap for wall creation/removal, definition change, session roll, scope change and provider change. A removed wall is never forward-filled and a neighbouring wall is never joined.
- Keeps missing, invalid, unavailable, partial and a measured zero apart. An unusable population is `VALUE_UNAVAILABLE`, never a zero; a truncated snapshot is `COVERAGE_TRUNCATED`; an unstored metric is `METRIC_NOT_STORED`.
- Serves only the stored raw families (`dadgex_net_v1`, `dadgex_gross_v1`, `volume_gamma_v1`, `session_delta_volume_gamma_v1`). The registry IDs are `dadgex_*` while the stored field names are `daddex_*`; the mapping is explicit and an unsupported ID is refused rather than approximated.
- Keeps a negative cumulative change as a retraction. It is never clamped to zero.

Verification run on November 2, 2026: 21 service checks in `backend/tests/services/test_recorded_wall_curve.py` and 4 mounted-route checks in `backend/tests/solstice/test_wall_curve_route.py` pass, together with the API-doc freshness checks (33 checks in that run); `ruff` is clean on the changed files.

Still unclaimed: the adjusted/window curve, the DUO/DVO displays and their display descriptor, and any second-order display admission. Items 5 and 6 of the acceptance boundary above remain design-only. The window point identity, comparison identity and retraction policy in this document are not implemented by the raw slice.
