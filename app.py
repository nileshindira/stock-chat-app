import asyncio
import json
import random
import time
from typing import Dict, List, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


app = FastAPI(title="Stock Chat Carousel (Demo)")

# Serve frontend
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Demo stock universe ----------
SYMBOLS = [
    "NSE:RELIANCE", "NSE:TCS", "NSE:HDFCBANK", "NSE:INFY", "NSE:ICICIBANK",
    "NSE:ITC", "NSE:SBIN", "NSE:BHARTIARTL", "NSE:LT", "NSE:AXISBANK"
]

def seed_prices() -> Dict[str, Dict[str, Any]]:
    base = {}
    for s in SYMBOLS:
        base_price = random.uniform(200, 3500)
        base[s] = {
            "symbol": s,
            "ltp": round(base_price, 2),
            "change": 0.0,
            "change_pct": 0.0,
            "day_high": round(base_price * random.uniform(1.005, 1.03), 2),
            "day_low": round(base_price * random.uniform(0.97, 0.995), 2),
            "vol": random.randint(50_000, 5_000_000),
            "updated_at": int(time.time()),
        }
    return base

PRICE_STATE: Dict[str, Dict[str, Any]] = seed_prices()

# ---------- Demo news ----------
DEMO_NEWS = {
    "NSE:RELIANCE": [
        {"title": "Reliance: board meeting highlights expected", "source": "DemoWire", "ts": "2m ago"},
        {"title": "Reliance: retail footfall trends remain strong", "source": "DemoWire", "ts": "18m ago"},
    ],
    "NSE:TCS": [
        {"title": "TCS: deal pipeline commentary in focus", "source": "DemoWire", "ts": "6m ago"},
    ],
}

def get_news(symbol: str) -> List[Dict[str, Any]]:
    # Always return a list (even if empty), UI renders it.
    return DEMO_NEWS.get(symbol, [
        {"title": f"{symbol}: no breaking news (demo feed)", "source": "DemoWire", "ts": "just now"}
    ])

# ---------- Chat request ----------
class ChatRequest(BaseModel):
    message: str


def normalize_query(q: str) -> str:
    return (q or "").strip().lower()


def pick_symbols_from_message(msg: str) -> List[str]:
    q = normalize_query(msg)

    # Super simple intent parsing (extend later)
    if any(k in q for k in ["top movers", "movers", "trending", "hot", "watchlist"]):
        return random.sample(SYMBOLS, k=min(6, len(SYMBOLS)))

    # If user mentions a company name, map it
    mapping = {
        "reliance": "NSE:RELIANCE",
        "tcs": "NSE:TCS",
        "hdfc": "NSE:HDFCBANK",
        "hdfcbank": "NSE:HDFCBANK",
        "infy": "NSE:INFY",
        "infosys": "NSE:INFY",
        "icici": "NSE:ICICIBANK",
        "itc": "NSE:ITC",
        "sbin": "NSE:SBIN",
        "sbi": "NSE:SBIN",
        "bharti": "NSE:BHARTIARTL",
        "airtel": "NSE:BHARTIARTL",
        "lt": "NSE:LT",
        "l&t": "NSE:LT",
        "axis": "NSE:AXISBANK",
    }
    for key, sym in mapping.items():
        if key in q:
            return [sym]

    # If user directly types NSE:XXXX
    for sym in SYMBOLS:
        if sym.lower() in q:
            return [sym]

    # Default: show a small set
    return random.sample(SYMBOLS, k=5)


def build_cards(symbols: List[str]) -> List[Dict[str, Any]]:
    cards = []
    for s in symbols:
        p = PRICE_STATE.get(s)
        if not p:
            continue
        cards.append({
            "symbol": s,
            "ltp": p["ltp"],
            "change": p["change"],
            "change_pct": p["change_pct"],
            "day_high": p["day_high"],
            "day_low": p["day_low"],
            "vol": p["vol"],
            "news": get_news(s),
        })
    return cards


@app.get("/", response_class=HTMLResponse)
def home():
    # Serve the single-page UI
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    Returns ONLY carousel items (cards) + a short assistant line.
    """
    symbols = pick_symbols_from_message(req.message)
    cards = build_cards(symbols)
    assistant = f"Showing {len(cards)} symbols in carousel (demo live tickers)."
    return {"assistant": assistant, "cards": cards}


@app.post("/api/order")
def place_order(payload: Dict[str, Any]):
    """
    Demo order endpoint. In real version, validate user auth, risk checks, broker API, etc.
    """
    # Minimal validation
    symbol = payload.get("symbol")
    side = payload.get("side")
    qty = int(payload.get("qty", 1))
    if symbol not in SYMBOLS:
        return {"ok": False, "error": "Unknown symbol"}
    if side not in ("BUY", "SELL"):
        return {"ok": False, "error": "Invalid side"}
    if qty <= 0:
        return {"ok": False, "error": "Qty must be > 0"}

    return {
        "ok": True,
        "message": f"Demo order accepted: {side} {qty} of {symbol}",
        "order_id": f"DEMO-{int(time.time())}-{random.randint(100,999)}"
    }


# ---------- WebSocket price streamer ----------
async def price_engine():
    """
    Continuously mutate PRICE_STATE to simulate live ticks.
    """
    while True:
        for s, p in PRICE_STATE.items():
            old = p["ltp"]
            drift = random.uniform(-0.8, 0.8)  # small drift
            new = max(1.0, old + drift)
            p["ltp"] = round(new, 2)
            p["change"] = round(new - (old - p["change"]), 2)  # approximate
            # safer: compute pct from a fake prev_close
            prev_close = max(1.0, p.get("prev_close", old))
            p["prev_close"] = prev_close
            p["change"] = round(new - prev_close, 2)
            p["change_pct"] = round((p["change"] / prev_close) * 100.0, 2)

            p["day_high"] = round(max(p["day_high"], new), 2)
            p["day_low"] = round(min(p["day_low"], new), 2)
            p["vol"] = int(p["vol"] + random.randint(100, 8000))
            p["updated_at"] = int(time.time())

        await asyncio.sleep(0.35)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(price_engine())


@app.websocket("/ws/prices")
async def ws_prices(ws: WebSocket):
    """
    Client subscribes with:
      {"type":"subscribe","symbols":["NSE:RELIANCE","NSE:TCS"]}
    Then server pushes:
      {"type":"tick","data":{...}}
    """
    await ws.accept()
    subscribed: List[str] = []

    try:
        while True:
            # Non-blocking receive with timeout: allow pushing ticks even if no incoming messages
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.2)
                data = json.loads(msg)
                if data.get("type") == "subscribe":
                    requested = data.get("symbols") or []
                    subscribed = [s for s in requested if s in SYMBOLS]
                    await ws.send_text(json.dumps({"type": "subscribed", "symbols": subscribed}))
            except asyncio.TimeoutError:
                pass

            if subscribed:
                snap = {s: PRICE_STATE[s] for s in subscribed if s in PRICE_STATE}
                await ws.send_text(json.dumps({"type": "tick", "data": snap}))
    except WebSocketDisconnect:
        return
