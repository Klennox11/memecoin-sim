"""Visual effects for the HUD. Uses only characters that even the old blue PowerShell
window can draw (full/half blocks, shades, arrows), so it looks right everywhere."""
import time

from rich import box
from rich.panel import Panel
from rich.text import Text

# Neon palette
CYAN, GREEN, TEAL, WHITE, RED, AMBER, DIM = "#00e5ff", "#39ff14", "#0e6f7a", "#e8ffff", "#ff3860", "#ffb000", "#4a6b70"
GRADIENT = ["#00e5ff", "#00f0c8", "#20ff8a", "#39ff14"]

# 5-row block font (only the letters we need; unknown letters become blanks)
FONT = {
    "S": ["###", "#  ", "###", "  #", "###"], "T": ["###", " # ", " # ", " # ", " # "],
    "O": ["###", "# #", "# #", "# #", "###"], "C": ["###", "#  ", "#  ", "#  ", "###"],
    "K": ["# #", "# #", "## ", "# #", "# #"], "-": ["   ", "   ", "###", "   ", "   "],
    "I": ["###", " # ", " # ", " # ", "###"], "M": ["#   #", "## ##", "# # #", "#   #", "#   #"],
    "E": ["###", "#  ", "###", "#  ", "###"], "N": ["#  #", "## #", "# ##", "#  #", "#  #"],
    " ": ["  ", "  ", "  ", "  ", "  "],
}


def banner(word: str) -> Text:
    """Big block-letter title squeezed into 3 lines with half blocks, cyan->green gradient."""
    rows = ["", "", "", "", "", ""]
    for ch in word.upper():
        g = FONT.get(ch, FONT[" "])
        for r in range(5):
            rows[r] += g[r] + " "
    rows[5] = " " * len(rows[0])
    out = Text()
    for i in range(3):
        top, bot = rows[2 * i], rows[2 * i + 1]
        line = "".join("█" if a == "#" and b == "#" else "▀" if a == "#" else "▄" if b == "#" else " "
                       for a, b in zip(top, bot))
        out.append(line + ("\n" if i < 2 else ""), f"bold {GRADIENT[i]}")
    return out


def chart(values: list[float], width: int, height: int, money: bool = True) -> Text:
    """Multi-line area chart using half blocks (2 levels per text row), with min/max labels."""
    if len(values) < 2:
        return Text("waiting for data...", DIM)
    # resample to width
    n = len(values)
    pts = [values[min(n - 1, int(i * n / width))] for i in range(width)] if n > width else values[:]
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    levels = [round((p - lo) / span * (height * 2 - 1)) + 1 for p in pts]
    color = GREEN if pts[-1] >= pts[0] else RED
    fmt = (lambda v: f"${v:,.0f}") if money else (lambda v: f"{v:,.2f}")
    lab_w = max(len(fmt(hi)), len(fmt(lo)))
    out = Text()
    for r in range(height):
        floor = (height - 1 - r) * 2
        label = fmt(hi) if r == 0 else fmt(lo) if r == height - 1 else ""
        out.append(f"{label:>{lab_w}} ", DIM)
        out.append("│", TEAL)
        shade = GRADIENT[min(3, r * 4 // height)] if color == GREEN else color
        for lv in levels:
            out.append("█" if lv >= floor + 2 else "▄" if lv == floor + 1 else " ", shade)
        if r < height - 1:
            out.append("\n")
    return out


def gauge(frac: float, width: int = 20, color: str = GREEN) -> Text:
    frac = max(0.0, min(1.0, frac))
    n = round(frac * width)
    return Text.assemble(("█" * n, color), ("░" * (width - n), TEAL))


def pulse(busy: bool) -> Text:
    """Animated activity light: pulses when a bot is working, dim dot when idle."""
    if not busy:
        return Text("·", DIM)
    frames = "░▒▓█▓▒"
    return Text(frames[int(time.time() * 6) % len(frames)], GREEN)


def blink(text: str, on: str = RED, off: str = "#5a1020") -> Text:
    return Text(text, f"bold {on if int(time.time() * 2) % 2 else off}")


def tape(items: list[tuple[str, object, float]], width: int) -> Text:
    """Scrolling ticker tape: (symbol, price or preformatted text, % change)."""
    if not items:
        return Text("")
    seg = Text()
    for sym, px, chg in items:
        up = chg >= 0
        seg.append(f"  {sym} ", f"bold {WHITE}")
        seg.append(f"{px} " if isinstance(px, str) else f"${px:,.2f} ", CYAN)
        seg.append(f"{'▲' if up else '▼'}{abs(chg):.2f}%", GREEN if up else RED)
        seg.append("   ║", TEAL)
    plain = seg.plain
    reps = width // max(1, len(plain)) + 2
    full = Text()
    for _ in range(reps):
        full.append_text(seg)
    off = int(time.time() * 4) % len(plain)
    return full[off:off + width]


def hud_panel(body, title, active: bool = False, subtitle: str | None = None) -> Panel:
    t = Text(title, f"bold {CYAN}") if isinstance(title, str) else title
    return Panel(body, title=Text.assemble(("╡ ", TEAL), t, (" ╞", TEAL)),
                 title_align="left", subtitle=Text(subtitle, DIM) if subtitle else None, subtitle_align="right",
                 border_style=GREEN if active else TEAL, box=box.DOUBLE, style="on black", padding=(0, 1))
