"""Where market data comes from.

LiveFeed  - real, free public APIs (no key needed):
    DexScreener  token-profiles / token-boosts  -> newly listed tokens
    DexScreener  tokens/v1/{chain}/{addresses}  -> price, liquidity, buys/sells, volume
    RugCheck     tokens/{mint}/report           -> mint/freeze authority, top holders, LP lock
DemoFeed  - a fake market with honest tokens, obvious scams and hidden rugs, for testing offline.

Both return the same simple dictionaries, so the bots don't care which one is running.
"""
import random
import time

import httpx

DEX = "https://api.dexscreener.com"
RUG = "https://api.rugcheck.xyz/v1"


def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def normalize_pair(p: dict) -> dict:
    """DexScreener pair -> the fields our bots use."""
    tx, vol, chg = p.get("txns") or {}, p.get("volume") or {}, p.get("priceChange") or {}
    m5, h1 = tx.get("m5") or {}, tx.get("h1") or {}
    base = p.get("baseToken") or {}
    return {
        "address": base.get("address", ""),
        "symbol": (base.get("symbol") or "?")[:10],
        "name": base.get("name") or "",
        "price": _f(p.get("priceUsd")),
        "liquidity": _f((p.get("liquidity") or {}).get("usd")),
        "created_ms": p.get("pairCreatedAt") or 0,
        "m5_change": _f(chg.get("m5")),
        "m5_volume": _f(vol.get("m5")),
        "m5_buys": int(m5.get("buys") or 0), "m5_sells": int(m5.get("sells") or 0),
        "h1_buys": int(h1.get("buys") or 0), "h1_sells": int(h1.get("sells") or 0),
        "dex": p.get("dexId", ""),
        "url": p.get("url", ""),
    }


class LiveFeed:
    def __init__(self, chain: str = "solana"):
        self.chain = chain
        self.http = httpx.Client(timeout=15, headers={"User-Agent": "memecoin-sim/0.1 (paper trading)"})

    def latest_tokens(self) -> list[str]:
        """Newest token addresses on our chain from DexScreener's public feeds."""
        seen = []
        for path in ("/token-profiles/latest/v1", "/token-boosts/latest/v1"):
            r = self.http.get(DEX + path)
            r.raise_for_status()
            for item in r.json():
                if item.get("chainId") == self.chain and item.get("tokenAddress") not in seen:
                    seen.append(item["tokenAddress"])
        return seen

    def pairs(self, addresses: list[str]) -> dict[str, dict]:
        """Best (most liquid) pair for each token address. Max 30 addresses per request."""
        out: dict[str, dict] = {}
        for i in range(0, len(addresses), 30):
            chunk = ",".join(addresses[i:i + 30])
            r = self.http.get(f"{DEX}/tokens/v1/{self.chain}/{chunk}")
            r.raise_for_status()
            for p in r.json() or []:
                n = normalize_pair(p)
                if n["address"] and (n["address"] not in out or n["liquidity"] > out[n["address"]]["liquidity"]):
                    out[n["address"]] = n
        return out

    def safety(self, mint: str) -> dict:
        """RugCheck report -> simple safety facts."""
        r = self.http.get(f"{RUG}/tokens/{mint}/report")
        r.raise_for_status()
        d = r.json()
        markets = d.get("markets") or []
        pool_accounts = set()
        lp_locked = None
        for m in markets:
            for k in ("pubkey", "liquidityAAccount", "liquidityBAccount", "liquidityA", "liquidityB"):
                if m.get(k):
                    pool_accounts.add(m[k])
            lp = (m.get("lp") or {}).get("lpLockedPct")
            if lp is not None:
                lp_locked = max(lp_locked or 0.0, _f(lp))
        if lp_locked is None and d.get("lpLockedPct") is not None:
            lp_locked = _f(d["lpLockedPct"])
        holders = [h for h in (d.get("topHolders") or [])
                   if h.get("address") not in pool_accounts and h.get("owner") not in pool_accounts]
        return {
            "mint_authority": bool(d.get("mintAuthority")),
            "freeze_authority": bool(d.get("freezeAuthority")),
            "top10_pct": sum(_f(h.get("pct")) for h in holders[:10]),
            "lp_locked_pct": lp_locked,
            "score": int(d.get("score_normalised") or 0),
            "danger": [x.get("name", "?") for x in (d.get("risks") or []) if x.get("level") == "danger"],
            "rugged": bool(d.get("rugged")),
        }


