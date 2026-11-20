"""MEMECOIN-SIM: an honest memecoin paper trader (no wallet, no real money).

    uv run main.py run            live data from DexScreener + RugCheck
    uv run main.py run --demo     fake market, to see the bots work offline
    uv run main.py report         summary of all closed trades
    uv run main.py reset          wipe the paper wallet
"""
import argparse
import time

from rich.live import Live
from rich.table import Table

from memesim.bots import Board, exits, risk, scanner, trader
from memesim.config import Settings
from memesim.feeds import DemoFeed, LiveFeed
from memesim.hud import console, panel, render
from memesim.wallet import DEMO_DB, LIVE_DB, PaperWallet


def cmd_run(a: argparse.Namespace) -> None:
    s = Settings(start_balance=a.balance, position_usd=a.size)
    if a.demo:  # fast-forward the timers so you see action quickly
        s.scan_every_s, s.risk_check_every_s, s.exit_check_every_s = 4, 0.5, 1
        s.min_age_min, s.max_hold_min = 3, 3
    feed = DemoFeed() if a.demo else LiveFeed(s.chain)
    wallet = PaperWallet(s.start_balance, DEMO_DB if a.demo else LIVE_DB)
    if a.demo:
        wallet.reset()
        wallet = PaperWallet(s.start_balance, DEMO_DB)
    b = Board()
    eq_hist: list[float] = []
    last = dict(scan=0.0, risk=0.0, trade=0.0, exit=0.0, eq=0.0)
    stop_at = time.time() + a.minutes * 60 if a.minutes else None

    def safe(name: str, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as e:  # network hiccup, rate limit... log it and keep going
            b.errors += 1
            b.status[name] = "error"
            b.log(name, f"error: {type(e).__name__}: {str(e)[:60]}", "red")

    with Live(console=console, refresh_per_second=2, get_renderable=lambda: render(wallet, b, s, eq_hist, a.demo)):
        try:
            while stop_at is None or time.time() < stop_at:
                now = time.time()
                if now - last["scan"] >= s.scan_every_s:
                    last["scan"] = now
                    safe("SCANNER", scanner, feed, b)
                if now - last["risk"] >= s.risk_check_every_s:
                    last["risk"] = now
                    safe("RISK", risk, feed, b, s)
                if now - last["exit"] >= s.exit_check_every_s:
                    last["exit"] = now
                    safe("EXITS", exits, feed, wallet, b, s)
                if now - last["trade"] >= max(s.exit_check_every_s, 5 if not a.demo else 1):
                    last["trade"] = now
                    safe("TRADER", trader, feed, wallet, b, s)
                if now - last["eq"] >= 5:
                    last["eq"] = now
                    eq_hist.append(wallet.equity())
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
    console.print("[bold cyan]Stopped. Open positions and history are saved; run again to continue, "
                  "or 'uv run main.py report' for a summary.[/]")


def cmd_report(a: argparse.Namespace) -> None:
    w = PaperWallet(1_000, DEMO_DB if a.demo else LIVE_DB)
    st = w.stats()
    t = Table(border_style="cyan", header_style="bold white", style="on black")
    t.add_column("Metric")
    t.add_column("Value", justify="right")
    eq = w.equity()
    rows = [
        ("Starting balance", f"${w.start:,.2f}"), ("Equity now", f"${eq:,.2f}"),
        ("Total P&L", f"${eq - w.start:+,.2f} ({(eq / w.start - 1):+.1%})"),
        ("Closed trades", str(st["n"])),
        ("Win rate", f"{st['wins'] / st['n']:.0%}" if st["n"] else "-"),
        ("Realized P&L", f"${st['pnl']:+,.2f}"),
        ("Best trade", f"{st['best']:+.1f}%" if st["best"] is not None else "-"),
        ("Worst trade", f"{st['worst']:+.1f}%" if st["worst"] is not None else "-"),
        ("Open positions", str(len(w.positions()))),
    ]
    for k, v in rows:
        t.add_row(k, v)
    console.print(panel(t, "MEMECOIN-SIM REPORT" + (" (DEMO)" if a.demo else "")))
    reasons: dict[str, list[float]] = {}
    for tr in w.trades(10_000):
        kind = next((k for k in ("take profit", "stop loss", "trailing stop", "time limit", "RUG")
                     if tr["reason"].startswith(k)), tr["reason"])
        reasons.setdefault(kind, []).append(tr["pnl"])
    if reasons:
        r = Table(border_style="cyan", header_style="bold white", style="on black")
        for c in ("Exit type", "Count", "Total P&L"):
            r.add_column(c, justify="right" if c != "Exit type" else "left")
        for k, v in sorted(reasons.items(), key=lambda kv: -len(kv[1])):
            r.add_row(k, str(len(v)), f"${sum(v):+,.2f}")
        console.print(panel(r, "HOW TRADES ENDED"))


def cmd_reset(a: argparse.Namespace) -> None:
    PaperWallet(1_000, LIVE_DB).reset()
    console.print("[bold green]Paper wallet wiped. Next run starts fresh.[/]")


def main() -> None:
    p = argparse.ArgumentParser(prog="memecoin-sim")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="start the 4 bots + dashboard")
    r.add_argument("--demo", action="store_true", help="fake market (works offline)")
    r.add_argument("--balance", type=float, default=1_000, help="starting fake balance for a NEW wallet")
    r.add_argument("--size", type=float, default=50, help="USD per pretend buy (default 50)")
    r.add_argument("--minutes", type=float, default=None, help="stop automatically after N minutes")
    r.set_defaults(func=cmd_run)
    rp = sub.add_parser("report", help="summary of closed trades")
    rp.add_argument("--demo", action="store_true", help="report on the demo wallet")
    rp.set_defaults(func=cmd_report)
    sub.add_parser("reset", help="wipe the paper wallet").set_defaults(func=cmd_reset)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
