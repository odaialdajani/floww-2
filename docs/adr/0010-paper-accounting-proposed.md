# Paper accounting clarification

Status: Proposed, awaiting owner decision. Does not edit or supersede the accepted backtest decision yet.
Date: 2026-09-11

The Lodestar revision-4 plan requires a clarifying accounting decision before sharing accounting logic or shipping the paper book. ADR-0003 embeds slippage in the fill and deducts it again as cash, despite describing that as a single economic deduction. Its numerical example also subtracts both.

Proposed rule for the separate Lodestar paper book: slippage appears once, in the actual simulated fill price. Deduct explicit fees once. Do not deduct the same slippage again as cash. Preserve existing backtest results and mark their different convention; this proposal does not authorize rewriting historical results.

Independent example, one standard 100-share option contract:

| Event | Calculation | Cash |
| --- | --- | --- |
| Start | Initial cash | $1,000.00 |
| Buy | $2.05 fill x 100, plus $0.65 fee | $794.35 |
| Mark at entry fill | Cash + $205.00 holding | Equity $999.35 |
| Sell | $2.45 fill x 100, less $0.65 fee | $1,038.70 |
| Final result | ($2.45 - $2.05) x 100 - $1.30 | +$38.70 |

If the original mid references were $2.00 and $2.50, the fills already include $10.00 total adverse slippage. Deducting another $10.00 would incorrectly produce $28.70.

Signed fill invariant: cash change = -signed quantity x verified premium price factor x fill price - fees. Marked equity = cash + signed marked holdings. Buying-power reservations are separate from cash and holdings. Unknown lifecycle state cannot erase holdings or release reservations.

Until accepted, paper actions remain disabled. Research, evidence, UI work, proposal validation and offline arithmetic verification can proceed. No live authorization is requested or granted here.
