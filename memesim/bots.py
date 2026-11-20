"""The four bots. Each one does one job and writes what it's doing to its own log panel.

  SCANNER  finds newly listed tokens
  RISK     throws out likely scams / rug pulls (must pass EVERY rule)
  TRADER   makes a pretend buy when an approved token shows momentum
  EXITS    makes a pretend sell at take-profit / stop-loss / trailing stop / timeout / rug
"""
import time
from collections import deque
from dataclasses import dataclass, field

from .config import Settings
from .costs import buy_fill, sell_fill
from .wallet import PaperWallet

BOTS = ("SCANNER", "RISK", "TRADER", "EXITS")


@dataclass
class Board:
    """Shared 'whiteboard' the bots write to and the dashboard reads from."""
    logs: dict = field(default_factory=lambda: {b: deque(maxlen=8) for b in BOTS})
    status: dict = field(default_factory=lambda: {b: "starting" for b in BOTS})
    counts: dict = field(default_factory=lambda: dict(seen=0, checked=0, rejected=0, approved=0, bought=0))
    reject_reasons: dict = field(default_factory=dict)
    queue: deque = field(default_factory=deque)       # found by scanner, waiting for risk check
    seen: set = field(default_factory=set)
    approved: dict = field(default_factory=dict)      # address -> (symbol, approved_at)
    started: float = field(default_factory=time.time)
    errors: int = 0

    def log(self, bot: str, msg: str, style: str = "white") -> None:
        if self.logs[bot] and self.logs[bot][-1][1] == msg:  # don't spam the same line
            return
        self.logs[bot].append((time.strftime("%H:%M:%S"), msg, style))


def scanner(feed, b: Board) -> None:
    b.status["SCANNER"] = "scanning"
    new = [a for a in feed.latest_tokens() if a not in b.seen]
    for a in new:
        b.seen.add(a)
        b.queue.append(a)
    b.counts["seen"] += len(new)
    b.log("SCANNER", f"{len(new)} new token(s) found, {len(b.queue)} waiting for RISK", "cyan" if new else "grey50")
    b.status["SCANNER"] = "idle"


def risk_check(pair: dict | None, safety: dict | None, s: Settings) -> list[str]:
    """Return a list of failed rules. Empty list = passed."""
    if pair is None:
        return ["no trading pair yet"]
    if safety is None:
        return ["no RugCheck data (unknown = unsafe)"]
    fails = []
    age_min = (time.time() * 1000 - pair["created_ms"]) / 60_000 if pair["created_ms"] else -1
    if pair["liquidity"] < s.min_liquidity_usd:
        fails.append(f"liquidity ${pair['liquidity']:,.0f} < ${s.min_liquidity_usd:,.0f}")
    if age_min < s.min_age_min:
        fails.append(f"too new ({age_min:.0f} min)")
    elif age_min > s.max_age_h * 60:
        fails.append(f"too old ({age_min / 60:.0f} h)")
    if safety["rugged"]:
        fails.append("already rugged")
    if safety["mint_authority"]:
        fails.append("dev can still mint more tokens")
    if safety["freeze_authority"]:
        fails.append("dev can freeze wallets (can't sell)")
    if pair["h1_sells"] < s.min_sells_1h:
        fails.append(f"only {pair['h1_sells']} sells in 1h (can people sell?)")
    elif pair["h1_buys"] and pair["h1_sells"] / pair["h1_buys"] < s.min_sell_buy_ratio:
        fails.append("almost nobody is selling (honeypot?)")
    if safety["top10_pct"] > s.max_top10_pct:
        fails.append(f"top 10 wallets own {safety['top10_pct']:.0f}%")
    if safety["lp_locked_pct"] is None or safety["lp_locked_pct"] < s.min_lp_locked_pct:
        lp = safety["lp_locked_pct"]
        fails.append(f"liquidity not locked ({'?' if lp is None else f'{lp:.0f}%'})")
    if safety["score"] > s.max_rugcheck_score:
        fails.append(f"RugCheck risk score {safety['score']}/100")
    fails += [f"RugCheck: {d}" for d in safety["danger"][:2]]
    return fails


