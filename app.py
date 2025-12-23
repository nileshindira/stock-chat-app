import asyncio
import json
import random
import time
from typing import Dict, List, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


app = FastAPI(title="Carousel-Only Demo Platform")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------- Universal carousel schema (what the UI expects) ----------
# Response:
# {
#   "assistant_text": "...",
#   "carousels": [ {carousel}, {carousel}, ... ]
# }
#
# carousel:
# {
#   "carousel_id": "...",
#   "title": "...",
#   "subtitle": "...",
#   "layout": "card",
#   "items": [ {item}, ... ]
# }
#
# item:
# {
#   "id": "...",
#   "title": "...",
#   "subtitle": "...",
#   "image": null,
#   "badges": ["..."],
#   "primary_value": "...",
#   "secondary_value": "...",
#   "actions": [{"label":"...", "action":"..."}],
#   "metadata": {...}
# }


# ---------- Demo "catalogs" (like Canva templates / Booking hotels / Stocks) ----------
TEMPLATES = [
    {"id": "tpl_ig_post", "title": "Instagram Post", "subtitle": "1080×1080 • Social", "badges": ["Popular", "Free"]},
    {"id": "tpl_resume", "title": "Resume", "subtitle": "A4 • Professional", "badges": ["ATS-friendly"]},
    {"id": "tpl_pitch", "title": "Pitch Deck", "subtitle": "16:9 • Slides", "badges": ["Trending"]},
    {"id": "tpl_logo", "title": "Logo", "subtitle": "Vector • Brand", "badges": ["Quick"]},
    {"id": "tpl_story", "title": "IG Story", "subtitle": "1080×1920 • Social", "badges": ["New"]},
]

HOTELS = [
    {"id": "htl_1", "title": "Lakeview Residency", "subtitle": "Bengaluru • 4.3★", "badges": ["Breakfast", "Free cancellation"]},
    {"id": "htl_2", "title": "City Central Hotel", "subtitle": "Mumbai • 4.1★", "badges": ["Deal", "Near metro"]},
    {"id": "htl_3", "title": "Beachside Retreat", "subtitle": "Goa • 4.5★", "badges": ["Sea view"]},
    {"id": "htl_4", "title": "Heritage Palace", "subtitle": "Jaipur • 4.6★", "badges": ["Luxury"]},
    {"id": "htl_5", "title": "Budget Stay Plus", "subtitle": "Delhi • 4.0★", "badges": ["Best value"]},
]

STOCKS = [
    {"id": "stk_RELIANCE", "title": "RELIANCE", "subtitle": "Energy • Large Cap", "badges": ["NSE"]},
    {"id": "stk_TCS", "title": "TCS", "subtitle": "IT • Large Cap", "badges": ["NSE"]},
    {"id": "stk_HDFCBANK", "title": "HDFCBANK", "subtitle": "Banking • Large Cap", "badges": ["NSE"]},
    {"id": "stk_INFOSYS", "title": "INFY", "subtitle": "IT • Large Cap", "badges": ["NSE"]},
    {"id": "stk_ITC", "title": "ITC", "subtitle": "FMCG • Large Cap", "badges": ["NSE"]},
]


# ---------- Live value state (for WebSocket updates) ----------
# We'll update primary/secondary values continuously, per item.id
LIVE: Dict[str, Dict[str, Any]] = {}


def init_live_state():
    # Templates: "Uses today"
    for t in TEMPLATES:
        LIVE[t["id"]] = {
            "primary_value": f"{random.randint(1_000, 50_000)} uses",
            "secondary_value": f"+{random.randint(1, 30)}% this week",
            "updated_at": int(time.time()),
        }

    # Hotels: "Price per night"
    for h in HOTELS:
        price = random.randint(1800, 12000)
        LIVE[h["id"]] = {
            "primary_value": f"₹{price}/night",
            "secondary_value": f"{random.randint(5, 40)}% off",
            "updated_at": int(time.time()),
        }

    # Stocks: "Price"
    for s in STOCKS:
        price = random.uniform(200, 3500)
        LIVE[s["id"]] = {
            "primary_value": f"₹{price:.2f}",
            "secondary_value": f"{random.uniform(-2.5, 2.5):+.2f}%",
            "updated_at": int(time.time()),
        }


init_live_state()


