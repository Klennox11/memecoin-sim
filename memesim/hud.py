"""Neon terminal dashboard for the 4 memecoin bots."""
import time

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .bots import Board
from .config import Settings
from .fx import AMBER, CYAN, DIM, GREEN, RED, TEAL, WHITE, banner, blink, chart, gauge, hud_panel, pulse, tape
from .wallet import PaperWallet

console = Console(style="white on black", highlight=False)
NEON = {"green": GREEN, "bold green": f"bold {GREEN}", "cyan": CYAN, "red": RED, "bold red": f"bold {RED}",
        "grey50": DIM, "white": WHITE}
BOT_ROLES = {"SCANNER": "finds new tokens", "RISK": "rejects scams & rugs",
             "TRADER": "pretend buys on momentum", "EXITS": "pretend sells: TP / SL / rug"}


def panel(body, title: str, color: str = "cyan") -> Panel:  # used by the report command
    return hud_panel(body, title)


def tiny(px: float) -> str:
    """Memecoin prices are tiny: 0.0000123 -> $0.0000123"""
    return f"${px:.3g}" if px < 1 else f"${px:,.2f}"


def render(w: PaperWallet, b: Board, s: Settings, eq_hist: list[float], demo: bool) -> Layout:
    W, H = console.size.width, console.size.height
    eq = w.equity()
    pnl = eq - w.start
    up = pnl >= 0
    st = w.stats()
    positions = w.positions()
    c = b.counts
    t_up = int(time.time() - b.started)

    # --- title
    mode = "DEMO MARKET" if demo else "LIVE: DexScreener + RugCheck"
    title_box = Text.assemble(banner("MEMECOIN"), "\n", (f"{s.chain.upper()} // {mode}", DIM))

    # --- wallet status
    stat = Text()
    stat.append_text(blink("■ SCANNING ", GREEN, "#0c4a12"))
    stat.append(f"uptime {t_up // 3600}h{t_up // 60 % 60:02d}m{t_up % 60:02d}s   ", WHITE)
    stat.append("Ctrl+C to stop\n", DIM)
    stat.append("EQUITY ", DIM)
    stat.append(f"${eq:,.2f}   ", f"bold {WHITE}")
    stat.append("P&L ", DIM)
    stat.append(f"{'▲' if up else '▼'} ${abs(pnl):,.2f} ({pnl / w.start:+.1%})   ", f"bold {GREEN if up else RED}")
    stat.append("CASH ", DIM)
    stat.append(f"${w.cash:,.2f}\n", WHITE)
    stat.append("IN TRADES ", DIM)
    stat.append_text(gauge(len(positions) / s.max_positions, 14, CYAN))
    stat.append(f" {len(positions)}/{s.max_positions}   ", CYAN)
    stat.append("WINS ", DIM)
    stat.append(f"{st['wins']}/{st['n']}" + (f" ({st['wins'] / st['n']:.0%})" if st["n"] else ""), WHITE)
    if st["best"] is not None:
        stat.append("   BEST ", DIM)
        stat.append(f"{st['best']:+.0f}%", GREEN)
        stat.append("  WORST ", DIM)
        stat.append(f"{st['worst']:+.0f}%", RED)
    stat.append("\nFUNNEL ", DIM)
    stat.append(f"seen {c['seen']} ► checked {c['checked']} ► ", WHITE)
    stat.append(f"rejected {c['rejected']} ", RED)
    stat.append("│ ", TEAL)
    stat.append(f"passed {c['approved']} ", GREEN)
    stat.append(f"► bought {c['bought']}", f"bold {GREEN}")

    # --- ticker tape: open positions, else the buy list, else the funnel
    if positions:
        items = [(p["symbol"], tiny(p["last_price"]), (p["last_price"] / p["entry_price"] - 1) * 100) for p in positions]
    else:
        items = [(sym, "on buy list", 0.0) for sym, _ in list(b.approved.values())[:8]] or \
                [("SCANNING", f"{c['seen']} tokens seen", 0.0), ("REJECTED", f"{c['rejected']} scams/risky", 0.0)]

    # --- bots
    fit = max(3, (H - 23) // 2 - 2)

    def bot_panel(name: str):
        txt = Text()
        for ts, msg, style in list(b.logs[name])[-fit:]:
            txt.append(f"{ts} ", DIM)
            txt.append("► ", TEAL)
            txt.append(msg + "\n", NEON.get(style, style))
        busy = b.status[name] not in ("idle", "waiting", "starting")
        head = Text.assemble(pulse(busy), " ", (f"{name} BOT", f"bold {CYAN}"),
                             (f"  {b.status[name].upper()}", RED if b.status[name] == "error" else GREEN if busy else DIM))
        return hud_panel(txt, head, busy, BOT_ROLES[name])

    # --- positions
    pos = Table(box=box.SIMPLE_HEAD, border_style=TEAL, header_style=f"bold {CYAN}", style="on black",
                expand=True, padding=(0, 1), show_edge=False)
    for col in ("TOKEN", "ENTRY", "NOW", "P&L", "HELD", "LIQ"):
        pos.add_column(col, justify="left" if col == "TOKEN" else "right")
    for p in positions:
        chg = (p["last_price"] / p["entry_price"] - 1) * 100
        held = (time.time() - p["entry_time"]) / 60
        pos.add_row(Text(p["symbol"], f"bold {WHITE}"), tiny(p["entry_price"]), tiny(p["last_price"]),
                    Text(f"{'▲' if chg >= 0 else '▼'}{abs(chg):.1f}%", GREEN if chg >= 0 else RED),
                    f"{held:.0f}m", f"${p['last_liq'] / 1000:,.0f}k")
    if not positions:
        pos.add_row(Text("no open positions", DIM), "", "", "", "", "")

    # --- closed trades + reject reasons
    tr = Text()
    for t in w.trades(8):
        win = t["pnl"] > 0
        tr.append(f"{'▲' if win else '▼'} ", GREEN if win else RED)
        tr.append(f"{t['symbol']:<8}", WHITE)
        tr.append(f"{t['pnl_pct']:+6.1f}% ", GREEN if win else RED)
        tr.append(f"{t['reason'].split(' (')[0][:16]}\n", DIM)
    if not tr.plain:
        tr.append("no closed trades yet\n", DIM)
    top = sorted(b.reject_reasons.items(), key=lambda kv: -kv[1])[:3]
    if top:
        tr.append("TOP REJECTS ", f"bold {AMBER}")
        tr.append(", ".join(f"{k[:24]} ({v})" for k, v in top), DIM)

    bottom_h = 13
    eq_panel = hud_panel(chart(eq_hist or [eq], max(10, W * 2 // 7 - 14), bottom_h - 2), "EQUITY CURVE")

    lay = Layout()
    lay.split_column(Layout(name="top", size=6), Layout(tape(items, W), size=1), Layout(name="bots"),
                     Layout(name="bottom", size=bottom_h),
                     Layout(Text(" ■ SIMULATED. Real bots would do worse: faster competitors, failed transactions, "
                                 "MEV sandwiches, data seconds old.", AMBER), size=1))
    lay["top"].split_row(Layout(hud_panel(title_box, "4-BOT PAPER TRADER", subtitle="no wallet · no real money"), size=48),
                         Layout(hud_panel(stat, "WALLET (FAKE MONEY)", up)))
    lay["bots"].split_row(Layout(name="l"), Layout(name="r"))
    lay["bots"]["l"].split_column(Layout(bot_panel("SCANNER")), Layout(bot_panel("RISK")))
    lay["bots"]["r"].split_column(Layout(bot_panel("TRADER")), Layout(bot_panel("EXITS")))
    lay["bottom"].split_row(Layout(eq_panel, ratio=2), Layout(hud_panel(pos, "OPEN POSITIONS"), ratio=3),
                            Layout(hud_panel(tr, "CLOSED TRADES"), ratio=2))
    return lay
