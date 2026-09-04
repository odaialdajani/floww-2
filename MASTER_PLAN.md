# CONFLUENCER DECODER — MASTER PLAN

## Current Status: Research & Development Phase
## Goal: Build the ultimate free options trading intelligence platform

---

## ✅ COMPLETED FEATURES

### Data Sources (All Free)
- [x] Finnhub — real-time quotes, news, earnings (60/min)
- [x] Alpha Vantage — RSI, MACD, SMA, EMA, BBANDS (500/day)
- [x] Polygon.io — ticker details, options contracts (5/min)
- [x] FlashAlpha — GEX, DEX, VEX, CHEX, flow, earnings VRP, max pain (81 endpoints)
- [x] yfinance — unlimited fallback for chains and spot prices
- [x] Databento — historical options data ($125 credits)
- [x] Barchart OnDemand — quotes, options, fundamentals, news (cloned, not yet integrated)

### Trading Tools
- [x] GEX calculator with gamma flip detection
- [x] Options flow detector (sweeps, blocks, unusual volume)
- [x] Alert system (7 alert types)
- [x] Trade journal with P&L tracking
- [x] Position sizing calculator
- [x] Trade entry templates (5 strategies)
- [x] Morning briefing with pre-market checklist
- [x] Daily trading checklist API

### AI Features
- [x] Gemini AI trade analysis
- [x] FlashAlpha exposure narrative
- [x] Social sentiment analysis (VADER + TextBlob)

### Broker Integration
- [x] Alpaca paper trading ($100K account, options level 3)
- [x] Schwab API scaffold (waiting on user access)

### Infrastructure
- [x] MongoDB Atlas (cloud database)
- [x] FastAPI backend (34+ routes)
- [x] React frontend (15+ components)
- [x] WebSocket live GEX streaming
- [x] Rate limiting, CORS, file logging
- [x] 24/24 tests passing
- [x] GitHub Actions CI/CD pipeline
- [x] Docker setup

---

## 🔜 NEXT PRIORITIES

### Phase 1: Real-Time Data & Alerts (MOST IMPORTANT)
1. Set up cron job to fetch GEX data every 5 minutes
2. Run alert engine on each snapshot
3. WebSocket push notifications to frontend
4. Store alerts in MongoDB with history
5. Alert sound/visual notification in browser

### Phase 2: Options Flow Monitor
1. Integrate FlashAlpha flow endpoints (live, blocks, sweeps)
2. Build real-time flow ticker component
3. Filter by premium size, volume/OI ratio
4. Color-code bullish/bearish flow
5. Add to dashboard sidebar

### Phase 3: Advanced GEX Dashboard
1. Multiple GEX calculation methods side-by-side
2. GEX surface visualization (strike × expiry)
3. Historical GEX chart
4. Compare GEX across tickers (SPY vs QQQ vs IWM)
5. GEX regime history and statistics

### Phase 4: Paper Trading Automation
1. Connect alert signals to Alpaca order placement
2. Auto-trade based on GEX regime + flow signals
3. Paper trading journal with auto-filled trades
4. Performance tracking and statistics
5. Risk management rules (max position size, stop losses)

### Phase 5: Mobile & Notifications
1. Mobile-responsive dashboard
2. Browser push notifications for HIGH alerts
3. Daily briefing email
4. End-of-day summary with AI coaching

### Phase 6: Deployment
1. Deploy to Azure ($100 credit)
2. Custom domain (Namecheap free domain)
3. SSL certificate
4. Production monitoring

---

## 📊 API KEYS STATUS

### Working
- [x] Finnhub: <REDACTED — see backend/.env; rotate this key, it was committed>
- [x] Alpha Vantage: 5RZUH1L9369493X8
- [x] Polygon.io: LYlNC8d907kAZEpNrIIZK48s1GmBYP2B
- [x] FlashAlpha: wq0ZTRntxMsWwlL1O1XXcFT4YSjBFDvciQYLHnHy
- [x] Alpaca: PKTEX672DYLUZD2Q4DIZPYHVTT / 2Lq89Z1NhFHcctKbSyegEegn6BYVrUdrJ11YZ3Xntp1P
- [x] Gemini: AIzaSyDmkOeu0XZuj_lJgf52rL19_Ni8yp5Bzvs (quota exhausted, student pack coming)
- [x] MongoDB Atlas: hermesterminal / fwBdadhctVpkG9TN
- [x] Databento: db-PBRQ7ia8dQ8wi6Yj7imWDfxXxGFrN

