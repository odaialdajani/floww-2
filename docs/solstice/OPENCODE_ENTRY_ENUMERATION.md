# Broker-entry enumeration at cb483298 (integration baseline)

Read-only audit, 2026-10-04. Every code path that can reach a broker
order placement, with mount and gate evidence. No code changed.

| # | Caller | Mounted | Broker target | Gate |
|---|---|---|---|---|
| 1 | `routes/public_brokerage.py:473` `broker.place_order` | YES `/api/public` | Public.com LIVE gateway | `FLOWW_ENABLE_LIVE_PUBLIC==1` kill-switch (422-first), then store/policy/approval admission; 403 otherwise, zero placements |
| 2 | `routes/alpaca.py:93` `place_stock_order` | YES `alpaca` | `paper-api.alpaca.markets` hardcoded | Safe by construction (paper host; changing it is forbidden without Nav) |
| 3 | `services/order_router.py:201` via `discord_bot.py:196` | YES `discord` | Alpaca paper only (Schwab path removed, import-guarded by test) | `allow_market=False` default-deny |
| 4 | `routes/flowseeker.py:2248` `engine.submit_order` | YES `flowseeker` | `PaperTradingEngine` (simulated, `server._paper_engine`) | Batch kill-switch trips mid-batch on losing streak; `no_paper_engine` refusal when uninitialized |
| 5 | `routes/paper_trading.py:48` | YES `paper_trading` | `PaperTradingEngine` (simulated) | Simulated fills only |
| 6 | `routes/agentfield_api.py:138` reasoner `submit_order` | YES `/api/agentfield` | Hub reasoner lookup | 503 hub-uninitialized / 404 unregistered; agent tool registry bans order modules/tokens at import |
| 7 | `services/public_execution_lifecycle.py:1277` `submit` | NO route/job caller | Caller-supplied broker arg | `armed=False` default refuses before broker access; approval/preflight/recovery gates |

No cron/retry/replacement job references any placement path
(`recorder_health`, `solstice_price_producer`, `cron_*` clean).
Offline scripts pin `FLOWW_ENABLE_LIVE_PUBLIC="0"`.
`routes/execution_admission.py` mentions the flag in docs only (unmounted).

Consequence for S03: the only LIVE-money path is caller #1, which the
Spark lane hardens; callers #2–#5 are paper/simulated by construction;
#6 has no registered live reasoner; #7 is reachable only in tests.
Wiring the full commissioned pipeline into #1 remains a reviewed named
production change (not done here).
