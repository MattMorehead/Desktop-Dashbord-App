import sys
import os
import json
import time
import threading
import sqlite3
import requests
import feedparser
import yfinance as yf
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
import concurrent.futures
from google import genai
from google.genai import types
import keyring
from platformdirs import user_data_dir

# --- Watchdog: Terminate immediately if Tauri closes stdin ---
def stdin_watchdog():
    pass

threading.Thread(target=stdin_watchdog, daemon=True).start()

# Redirect normal stdout to stderr to prevent libraries from corrupting our JSON IPC
IPC_STDOUT = sys.stdout
sys.stdout = sys.stderr

# --- Database & Storage ---
APP_DIR = Path(user_data_dir("AiDashboard", "Antigravity"))
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / "dashboard_store.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS component_cache (
            component_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            status TEXT DEFAULT 'healthy',
            last_updated INTEGER NOT NULL
        );
    """)
    conn.close()

init_db()

# --- Location Agent ---
def get_location():
    try:
        data = requests.get("http://ip-api.com/json/", timeout=2).json()
        if data.get("status") == "success":
            return {
                "city": data.get("city", "Unknown City"),
                "region": data.get("region", "Unknown"),
                "lat": data.get("lat", 40.7128),
                "lon": data.get("lon", -74.0060),
                "timezone": data.get("timezone", "America/New_York")
            }
    except Exception as e:
        sys.stderr.write(f"Location fetch failed: {e}\n")
    
    # Fallback if network or API fails
    return {"city": "New York City (Fallback)", "region": "NY", "lat": 40.7128, "lon": -74.0060, "timezone": "America/New_York"}

# --- Weather Agent ---
WMO_MAP = {
    0: ("Clear", "sunny"),
    1: ("Mainly clear", "partly_cloudy_day"),
    2: ("Partly cloudy", "partly_cloudy_day"),
    3: ("Overcast", "cloudy"),
    45: ("Fog", "foggy"),
    48: ("Rime fog", "foggy"),
    51: ("Light drizzle", "rainy"),
    53: ("Drizzle", "rainy"),
    55: ("Dense drizzle", "rainy"),
    56: ("Freezing drizzle", "rainy"),
    57: ("Dense freezing drizzle", "rainy"),
    61: ("Light rain", "rainy"),
    63: ("Rain", "rainy"),
    65: ("Heavy rain", "rainy"),
    66: ("Freezing rain", "rainy"),
    67: ("Heavy freezing rain", "rainy"),
    71: ("Light snow", "snowing"),
    73: ("Snow", "snowing"),
    75: ("Heavy snow", "snowing"),
    77: ("Snow grains", "snowing"),
    80: ("Light rain showers", "rainy"),
    81: ("Rain showers", "rainy"),
    82: ("Heavy rain showers", "rainy"),
    85: ("Snow showers", "snowing"),
    86: ("Heavy snow showers", "snowing"),
    95: ("Thunderstorm", "thunderstorm"),
    96: ("Thunderstorm, light hail", "thunderstorm"),
    99: ("Thunderstorm, heavy hail", "thunderstorm")
}

def fetch_weather(lat, lon, timezone):
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min"
            f"&temperature_unit=fahrenheit&timezone={timezone}&forecast_days=1"
        )
        data = requests.get(url, timeout=5).json()
        curr = data.get("current", {})
        daily = data.get("daily", {})
        
        wmo = curr.get("weather_code", 0)
        desc, icon = WMO_MAP.get(wmo, ("Unknown", "question_mark"))
        
        high = round(daily.get("temperature_2m_max", [0])[0])
        low = round(daily.get("temperature_2m_min", [0])[0])

        return {
            "status": "healthy",
            "temperature": f"{round(curr.get('temperature_2m', 0))}°",
            "condition": desc,
            "icon": icon,
            "high": f"H:{high}°",
            "low": f"L:{low}°",
            "wmo_code": wmo,
            "updated_at": datetime.now().strftime("%I:%M %p"),
            "alert": None
        }
    except Exception as e:
        sys.stderr.write(f"Error fetching weather: {e}\n")
        return {"status": "offline", "error": str(e)}

# --- Market Agent ---
def fetch_markets():
    try:
        tickers = yf.Tickers("^DJI ^GSPC ^IXIC")
        indices = []
        mapping = {"^DJI": "DOW", "^GSPC": "S&P 500", "^IXIC": "NASDAQ"}
        
        for sym, label in mapping.items():
            hist = tickers.tickers[sym].history(period="2d")
            if len(hist) >= 2:
                prev, last = hist['Close'].iloc[-2], hist['Close'].iloc[-1]
                pct = ((last - prev) / prev) * 100
                indices.append({
                    "ticker": sym,
                    "symbol": label,
                    "value": f"{last:,.2f}",
                    "change": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                    "trend": "up" if pct >= 0 else "down"
                })
        # Calculate top movers from a preset basket
        basket = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'META', 'AMZN', 'GOOGL', 'AMD', 'INTC', 'NFLX']
        movers_tickers = yf.Tickers(' '.join(basket))
        movers = []
        for sym, t in movers_tickers.tickers.items():
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev, last = hist['Close'].iloc[-2], hist['Close'].iloc[-1]
                pct = ((last - prev) / prev) * 100
                movers.append({
                    "ticker": sym,
                    "symbol": sym,
                    "value": f"{last:,.2f}",
                    "change": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                    "trend": "up" if pct >= 0 else "down",
                    "pct_float": pct
                })
        
        # Sort by absolute percent change and take top 5
        movers.sort(key=lambda x: abs(x['pct_float']), reverse=True)
        top_movers = movers[:5]
        for m in top_movers:
            del m['pct_float'] # clean up response

        return {"status": "healthy", "indices": indices, "movers": top_movers}
    except Exception as e:
        sys.stderr.write(f"Error fetching markets: {e}\n")
        return {"status": "offline", "error": str(e)}

# --- News Agent (Gemini Flash Structured Extraction) ---
class ArticleItem(BaseModel):
    title: str
    source: str
    url: str
    is_breaking: bool = Field(default=False)

class NewsCategories(BaseModel):
    world: list[ArticleItem]
    national: list[ArticleItem]
    local: list[ArticleItem]

def fetch_news(api_key: str, loc_name: str):
    if not api_key:
        return {"world": [], "national": [], "local": [], "status": "missing_key"}
    try:
        client = genai.Client(api_key=api_key)
        rss_url = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        raw_titles = [e.title for e in feed.entries[:12]]
        
        prompt = f"Extract and distribute these headlines into three distinct fields: 'world', 'national', and 'local' ({loc_name}). Flag any breaking news:\n{raw_titles}"
        res = client.models.generate_content(
            model='gemini-flash-lite-latest',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=NewsCategories
            )
        )
        parsed = json.loads(res.text or "{}")
        return {
            "status": "healthy",
            "world": parsed.get("world", []),
            "national": parsed.get("national", []),
            "local": parsed.get("local", [])
        }
    except Exception as e:
        sys.stderr.write(f"Error fetching news: {e}\n")
        return {"status": "stale", "items": [], "error": str(e)}

# --- Manager Event Loop ---
def run_manager_loop():
    loc = get_location()
    api_key = (
        os.getenv("VITE_GEMINI_API_KEY") or
        os.getenv("GEMINI_API_KEY") or
        keyring.get_password("AiDashboard", "gemini_api_key") or
        "PLACEHOLDER_KEY"
    )

    news_data = {"status": "stale", "items": []}
    last_news_time = 0

    while True:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_weather = executor.submit(fetch_weather, loc["lat"], loc["lon"], loc["timezone"])
            future_markets = executor.submit(fetch_markets)
            
            # Throttle API calls to Gemini (News) to once every 15 minutes
            if time.time() - last_news_time >= 900:
                future_news = executor.submit(fetch_news, api_key, str(loc["city"]))
                news_data = future_news.result()
                last_news_time = time.time()

            weather_data = future_weather.result()
            market_data = future_markets.result()

        state_event = {
            "type": "STATE_UPDATE",
            "timestamp": int(time.time()),
            "location": loc,
            "weather": weather_data,
            "markets": market_data,
            "news": news_data
        }

        # Emit Line-Delimited JSON to stdout for Tauri IPC
        if IPC_STDOUT:
            IPC_STDOUT.write(json.dumps(state_event) + "\n")
            IPC_STDOUT.flush()
        
        time.sleep(30) # Poll cycle

if __name__ == "__main__":
    run_manager_loop()
