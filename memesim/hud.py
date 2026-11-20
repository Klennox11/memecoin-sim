"""Black / cyan / green terminal dashboard."""
import os
import sys
import time

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .bots import Board
from .config import Settings
from .wallet import PaperWallet

console = Console(style="white on black", highlight=False)
FANCY = sys.platform != "win32" or "WT_SESSION" in os.environ  # old PowerShell window can't draw blocks
BLOCKS = "▁▂▃▄▅▆▇█" if FANCY else "_.-~=+*#"


def sparkline(vals: list[float], width: int = 40) -> str:
    if len(vals) < 2:
        return ""
    step = max(1, len(vals) // width)
    pts = vals[::step][-width:]
    lo, hi = min(pts), max(pts)
    span = hi - lo or 1
    return "".join(BLOCKS[int((p - lo) / span * (len(BLOCKS) - 1))] for p in pts)


def panel(body, title: str, color: str = "cyan") -> Panel:
    return Panel(body, title=f"[bold cyan]// {title}[/]", border_style=color, style="on black")


def money(x: float) -> str:
    return f"${x:+,.2f}"


def render(w: PaperWallet, b: Board, s: Settings, eq_hist: list[float], demo: bool) -> Layout:
    eq = w.equity()
    pnl = eq - w.start
    st = w.stats()
    up = int(time.time() - b.started)
    c = b.counts
    win = f"{st['wins']}/{st['n']} ({st['wins'] / st['n']:.0%})" if st["n"] else "0/0"
    head = Text.assemble(
        ("MEMECOIN-SIM ", "bold cyan"), ("// 4-BOT PAPER TRADER ", "bold green"),
        (f"// {s.chain.upper()} {'// DEMO DATA' if demo else '// LIVE DATA (DexScreener + RugCheck)'}\n", "bold white"),
        ("Equity ", "grey50"), (f"${eq:,.2f}  ", "bold white"),
        ("P&L ", "grey50"), (f"{money(pnl)} ({pnl / w.start:+.1%})  ", "bold green" if pnl >= 0 else "bold red"),
        ("Cash ", "grey50"), (f"${w.cash:,.2f}  ", "white"),
        ("Wins ", "grey50"), (f"{win}  ", "white"),
        ("Uptime ", "grey50"), (f"{up // 3600}h{up // 60 % 60:02d}m{up % 60:02d}s\n", "white"),
        ("Funnel ", "grey50"),
        (f"seen {c['seen']} -> checked {c['checked']} -> ", "white"),
        (f"rejected {c['rejected']} ", "red"), ("/ ", "grey50"), (f"approved {c['approved']} ", "green"),
        (f"-> bought {c['bought']}   ", "bold green"),
        ("Equity ", "grey50"), (sparkline(eq_hist), "cyan"),
    )

    def bot(name: str):
        t = Text()
        fit = max(3, (console.size.height - 18) // 2 - 2)  # only the newest lines that fit on screen
        for ts, msg, style in list(b.logs[name])[-fit:]:
            t.append(f"{ts} ", "grey50")
            t.append(msg + "\n", style)
        busy = b.status[name] not in ("idle", "waiting")
        return panel(t, f"{name} BOT ({b.status[name]})", "green" if busy else "cyan")

    pos = Table(border_style="cyan", header_style="bold white", style="on black", expand=True)
    for col in ("Token", "Entry", "Now", "P&L", "Held", "Liquidity"):
        pos.add_column(col, justify="left" if col == "Token" else "right")
    for p in w.positions():
        chg = (p["last_price"] / p["entry_price"] - 1) * 100
        held = (time.time() - p["entry_time"]) / 60
        pos.add_row(p["symbol"], f"{p['entry_price']:.3g}", f"{p['last_price']:.3g}",
                    Text(f"{chg:+.1f}%", "green" if chg >= 0 else "red"), f"{held:.0f}m", f"${p['last_liq']:,.0f}")

    tr = Text()
    for t in w.trades(8):
        tr.append(f"{t['symbol']:<9}", "white")
        tr.append(f"{money(t['pnl']):>9} {t['pnl_pct']:+6.1f}%  ", "green" if t["pnl"] > 0 else "red")
        tr.append(f"{t['reason']}\n", "grey50")
    top = sorted(b.reject_reasons.items(), key=lambda kv: -kv[1])[:4]
    if top:
        tr.append("\nTop reject reasons: ", "cyan")
        tr.append(", ".join(f"{k} ({v})" for k, v in top), "grey50")

    lay = Layout()
    lay.split_column(Layout(panel(head, "WALLET (FAKE MONEY)"), size=5), Layout(name="bots"),
                     Layout(name="bottom", size=12),
                     Layout(Text(" SIMULATED. Real bots would do worse: faster competitors, failed transactions, "
                                 "MEV sandwiches, and data that is seconds old.", "grey50"), size=1))
    lay["bots"].split_row(Layout(name="l"), Layout(name="r"))
    lay["bots"]["l"].split_column(Layout(bot("SCANNER")), Layout(bot("RISK")))
    lay["bots"]["r"].split_column(Layout(bot("TRADER")), Layout(bot("EXITS")))
    lay["bottom"].split_row(Layout(panel(pos, "OPEN POSITIONS")), Layout(panel(tr, "CLOSED TRADES")))
    return lay