- [x] MarketStack: 2936a82c56aaab09794b1889b5e8147d

### Pending
- [ ] Barchart OnDemand API key (need to sign up at barchartondemand.com)
- [ ] Gemini student pack credits (2-3 days)
- [ ] Charles Schwab API access (user is applying)

---

## 🎯 KEY RESEARCH FINDINGS

### Best Free Data Sources (Ranked)
1. **FlashAlpha** — 81 endpoints, GEX/DEX/VEX/CHEX/flow/earnings, free tier available
2. **Finnhub** — real-time quotes, news, 60/min free
3. **Alpha Vantage** — technical indicators, 500/day free
4. **Polygon.io** — options contracts, 5/min free
5. **yfinance** — unlimited, unofficial, good fallback
6. **Barchart OnDemand** — quotes, options, fundamentals (need API key)

### Best Open Source Projects (Researched)
1. **neeleshroy2023/gex-alerts** — Signal detection engine (adapted for our alert system)
2. **FlashAlpha-lab/flashalpha-python** — Full options analytics SDK
3. **Matteo-Ferrara/gex-tracker** — GEX calculation from CBOE data
4. **Proshotv2/Gamma-Vanna-Exposure** — Gamma/Vanna exposure with Tradier
5. **Buzzfund/UnusualOptions** — UOA detection with Yahoo Finance
6. **shirosaidev/stocksight** — Twitter sentiment analysis
7. **jasti/Stock-Predictor** — ML-based stock prediction from tweets
8. **FullStackCraft/floe** — TypeScript options analytics library
9. **iAmGiG/gex-llm-patterns** — LLM + GEX pattern analysis
10. **michael-kupa/options-flow** — Next.js options flow dashboard

### Alert Strategy (From Research)
- Compare GEX snapshots over time (5-min intervals)
- HIGH priority: gamma flip, gamma squeeze, momentum extreme
- MEDIUM priority: wall breach, GEX magnitude shift, flip proximity
- LOW priority: pin risk
- Volume spike detection at near-ATM strikes
- Only alert on HIGH priority for actionable signals

### GEX Calculation Methods
1. **Standard**: GEX = gamma × OI × spot × 0.01 (calls positive, puts negative)
2. **Vanna-adjusted**: Include vanna exposure for vol regime changes
3. **DEX**: Delta exposure for directional hedging pressure
4. **CHEX**: Charm exposure for time decay effects
5. **FlashAlpha**: Proprietary calculation (use their API)

---

## 💡 TRADING STRATEGIES TO IMPLEMENT

### Based on GEX Regime
- **Positive Gamma**: Sell premium (iron condors, strangles), mean reversion
- **Negative Gamma**: Buy premium (straddles, strangles), momentum trades
- **Transitioning**: Reduce size, wait for clarity

### Based on Flow Signals
- **Sweep orders**: Follow the smart money direction
- **Large blocks**: Institutional positioning, potential support/resistance
- **Unusual volume**: Early signal of upcoming price movement

### Based on Combined Signals
- GEX negative + bearish flow + momentum < 20 = Strong bearish
- GEX positive + bullish flow + momentum > 80 = Strong bullish
- Gamma flip + volume spike = Potential breakout

---

## 📝 NOTES

- User wants everything free/cheap
- User has Azure $100, AWS $100, GitHub Student Pack
- User is applying for Charles Schwab API and X API
- Gemini student pack credits coming in 2-3 days
- Don't deploy yet — user wants more research first
- Focus on building features that help with actual trading decisions
- JetBrains tools for development (PyCharm, DataGrip, WebStorm)