class DemoFeed:
    """Fake memecoin market. Most tokens drift down, scams are common, and some
    'clean-looking' tokens still get rugged later -- just like the real thing."""

    KINDS = ["honest"] * 3 + ["scam_mint", "scam_freeze", "scam_whale", "honeypot", "hidden_rug", "hidden_rug"]

    def __init__(self, seed: int = 1):
        self.rng = random.Random(seed)
        self.tokens: dict[str, dict] = {}
        self.n = 0
        self.last = time.time()

    def _new_token(self) -> str:
        self.n += 1
        kind = self.rng.choice(self.KINDS)
        addr = f"DEMO{self.n:04d}" + "".join(self.rng.choices("abcdefghjkmnpqrstuvwxyz123456789", k=8))
        sym = self.rng.choice(["PEPE", "DOGE", "CAT", "MOON", "WIF", "FROG", "BONK", "CHAD", "GIGA", "TRUMP"]) + \
            self.rng.choice(["", "2", "AI", "INU", "X", "SOL"])
        self.tokens[addr] = dict(
            kind=kind, symbol=sym, price=self.rng.uniform(1e-5, 1e-3),
            liq=self.rng.uniform(8_000, 120_000), created=time.time() - self.rng.uniform(5, 300) * 60,
            drift=self.rng.uniform(-0.004, 0.003), vol=self.rng.uniform(0.01, 0.04),
            rug_at=time.time() + self.rng.uniform(60, 900) if kind == "hidden_rug" else None,
            rugged=False, m5_change=0.0,
        )
        return addr

    def _step(self) -> None:
        now = time.time()
        steps = int((now - self.last) // 1)  # one price step per second
        if steps <= 0:
            return
        self.last = now
        for t in self.tokens.values():
            if t["rugged"]:
                continue
            start = t["price"]
            for _ in range(min(steps, 60)):
                t["price"] *= 1 + self.rng.gauss(t["drift"], t["vol"])
                t["price"] = max(t["price"], 1e-12)
            t["m5_change"] = 0.7 * t["m5_change"] + (t["price"] / start - 1) * 100 * 3
            if t["rug_at"] and now > t["rug_at"]:  # dev pulls the liquidity
                t["rugged"], t["liq"], t["price"] = True, t["liq"] * 0.03, t["price"] * 0.05

    def latest_tokens(self) -> list[str]:
        for _ in range(self.rng.randint(1, 4)):
            self._new_token()
        return list(self.tokens)[-10:]

    def pairs(self, addresses: list[str]) -> dict[str, dict]:
        self._step()
        out = {}
        for a in addresses:
            t = self.tokens.get(a)
            if not t:
                continue
            honeypot = t["kind"] == "honeypot"
            buys = self.rng.randint(20, 200)
            out[a] = {
                "address": a, "symbol": t["symbol"], "name": t["symbol"], "price": t["price"],
                "liquidity": t["liq"], "created_ms": int(t["created"] * 1000),
                "m5_change": t["m5_change"], "m5_volume": self.rng.uniform(500, 20_000),
                "m5_buys": buys // 6, "m5_sells": 0 if honeypot else int(buys // 6 * self.rng.uniform(0.3, 1.1)),
                "h1_buys": buys, "h1_sells": 0 if honeypot else int(buys * self.rng.uniform(0.3, 1.0)),
                "dex": "demo", "url": "",
            }
        return out

    def safety(self, mint: str) -> dict:
        t = self.tokens[mint]
        k = t["kind"]
        return {
            "mint_authority": k == "scam_mint",
            "freeze_authority": k in ("scam_freeze", "honeypot"),
            "top10_pct": self.rng.uniform(55, 90) if k == "scam_whale" else self.rng.uniform(10, 30),
            "lp_locked_pct": 0.0 if k == "scam_whale" else 100.0,
            "score": self.rng.randint(60, 95) if k.startswith("scam") else self.rng.randint(1, 40),
            "danger": ["Mint Authority still enabled"] if k == "scam_mint" else [],
            "rugged": t["rugged"],
        }
