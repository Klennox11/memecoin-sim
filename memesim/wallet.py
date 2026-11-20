"""Pretend wallet, saved in a SQLite file so it survives restarts. No keys, no real money."""
import sqlite3
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_DB, DEMO_DB = ROOT / "paper_wallet.db", ROOT / "paper_wallet_demo.db"


class PaperWallet:
    def __init__(self, start_balance: float, db: Path):
        self.lock = threading.RLock()  # dashboard thread + bots share the database
        self.con = sqlite3.connect(db, check_same_thread=False)
        self.con.executescript("""
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value REAL);
            CREATE TABLE IF NOT EXISTS positions (address TEXT PRIMARY KEY, symbol TEXT, tokens REAL, cost REAL,
                entry_price REAL, entry_time REAL, peak_price REAL, entry_liq REAL, last_price REAL, last_liq REAL);
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, address TEXT, cost REAL,
                proceeds REAL, pnl REAL, pnl_pct REAL, reason TEXT, opened REAL, closed REAL);
        """)
        if self._get("cash") is None:
            self._set("cash", start_balance)
            self._set("start", start_balance)
        self.con.commit()

    def _get(self, k):
        with self.lock:
            r = self.con.execute("SELECT value FROM kv WHERE key=?", (k,)).fetchone()
            return r[0] if r else None

    def _set(self, k, v):
        with self.lock:
            self.con.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, v))

    @property
    def cash(self) -> float:
        return self._get("cash")

    @property
    def start(self) -> float:
        return self._get("start")

    def positions(self) -> list[dict]:
        with self.lock:
            cur = self.con.execute("SELECT * FROM positions ORDER BY entry_time")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def trades(self, limit: int = 8) -> list[dict]:
        with self.lock:
            cur = self.con.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def stats(self) -> dict:
        with self.lock:
            n, wins, pnl, best, worst = self.con.execute(
                "SELECT COUNT(*), COALESCE(SUM(pnl>0),0), COALESCE(SUM(pnl),0), MAX(pnl_pct), MIN(pnl_pct) FROM trades"
            ).fetchone()
        return dict(n=n, wins=wins, pnl=pnl, best=best, worst=worst)

    def equity(self) -> float:
        """Cash + open positions valued at the last seen price (before exit costs)."""
        return self.cash + sum(p["tokens"] * p["last_price"] for p in self.positions())

    def open(self, pair: dict, tokens: float, cost: float) -> None:
        with self.lock:
            self._set("cash", self.cash - cost)
            px = pair["price"]
            self.con.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (pair["address"], pair["symbol"], tokens, cost, px, time.time(), px,
                              pair["liquidity"], px, pair["liquidity"]))
            self.con.commit()

    def mark(self, address: str, price: float, liq: float) -> None:
        with self.lock:
            self.con.execute("UPDATE positions SET last_price=?, last_liq=?, peak_price=MAX(peak_price, ?) "
                             "WHERE address=?", (price, liq, price, address))
            self.con.commit()

    def close(self, pos: dict, proceeds: float, reason: str) -> float:
        with self.lock:
            pnl = proceeds - pos["cost"]
            self._set("cash", self.cash + proceeds)
            self.con.execute("DELETE FROM positions WHERE address=?", (pos["address"],))
            self.con.execute("INSERT INTO trades (symbol,address,cost,proceeds,pnl,pnl_pct,reason,opened,closed) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", (pos["symbol"], pos["address"], pos["cost"], proceeds,
                                                            pnl, pnl / pos["cost"] * 100, reason, pos["entry_time"],
                                                            time.time()))
            self.con.commit()
            return pnl

    def reset(self) -> None:
        with self.lock:
            self.con.executescript("DELETE FROM kv; DELETE FROM positions; DELETE FROM trades;")
            self.con.commit()
