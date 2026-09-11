# Discord Ops Setup — SOLSTICE bot (gamma/vanna desk) + Alpaca paper

This bot is **Solstice-specialized**: dealer positioning first — `!heatmap`,
`!vanna`, `!walls` render GEX/VEX pictures on request — paper trading second
(`!buy/!sell/!approve/!holdings`, Alpaca paper only, hardcoded, no live path).
A separate Tidehunter flow bot comes later.

## 1. Create the bot (5 min, Discord side)

1. Go to https://discord.com/developers/applications → **New Application** → name it (e.g. `Tidehunter`).
2. **Bot** → **Reset Token** → copy it → this is `DISCORD_BOT_TOKEN` (never commit it).
3. **Bot** → enable **Message Content Intent** (required for `!` commands).
4. **OAuth2 → URL Generator** → scopes `bot` (+ `applications.commands` if you add slash commands later) → bot permissions: **Send Messages**, **Embed Links**, **Read Message History** → open the URL → invite to your server.
5. Right-click your server name → **Server Settings → Widget** or enable **Developer Mode** (User Settings → Advanced), then right-click your own username → **Copy User ID** → this is `DISCORD_ALLOWED_USER_IDS`.

## 2. Alert webhook (alerts-out)

1. Server Settings → **Integrations → Webhooks** → New Webhook → pick the channel (e.g. `#flow`) → **Copy Webhook URL** → `DISCORD_WEBHOOK_URL`.

## 3. Env (backend/.env — gitignored, never chat these values)

```bash
DISCORD_BOT_TOKEN=<paste>
DISCORD_WEBHOOK_URL=<paste>
DISCORD_ALLOWED_USER_IDS=<your numeric user id>
DISCORD_MIN_TIER=GOLD                 # GOLD only by default
DISCORD_RULES=OICONF,WHALE,SCORE,PRIME
ALPACA_API_KEY=<paper key from app.alpaca.markets/paper/dashboard/overview>
ALPACA_SECRET_KEY=<paper secret>
```

Empty allowlist = trading commands denied for everyone (read-only still works).

## 4. Run

```bash
cd backend
.venv/bin/python3 discord_bot.py     # separate process; backend boots without it
```

Persistence across reboots (macOS launchd — secrets stay in `backend/.env`,
which the bot loads itself; nothing secret in the plist):

```bash
cp deploy/ai.tidehunter.discord-bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/ai.tidehunter.discord-bot.plist
# check: tail -f /tmp/tidehunter-discord-bot.log
# stop:  launchctl unload ~/Library/LaunchAgents/ai.tidehunter.discord-bot.plist
```

Verify wiring without Discord open: `GET /api/discord/status` (booleans only)
and `POST /api/discord/test` (posts a ping; both behind the API key).

## 5. Commands

Solstice (works for everyone, no allowlist needed):
`!heatmap <TICKER>` — GEX ladder picture (walls, flip, King Node)
`!vanna <TICKER>` — VEX (vomma exposure) picture
`!walls <TICKER>` — call/put walls, flip, regime readout

Paper trading (allowlisted only):
`!buy <qty> <SYM> [limit <px>]` · `!sell <qty> <SYM>` · `!bracket <buy|sell> <qty> <SYM> <tp%> <sl%>` (entry + TP/SL legs, prices from live quote)
`!approve <alert-key> [qty]` · `!close <SYM>` · `!cancel <order-id>`
`!holdings` · `!orders` · `!pnl` · `!risk` · `!journal [n]` · `!audit [n]`
`!alerts [n]` · `!help [solstice|trading|portfolio|ops]`
Aliases: h pos/p a hm w v j p x. Plain `spy walls` (no `!`) works for reads;
trading never triggers without the prefix. Unknown commands get a
did-you-mean suggestion. Picture commands cool down 20s per user
(paid-chain budget). Big alert sweeps arrive as digests (≤3 messages, top
conviction first, approve keys kept) — Discord caps webhooks at ~30/min.

Alert embeds carry the approve key: `!approve score|SPY|call|745|2099-01-08 2`
buys 2 shares of SPY on Alpaca paper (direction from alert bias).
Every executed trade is journaled as an **equity** seed (type=equity, ref px
in notes — never mislabeled as an option contract) so position memory and
the lifecycle tracker follow it to exit. Same for UI/API trades via
`POST /api/alpaca/order` (source tags: `discord-approve` / `api-alpaca`).