def risk(feed, b: Board, s: Settings) -> None:
    if not b.queue:
        b.status["RISK"] = "idle"
        return
    b.status["RISK"] = "checking"
    addr = b.queue.popleft()
    pair = feed.pairs([addr]).get(addr)
    safety = None
    if pair:
        try:
            safety = feed.safety(addr)
        except Exception as e:
            b.log("RISK", f"RugCheck lookup failed ({type(e).__name__})", "grey50")
    fails = risk_check(pair, safety, s)
    sym = pair["symbol"] if pair else addr[:6]
    b.counts["checked"] += 1
    if fails:
        b.counts["rejected"] += 1
        key = fails[0].split("(")[0].split("$")[0].strip()
        b.reject_reasons[key] = b.reject_reasons.get(key, 0) + 1
        more = f" (+{len(fails) - 1} more)" if len(fails) > 1 else ""
        b.log("RISK", f"REJECT {sym}: {fails[0]}{more}", "red")
    else:
        b.counts["approved"] += 1
        b.approved[addr] = (sym, time.time())
        b.log("RISK", f"PASS {sym}: all safety checks OK -> buy list", "bold green")
    b.status["RISK"] = "idle"


def trader(feed, wallet: PaperWallet, b: Board, s: Settings) -> None:
    now = time.time()
    for a, (sym, t) in list(b.approved.items()):  # forget stale approvals
        if now - t > s.watch_minutes * 60:
            del b.approved[a]
            b.log("TRADER", f"{sym}: no momentum in {s.watch_minutes} min, dropped", "grey50")
    held = {p["address"] for p in wallet.positions()}
    cands = [a for a in b.approved if a not in held]
    if not cands:
        b.status["TRADER"] = "waiting"
        return
    b.status["TRADER"] = "watching"
    pairs = feed.pairs(cands)
    for a in cands:
        p = pairs.get(a)
        if not p:
            continue
        if len(held) >= s.max_positions:
            b.log("TRADER", f"max {s.max_positions} positions open, skipping {p['symbol']}", "grey50")
            break
        if not (p["m5_change"] >= s.min_m5_change_pct and p["m5_buys"] > p["m5_sells"]
                and p["m5_volume"] >= s.min_m5_volume_usd):
            continue
        size = min(s.position_usd, p["liquidity"] * s.max_pos_vs_liquidity, wallet.cash - s.network_fee_usd)
        if size < 5:
            b.log("TRADER", f"not enough cash to buy {p['symbol']}", "red")
            break
        tokens, cost = buy_fill(size, p["price"], p["liquidity"], s)
        wallet.open(p, tokens, cost)
        held.add(a)
        b.approved.pop(a, None)
        b.counts["bought"] += 1
        lost = cost - tokens * p["price"]
        b.log("TRADER", f"BUY {p['symbol']} ${size:,.2f} (+{p['m5_change']:.1f}% 5m) "
                        f"costs ${lost:.2f}", "bold green")
        b.status["TRADER"] = "bought"


def exits(feed, wallet: PaperWallet, b: Board, s: Settings) -> None:
    pos = wallet.positions()
    if not pos:
        b.status["EXITS"] = "idle"
        return
    b.status["EXITS"] = f"guarding {len(pos)}"
    pairs = feed.pairs([p["address"] for p in pos])
    now = time.time()
    for p in pos:
        q = pairs.get(p["address"])
        if q is None:
            continue
        wallet.mark(p["address"], q["price"], q["liquidity"])
        chg = (q["price"] / p["entry_price"] - 1) * 100
        from_peak = (q["price"] / max(p["peak_price"], q["price"]) - 1) * 100
        peak_gain = (max(p["peak_price"], q["price"]) / p["entry_price"] - 1) * 100
        liq_drop = (1 - q["liquidity"] / p["entry_liq"]) * 100 if p["entry_liq"] else 0
        held_min = (now - p["entry_time"]) / 60
        reason = None
        if liq_drop >= s.rug_liq_drop_pct:
            reason = f"RUG! liquidity -{liq_drop:.0f}%"
        elif chg >= s.take_profit_pct:
            reason = f"take profit +{chg:.0f}%"
        elif chg <= -s.stop_loss_pct:
            reason = f"stop loss {chg:.0f}%"
        elif peak_gain >= s.trail_start_pct and from_peak <= -s.trail_pct:
            reason = f"trailing stop ({from_peak:.0f}% from peak)"
        elif held_min >= s.max_hold_min:
            reason = f"time limit {s.max_hold_min:.0f} min"
        if reason:
            proceeds = sell_fill(p["tokens"], q["price"], q["liquidity"], s)
            pnl = wallet.close(p, proceeds, reason)
            b.log("EXITS", f"SELL {p['symbol']}: {reason} -> P&L ${pnl:+,.2f}", "bold green" if pnl > 0 else "bold red")
