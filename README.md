# MEMECOIN-SIM

An **honest** memecoin paper-trading simulator. No wallet, no keys, no real money.

Inspired by social-media posts like "4 bots turned $118 into $6,903", which usually turn out
to be simulated trades with no fees. This project builds the same 4-bot idea, but charges
realistic costs, and its results show how hard this really is.

## The 4 bots
| Bot | Job |
|---|---|
| **SCANNER** | Polls DexScreener's free public feeds for newly listed Solana tokens every 5 s; tokens too new to judge are re-checked once they're 10 min old |
| **RISK** | Rejects a token unless it passes **every** check: liquidity >= $15k, age 10 min to 24 h, mint authority revoked, freeze authority revoked (otherwise you may be unable to sell), real sells happening (honeypot check), top-10 wallets own <= 35%, liquidity >= 80% locked/burned, RugCheck risk score <= 50 |
| **TRADER** | Pretend-buys an approved token when it has momentum (up >= 2% in 5 min, more buys than sells, >= $2k volume). Max 5 positions, never more than 2% of the pool |
| **EXITS** | Pretend-sells on take profit (+40%), stop loss (-20%), trailing stop (-12% from peak once up 15%), 30-minute time limit, or a rug (liquidity drops 50%) |

## Honest costs on every trade
- 0.25% DEX pool fee each way
- **Price impact** from a constant-product (x*y=k) pool model: bigger trades vs. pool = worse price
- 1% latency slippage each way (faster bots get there first)
- $0.05 Solana network/priority fee per transaction

Even so, real results would likely be **worse**: failed transactions, MEV sandwich attacks,
and DexScreener data that is seconds old.

All rules live in `memesim/config.py`; change the numbers to experiment.

## Run it (Windows PowerShell)
```powershell
uv run main.py run --demo       # fake market: see the bots work right away
uv run main.py run              # live data (DexScreener + RugCheck), fake money
uv run main.py report           # summary: win rate, best/worst, how trades ended
uv run main.py reset            # wipe the paper wallet
```
Press **Ctrl+C** to stop. The wallet is saved in `paper_wallet.db`.

## Data sources (free, no API key)
- DexScreener: `token-profiles/latest/v1`, `token-boosts/latest/v1`, `tokens/v1/{chain}/{addresses}`
- RugCheck: `v1/tokens/{mint}/report`
