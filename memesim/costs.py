"""How a pretend trade is filled. Models a constant-product AMM pool (x*y=k), which is how
Raydium / PumpSwap pools work: the bigger your trade vs the pool, the worse your price."""
from .config import Settings


def buy_fill(usd: float, price: float, liquidity_usd: float, s: Settings) -> tuple[float, float]:
    """Spend `usd` -> returns (tokens received, total cost in USD including network fee)."""
    side = liquidity_usd / 2                       # USD-side reserve of the pool
    into_pool = usd * (1 - s.dex_fee_pct / 100)
    impact = 1 + into_pool / side                  # average price paid vs spot
    paid_price = price * impact * (1 + s.latency_slip_pct / 100)
    return into_pool / paid_price, usd + s.network_fee_usd


def sell_fill(tokens: float, price: float, liquidity_usd: float, s: Settings) -> float:
    """Sell all `tokens` -> returns USD received after impact, fees and network fee."""
    side = max(liquidity_usd / 2, 1e-9)
    value = tokens * price * (1 - s.latency_slip_pct / 100)
    value = value * side / (side + value)          # price impact
    value *= 1 - s.dex_fee_pct / 100
    return max(0.0, value - s.network_fee_usd)
