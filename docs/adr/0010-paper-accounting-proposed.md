# Paper accounting clarification

Status: Accepted for the separate configurable paper book on 2026-09-26. Historical backtests and ADR-0003 remain unchanged.
Date: 2026-09-11; owner clarification: 2026-09-26 21:44 UTC.

The Lodestar revision-4 plan requires a clarifying accounting decision before sharing accounting logic or shipping the paper book. ADR-0003 embeds slippage in the fill and deducts it again as cash, despite describing that as a single economic deduction. Its numerical example also subtracts both.

The owner requested that slippage be toggleable, then explicitly answered "all options above should be an optino" when asked whether that means on/off or choosing how it is charged. Both controls are required for the separate Lodestar paper book:

- Slippage off: use the eligible executable reference price with no added slippage charge. Explicit fees still apply once.
- Slippage on, worse fill price: move the fill adversely from the eligible reference price; no separate slippage cash charge.
- Slippage on, separate cash charge: keep the eligible reference price as the fill and subtract the equivalent adverse slippage cash charge once.

No mode is silently selected. Account settings and each confirmed proposal must identify the enabled choice, method, declared price-unit increment, fee schedule and version. Turning slippage off retains the selected method for a later toggle but the saved fill records an effective mode of off. Changing settings affects future confirmations/fills only; existing fills keep their immutable accounting choice. The reference is a verified executable quote, not an assumed midpoint. Quote freshness, displayed size, order limits and lifecycle checks remain independent requirements.

Preserve existing backtest results and mark their different convention. This decision does not authorize rewriting historical results or enabling paper/live orders before their other release gates pass.

Independent example, one standard 100-share option contract:

| Event | Calculation | Cash |
| --- | --- | --- |
| Start | Initial cash | $1,000.00 |
| Buy | $2.05 fill x 100, plus $0.65 fee | $794.35 |
| Mark at entry fill | Cash + $205.00 holding | Equity $999.35 |
| Sell | $2.45 fill x 100, less $0.65 fee | $1,038.70 |
| Final result | ($2.45 - $2.05) x 100 - $1.30 | +$38.70 |

If the original mid references were $2.00 and $2.50, the fills already include $10.00 total adverse slippage. Deducting another $10.00 would incorrectly produce $28.70.

For the price method, signed fill invariant: cash change = -signed quantity x verified premium price factor x fill price - fees. For the separate-charge method, subtract the disclosed slippage cash charge once as well; its fill price has no embedded slippage. In either case the economic cost is identical for an equal adverse price-unit increment, before any explicitly declared rounding policy. Marked equity = cash + signed marked holdings. Buying-power reservations are separate from cash and holdings. Unknown lifecycle state cannot erase holdings or release reservations.

The accounting choice is now accepted. Paper actions remain disabled until research/proposal acceptance, verified product/lifecycle behavior, owner-selected account settings and protected human confirmation pass. The owner also requested use of whichever account setup is selected: an existing eligible paper account or a new account with user-provided cash/risk settings; this is not permission to choose a live account or invent capital limits. No live authorization is requested or granted here.