def build_item(base: Dict[str, Any], actions: List[Dict[str, str]], extra_meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    live = LIVE.get(base["id"], {})
    return {
        "id": base["id"],
        "title": base["title"],
        "subtitle": base["subtitle"],
        "image": None,
        "badges": base.get("badges", []),
        "primary_value": live.get("primary_value", "-"),
        "secondary_value": live.get("secondary_value", "-"),
        "actions": actions,
        "metadata": extra_meta or {},
    }


def carousel(carousel_id: str, title: str, subtitle: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "carousel_id": carousel_id,
        "title": title,
        "subtitle": subtitle,
        "layout": "card",
        "items": items,
    }


class ChatRequest(BaseModel):
    message: str


def route_intent(message: str) -> str:
    q = (message or "").strip().lower()
    # very simple intent routing for demo
    if any(k in q for k in ["template", "design", "canva", "poster", "resume", "logo", "story"]):
        return "templates"
    if any(k in q for k in ["hotel", "booking", "stay", "room", "goa", "mumbai", "delhi", "bangalore", "bengaluru", "jaipur"]):
        return "hotels"
    if any(k in q for k in ["stock", "price", "buy", "sell", "nse", "reliance", "tcs", "hdfc", "infy", "itc"]):
        return "stocks"
    if any(k in q for k in ["all", "everything", "explore", "discover"]):
        return "all"
    return "all"


@app.get("/", response_class=HTMLResponse)
def home():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/chat")
def chat(req: ChatRequest):
    intent = route_intent(req.message)

    carousels: List[Dict[str, Any]] = []

    if intent in ("templates", "all"):
        items = [
            build_item(t, actions=[{"label": "Use", "action": "USE_TEMPLATE"}, {"label": "Preview", "action": "PREVIEW"}])
            for t in random.sample(TEMPLATES, k=min(5, len(TEMPLATES)))
        ]
        carousels.append(carousel("templates", "Templates", "Pick a starting point (carousel-only)", items))

    if intent in ("hotels", "all"):
        items = [
            build_item(h, actions=[{"label": "Book", "action": "BOOK"}, {"label": "Save", "action": "SAVE"}])
            for h in random.sample(HOTELS, k=min(5, len(HOTELS)))
        ]
        carousels.append(carousel("hotels", "Stays & Deals", "Demo hotel cards (carousel-only)", items))

    if intent in ("stocks", "all"):
        items = [
            build_item(s, actions=[{"label": "Buy", "action": "BUY"}, {"label": "Sell", "action": "SELL"}])
            for s in random.sample(STOCKS, k=min(5, len(STOCKS)))
        ]
        carousels.append(carousel("stocks", "Market Watch", "Demo live tickers (random)", items))

    assistant_text = "Showing carousels based on your request. (Demo data, live updates via WebSocket.)"

    return {"assistant_text": assistant_text, "carousels": carousels}


@app.post("/api/action")
def action(payload: Dict[str, Any]):
    """
    Demo action handler for card buttons.
    In real apps, this triggers workflows: create design, book hotel, place order, etc.
    """
    item_id = payload.get("item_id")
    action_name = payload.get("action")
    return {
        "ok": True,
        "message": f"Action '{action_name}' received for item '{item_id}' (demo)."
    }


# ---------- WebSocket "live" updater ----------
async def live_engine():
    while True:
        # Templates: uses and growth
        for t in TEMPLATES:
            v = LIVE[t["id"]]
            uses = int(v["primary_value"].split()[0].replace(",", ""))
            uses += random.randint(0, 120)
            v["primary_value"] = f"{uses:,} uses"
            v["secondary_value"] = f"+{random.randint(1, 30)}% this week"
            v["updated_at"] = int(time.time())

        # Hotels: price and discount wiggle
        for h in HOTELS:
            price = random.randint(1800, 12000)
            LIVE[h["id"]] = {
                "primary_value": f"₹{price}/night",
                "secondary_value": f"{random.randint(5, 40)}% off",
                "updated_at": int(time.time()),
            }

        # Stocks: price + percent
        for s in STOCKS:
            old = float(LIVE[s["id"]]["primary_value"].replace("₹", ""))
            new = max(1.0, old + random.uniform(-2.5, 2.5))
            pct = random.uniform(-2.5, 2.5)
            LIVE[s["id"]]["primary_value"] = f"₹{new:.2f}"
            LIVE[s["id"]]["secondary_value"] = f"{pct:+.2f}%"
            LIVE[s["id"]]["updated_at"] = int(time.time())

        await asyncio.sleep(0.6)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(live_engine())


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    """
    Client subscribes with:
      {"type":"subscribe","item_ids":["tpl_ig_post","stk_TCS",...]}
    Server pushes:
      {"type":"update","data": {"item_id": {"primary_value":"...", "secondary_value":"..."} } }
    """
    await ws.accept()
    subscribed: List[str] = []

    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.25)
                data = json.loads(msg)
                if data.get("type") == "subscribe":
                    requested = data.get("item_ids") or []
                    subscribed = [i for i in requested if i in LIVE]
                    await ws.send_text(json.dumps({"type": "subscribed", "item_ids": subscribed}))
            except asyncio.TimeoutError:
                pass

            if subscribed:
                snap = {i: LIVE[i] for i in subscribed if i in LIVE}
                await ws.send_text(json.dumps({"type": "update", "data": snap}))
    except WebSocketDisconnect:
        return
