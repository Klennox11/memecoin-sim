"""Every rule the bots use, in one place. Change numbers here to experiment."""
from dataclasses import dataclass


@dataclass
class Settings:
    # --- account
    start_balance: float = 1_000.0      # fake USD
    position_usd: float = 50.0          # size of each pretend buy
    max_positions: int = 5

    # --- SCANNER
    chain: str = "solana"
    scan_every_s: int = 20              # DexScreener allows ~60 requests/min on this endpoint

    # --- RISK (a token must pass ALL of these)
    min_liquidity_usd: float = 15_000   # thin pools = huge slippage and easy rugs
    min_age_min: float = 10             # skip the first minutes (snipers + instant rugs)
    max_age_h: float = 24
    min_sells_1h: int = 15              # proof that real people CAN sell
    min_sell_buy_ratio: float = 0.25    # sells / buys; near zero smells like a honeypot
    max_top10_pct: float = 35.0         # top 10 wallets (excluding the pool) may own at most 35%
    min_lp_locked_pct: float = 80.0     # liquidity must be locked or burned
    max_rugcheck_score: int = 50        # RugCheck normalised risk score 0-100 (lower = safer); 0 = unknown
    risk_check_every_s: float = 2.0     # be polite to the RugCheck API

    # --- TRADER (entry signal on a token that passed risk)
    min_m5_change_pct: float = 2.0      # price up at least 2% in the last 5 minutes
    min_m5_volume_usd: float = 2_000
    max_pos_vs_liquidity: float = 0.02  # never buy more than 2% of the pool
    watch_minutes: int = 30             # how long an approved token stays on the buy list

    # --- EXITS
    take_profit_pct: float = 40.0
    stop_loss_pct: float = 20.0
    trail_start_pct: float = 15.0       # once up 15%...
    trail_pct: float = 12.0             # ...sell if it falls 12% from its best price
    max_hold_min: float = 30.0
    rug_liq_drop_pct: float = 50.0      # liquidity fell by half since we bought -> get out
    exit_check_every_s: float = 5.0

    # --- COSTS (what makes the results honest)
    dex_fee_pct: float = 0.25           # Raydium / PumpSwap pool fee, each trade
    network_fee_usd: float = 0.05       # Solana base + priority fee per transaction
    latency_slip_pct: float = 1.0       # price moves against you before your tx lands (bots are faster)
