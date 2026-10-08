import discord
import os
import re
import asyncio
import time
import random
import json
import io
import requests
import threading
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from openai import OpenAI

MAXCONV_API_KEY = os.environ.get("MAXCONV_API_KEY")
MAXCONV_API_BASE = "https://papi.maxconv.com/v1"

try:
    import zoneinfo
    EST = zoneinfo.ZoneInfo("America/New_York")
except ImportError:
    EST = timezone(timedelta(hours=-5))

def get_maxconv_revenue():
    if not MAXCONV_API_KEY:
        return "no_api_key"
    
    target_date = datetime.now(EST).strftime('%Y-%m-%d')
    
    try:
        headers = {
            "X-Api-Key": MAXCONV_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "group_by": ["ct1"],
            "metrics": ["uniq_visits_ip", "uniq_clicks_ip", "convs", "revenue"],
            "start_time": f"{target_date} 00:00:00",
            "end_time": f"{target_date} 23:59:59",
            "timezone": "America/New_York",
            "page_size": 500
        }
        resp = requests.post(f"{MAXCONV_API_BASE}/report", json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("suc"):
                return data.get("data", [])
            else:
                print(f"⚠️ MaxConv API error: {data.get('msg', 'unknown')}")
                return []
        else:
            print(f"⚠️ MaxConv API HTTP {resp.status_code}: {resp.text}")
            return []
    except Exception as e:
        print(f"❌ MaxConv API error: {e}")
        return []

def get_maxconv_subid_offers(subid):
    if not MAXCONV_API_KEY:
        return "no_api_key"
    
    target_date = datetime.now(EST).strftime('%Y-%m-%d')
    
    try:
        headers = {
            "X-Api-Key": MAXCONV_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "group_by": ["ct1", "offer"],
            "metrics": ["uniq_clicks_ip", "convs", "revenue"],
            "start_time": f"{target_date} 00:00:00",
            "end_time": f"{target_date} 23:59:59",
            "timezone": "America/New_York",
            "page_size": 500
        }
        resp = requests.post(f"{MAXCONV_API_BASE}/report", json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("suc"):
                return [r for r in data.get("data", []) if r.get("ct1", "").lower() == subid.lower()]
            else:
                print(f"⚠️ MaxConv API error: {data.get('msg', 'unknown')}")
                return []
        else:
            print(f"⚠️ MaxConv API HTTP {resp.status_code}: {resp.text}")
            return []
    except Exception as e:
        print(f"❌ MaxConv API error: {e}")
        return []

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET")
SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2024-10")

TOKEN_FILE = "shopify_token.json"

def load_saved_token():
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                data = json.load(f)
                return data.get("access_token")
    except:
        pass
    return None

def save_token(token):
    with open(TOKEN_FILE, 'w') as f:
        json.dump({"access_token": token}, f)

if not SHOPIFY_ACCESS_TOKEN:
    saved = load_saved_token()
    if saved:
        SHOPIFY_ACCESS_TOKEN = saved
        print(f"✅ Loaded Shopify access token from saved file")

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Your Shopify domain
SHOPIFY_STORE_DOMAIN = "uy2q14-an.myshopify.com"
SHOPIFY_BASE_URL = f"https://{SHOPIFY_STORE_DOMAIN}/"

# Cloudflare Worker cloak page uploader
WORKER_URL = os.environ.get("WORKER_URL", "https://palemoonshop.com")
UPLOAD_SECRET = os.environ.get("UPLOAD_SECRET", "")

# Domain rotation for cloak reply URLs (round-robin)
import itertools
WORKER_DOMAINS = [d.strip() for d in os.environ.get("WORKER_DOMAINS", WORKER_URL).split(",")]
_domain_cycle = itertools.cycle(WORKER_DOMAINS)

def next_domain():
    return next(_domain_cycle)

def resolve_domain(domain_arg):
    """Match a bare domain string (e.g. 'dewleaf.shop') against WORKER_DOMAINS.
    Returns the full https:// URL if found, or None if not in the list."""
    needle = domain_arg.lower().strip().strip("/").replace("https://", "").replace("http://", "")
    for d in WORKER_DOMAINS:
        if d.lower().replace("https://", "").replace("http://", "").strip("/") == needle:
            return d.rstrip("/")
    return None

# Cache of created pages to avoid duplicate API calls
CREATED_PAGES_CACHE = set()
CREATED_PAGES_FILE = "created_pages_cache.json"

def load_created_pages():
    try:
        if os.path.exists(CREATED_PAGES_FILE):
            with open(CREATED_PAGES_FILE, 'r') as f:
                return set(json.load(f))
    except:
        pass
    return set()

def save_created_pages():
    try:
        with open(CREATED_PAGES_FILE, 'w') as f:
            json.dump(list(CREATED_PAGES_CACHE), f)
    except:
        pass

CREATED_PAGES_CACHE = load_created_pages()

PAGE_TOPICS = [
    "sustainable living tips", "indoor gardening guide", "home workout routines",
    "healthy smoothie recipes", "travel photography tips", "DIY home decor ideas",
    "meditation and mindfulness", "pet care essentials", "beginner cooking techniques",
    "outdoor hiking adventures", "budget meal planning", "yoga for beginners",
    "creative journaling ideas", "home organization hacks", "seasonal fashion trends",
    "coffee brewing methods", "weekend brunch recipes", "digital detox strategies",
    "bicycle maintenance tips", "stargazing for beginners", "houseplant care guide",
    "natural skincare routines", "book club recommendations", "camping essentials checklist",
    "watercolor painting basics", "fermented foods guide", "board game night ideas",
    "morning routine optimization", "essential oil uses", "vintage furniture restoration",
    "birdwatching for beginners", "homemade candle making", "rock climbing basics",
    "aquarium setup guide", "pottery and ceramics intro", "smartphone photography tricks",
    "meal prep for the week", "knitting patterns for beginners", "urban sketching tips",
    "composting at home", "beach vacation packing list", "calligraphy for beginners",
    "home brewing basics", "marathon training plan", "succulent garden design",
    "acoustic guitar lessons", "woodworking project ideas", "essential kitchen gadgets",
    "landscape design inspiration", "aromatherapy basics", "family game ideas",
    "winter sports guide", "healthy snack alternatives", "nature walk meditation",
    "sourdough bread baking", "minimalist wardrobe tips", "fishing for beginners",
    "puzzle solving strategies", "herb garden setup", "sunrise yoga practice",
    "craft beer appreciation", "mountain biking trails", "art museum virtual tours",
    "homemade pasta recipes", "wildlife photography tips", "cozy reading nook ideas",
    "farmer market shopping guide", "pottery wheel techniques", "hammock camping guide",
    "tea ceremony traditions", "cloud watching guide", "flower arrangement basics",
    "road trip planning tips", "kite flying adventures", "autumn leaf crafts",
    "ice cream making at home", "treehouse design ideas", "seashell collecting guide",
    "botanical illustration tips", "rainy day activities", "sunset chasing adventures"
]

PAGE_STYLES = [
    "magazine-style article", "how-to guide", "listicle with tips",
    "personal blog post", "product review roundup", "educational resource",
    "seasonal guide", "beginner tutorial", "expert advice column",
    "lifestyle feature", "curated collection", "step-by-step walkthrough"
]

# ── Page Theme Randomisation System ─────────────────────────────────────────

PAGE_TITLE_TEMPLATES = [
    "{topic}",
    "The Complete Guide to {topic}",
    "Everything You Need to Know About {topic}",
    "{topic}: A Practical Guide",
    "Getting Started with {topic}",
    "The Beginner's Guide to {topic}",
    "Mastering {topic}",
    "{topic} Made Simple",
    "Your Guide to {topic}",
    "The Art of {topic}",
    "Discovering {topic}",
    "{topic} Essentials",
    "The {topic} Handbook",
    "Understanding {topic}",
    "All About {topic}",
    "{topic} Tips & Ideas",
    "Exploring {topic}",
    "A Deep Dive into {topic}",
    "{topic} for Everyone",
    "The Joy of {topic}",
]

COLOR_PALETTES = [
    {"name":"ocean","bg":"#f0f7ff","text":"#1a2e44","accent":"#0077b6","header_bg":"#03045e","header_text":"#ffffff","btn":"#0077b6","btn_text":"#ffffff","card_bg":"#ffffff","border":"#90e0ef"},
    {"name":"forest","bg":"#f1f8e9","text":"#1b3a1e","accent":"#2d6a4f","header_bg":"#1b4332","header_text":"#d8f3dc","btn":"#40916c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#95d5b2"},
    {"name":"sunset","bg":"#fff3e0","text":"#3e1f00","accent":"#e76f51","header_bg":"#c1440e","header_text":"#fff8f0","btn":"#e76f51","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f4a261"},
    {"name":"lavender","bg":"#f3f0ff","text":"#2d1b69","accent":"#7c3aed","header_bg":"#4c1d95","header_text":"#ede9fe","btn":"#7c3aed","btn_text":"#ffffff","card_bg":"#ffffff","border":"#c4b5fd"},
    {"name":"rose","bg":"#fff1f2","text":"#4c0519","accent":"#e11d48","header_bg":"#881337","header_text":"#ffe4e6","btn":"#e11d48","btn_text":"#ffffff","card_bg":"#ffffff","border":"#fda4af"},
    {"name":"midnight","bg":"#0f172a","text":"#e2e8f0","accent":"#38bdf8","header_bg":"#020617","header_text":"#f0f9ff","btn":"#0ea5e9","btn_text":"#ffffff","card_bg":"#1e293b","border":"#334155"},
    {"name":"citrus","bg":"#fffbeb","text":"#3b2000","accent":"#d97706","header_bg":"#92400e","header_text":"#fef3c7","btn":"#f59e0b","btn_text":"#ffffff","card_bg":"#ffffff","border":"#fcd34d"},
    {"name":"mint","bg":"#f0fdf4","text":"#14532d","accent":"#16a34a","header_bg":"#15803d","header_text":"#dcfce7","btn":"#22c55e","btn_text":"#ffffff","card_bg":"#ffffff","border":"#86efac"},
    {"name":"charcoal","bg":"#f8fafc","text":"#1e293b","accent":"#64748b","header_bg":"#1e293b","header_text":"#f1f5f9","btn":"#475569","btn_text":"#ffffff","card_bg":"#ffffff","border":"#cbd5e1"},
    {"name":"coral","bg":"#fff5f0","text":"#451a0a","accent":"#f97316","header_bg":"#c2410c","header_text":"#fff7ed","btn":"#ea580c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#fed7aa"},
    {"name":"teal","bg":"#f0fdfa","text":"#134e4a","accent":"#0d9488","header_bg":"#115e59","header_text":"#ccfbf1","btn":"#14b8a6","btn_text":"#ffffff","card_bg":"#ffffff","border":"#99f6e4"},
    {"name":"indigo","bg":"#eef2ff","text":"#1e1b4b","accent":"#4f46e5","header_bg":"#312e81","header_text":"#e0e7ff","btn":"#6366f1","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a5b4fc"},
    {"name":"warm_gray","bg":"#fafaf9","text":"#292524","accent":"#78716c","header_bg":"#44403c","header_text":"#fafaf9","btn":"#57534e","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d6d3d1"},
    {"name":"sky","bg":"#f0f9ff","text":"#0c4a6e","accent":"#0284c7","header_bg":"#075985","header_text":"#e0f2fe","btn":"#0369a1","btn_text":"#ffffff","card_bg":"#ffffff","border":"#7dd3fc"},
    {"name":"crimson","bg":"#fff0f0","text":"#4a0000","accent":"#dc2626","header_bg":"#7f1d1d","header_text":"#fee2e2","btn":"#b91c1c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#fca5a5"},
    {"name":"emerald","bg":"#ecfdf5","text":"#064e3b","accent":"#059669","header_bg":"#065f46","header_text":"#d1fae5","btn":"#10b981","btn_text":"#ffffff","card_bg":"#ffffff","border":"#6ee7b7"},
    {"name":"plum","bg":"#fdf4ff","text":"#3b0764","accent":"#a21caf","header_bg":"#701a75","header_text":"#fae8ff","btn":"#c026d3","btn_text":"#ffffff","card_bg":"#ffffff","border":"#e879f9"},
    {"name":"sand","bg":"#fefce8","text":"#3b2f00","accent":"#ca8a04","header_bg":"#854d0e","header_text":"#fef9c3","btn":"#eab308","btn_text":"#ffffff","card_bg":"#ffffff","border":"#fde047"},
    {"name":"slate","bg":"#f8fafc","text":"#0f172a","accent":"#3b82f6","header_bg":"#1e3a5f","header_text":"#dbeafe","btn":"#2563eb","btn_text":"#ffffff","card_bg":"#ffffff","border":"#93c5fd"},
    {"name":"blush","bg":"#fdf2f8","text":"#500724","accent":"#db2777","header_bg":"#9d174d","header_text":"#fce7f3","btn":"#ec4899","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f9a8d4"},
    {"name":"night_ocean","bg":"#001220","text":"#cce4f7","accent":"#00b4d8","header_bg":"#000814","header_text":"#90e0ef","btn":"#0096c7","btn_text":"#ffffff","card_bg":"#012840","border":"#0077b6"},
    {"name":"earth","bg":"#f5f0eb","text":"#2c1810","accent":"#8b5e3c","header_bg":"#5c3317","header_text":"#f5e6d3","btn":"#a0522d","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d2b48c"},
    {"name":"arctic","bg":"#f0f8ff","text":"#1c3a4a","accent":"#4da6c8","header_bg":"#2c7da0","header_text":"#e8f4f8","btn":"#2196f3","btn_text":"#ffffff","card_bg":"#ffffff","border":"#b3d9f0"},
    {"name":"volcano","bg":"#fff9f5","text":"#3d0000","accent":"#ff4500","header_bg":"#8b1a00","header_text":"#ffe5d9","btn":"#e63900","btn_text":"#ffffff","card_bg":"#ffffff","border":"#ffb499"},
    {"name":"sage","bg":"#f4f7f0","text":"#2a3a28","accent":"#6b8f71","header_bg":"#4a6741","header_text":"#e8f0e5","btn":"#5a7a52","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a8c5a0"},
    {"name":"deep_space","bg":"#0a0a1a","text":"#e0e0ff","accent":"#6c63ff","header_bg":"#05051a","header_text":"#b8b5ff","btn":"#6c63ff","btn_text":"#ffffff","card_bg":"#12122e","border":"#2d2d6e"},
    {"name":"candy","bg":"#fff0f5","text":"#4a0020","accent":"#ff4081","header_bg":"#c2185b","header_text":"#fce4ec","btn":"#e91e63","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f8bbd0"},
    {"name":"copper","bg":"#fdf6f0","text":"#2c1810","accent":"#b87333","header_bg":"#7a4a2a","header_text":"#fdf6f0","btn":"#b87333","btn_text":"#ffffff","card_bg":"#ffffff","border":"#deb887"},
    {"name":"denim","bg":"#f0f4ff","text":"#0a1628","accent":"#3a5a9b","header_bg":"#1a2d4e","header_text":"#dde8ff","btn":"#2952a3","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a8bfe8"},
    {"name":"jade","bg":"#f0fff8","text":"#002a1a","accent":"#00a86b","header_bg":"#006b3c","header_text":"#ccffee","btn":"#00a86b","btn_text":"#ffffff","card_bg":"#ffffff","border":"#88e8c0"},
    {"name":"ruby","bg":"#fff5f5","text":"#3d0000","accent":"#9b111e","header_bg":"#6b0d14","header_text":"#ffe8e8","btn":"#9b111e","btn_text":"#ffffff","card_bg":"#ffffff","border":"#e8a0a8"},
    {"name":"amber","bg":"#fffbf0","text":"#3a2200","accent":"#ff8c00","header_bg":"#8a5200","header_text":"#fff3d6","btn":"#ff8c00","btn_text":"#ffffff","card_bg":"#ffffff","border":"#ffd280"},
    {"name":"silver","bg":"#f5f5f5","text":"#1a1a1a","accent":"#707070","header_bg":"#303030","header_text":"#f0f0f0","btn":"#505050","btn_text":"#ffffff","card_bg":"#ffffff","border":"#c0c0c0"},
    {"name":"peacock","bg":"#f0fcff","text":"#002030","accent":"#008080","header_bg":"#004050","header_text":"#ccf5ff","btn":"#007090","btn_text":"#ffffff","card_bg":"#ffffff","border":"#80d8e8"},
    {"name":"raspberry","bg":"#fff0f5","text":"#3d0020","accent":"#c51162","header_bg":"#880e4f","header_text":"#fce4ec","btn":"#c51162","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f48fb1"},
    {"name":"pine","bg":"#f0f8f2","text":"#0a2010","accent":"#2e7d32","header_bg":"#1b5e20","header_text":"#dcedc8","btn":"#388e3c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a5d6a7"},
    {"name":"gold","bg":"#fffdf0","text":"#2a1c00","accent":"#d4a017","header_bg":"#7a5c00","header_text":"#fff8d6","btn":"#c8960c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f0d060"},
    {"name":"lilac","bg":"#faf0ff","text":"#2a0050","accent":"#9c4dcc","header_bg":"#6a0dad","header_text":"#f5d6ff","btn":"#8e24aa","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d7a8f0"},
    {"name":"storm","bg":"#f0f4fa","text":"#0a1428","accent":"#4a6fa5","header_bg":"#1a2d4e","header_text":"#d0dcf0","btn":"#3a5a8a","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a0b8d8"},
    {"name":"rust","bg":"#fff8f5","text":"#2a0800","accent":"#b7410e","header_bg":"#7a2800","header_text":"#ffe8d8","btn":"#c0390a","btn_text":"#ffffff","card_bg":"#ffffff","border":"#e8a880"},
    {"name":"aqua","bg":"#f0ffff","text":"#002828","accent":"#00bcd4","header_bg":"#006878","header_text":"#cdf8ff","btn":"#00a0b4","btn_text":"#ffffff","card_bg":"#ffffff","border":"#80e8f8"},
    {"name":"cocoa","bg":"#fdf5ef","text":"#1e0c00","accent":"#7b4a2e","header_bg":"#4a2c1a","header_text":"#f5e0d0","btn":"#8b5a3c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d8b090"},
    {"name":"mauve","bg":"#f8f0f8","text":"#28002a","accent":"#8b5a8e","header_bg":"#58285a","header_text":"#f0d8f2","btn":"#7a4a7c","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d0a8d2"},
    {"name":"frost","bg":"#f0f8ff","text":"#0a2038","accent":"#5b9bd5","header_bg":"#1a4a78","header_text":"#d8eeff","btn":"#4080c0","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a8d0f0"},
    {"name":"tangerine","bg":"#fff8f0","text":"#2a1000","accent":"#ff6b2b","header_bg":"#c84000","header_text":"#fff0e0","btn":"#e85a20","btn_text":"#ffffff","card_bg":"#ffffff","border":"#ffa870"},
    {"name":"seafoam","bg":"#f0fdf8","text":"#002a20","accent":"#2ecf9a","header_bg":"#0a7a5c","header_text":"#ccf8e8","btn":"#20b88a","btn_text":"#ffffff","card_bg":"#ffffff","border":"#88e8c8"},
    {"name":"graphite","bg":"#f8f8fa","text":"#101018","accent":"#505060","header_bg":"#202030","header_text":"#e0e0f0","btn":"#404050","btn_text":"#ffffff","card_bg":"#ffffff","border":"#b0b0c0"},
    {"name":"cream","bg":"#fdfbf5","text":"#2a2010","accent":"#a08050","header_bg":"#604020","header_text":"#f8f0e0","btn":"#8a6840","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d8c8a0"},
    {"name":"electric","bg":"#f0f0ff","text":"#080820","accent":"#3d00e0","header_bg":"#1a0070","header_text":"#d8d0ff","btn":"#5020f0","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a090f8"},
    {"name":"blossom","bg":"#fff5fa","text":"#3a001a","accent":"#e0529c","header_bg":"#a0206a","header_text":"#ffe0f0","btn":"#d04090","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f8b0d8"},
    {"name":"obsidian","bg":"#111118","text":"#d8d8e8","accent":"#a78bfa","header_bg":"#080810","header_text":"#c4b5fd","btn":"#8b5cf6","btn_text":"#ffffff","card_bg":"#1e1e2e","border":"#3d3d5e"},
    {"name":"peach","bg":"#fff9f5","text":"#3a1800","accent":"#f4845f","header_bg":"#c05030","header_text":"#ffe8d8","btn":"#e86040","btn_text":"#ffffff","card_bg":"#ffffff","border":"#f8c0a0"},
    {"name":"glacier","bg":"#f5faff","text":"#082030","accent":"#48a8d8","header_bg":"#1a5878","header_text":"#d8f0ff","btn":"#3090c0","btn_text":"#ffffff","card_bg":"#ffffff","border":"#a0d8f0"},
    {"name":"aubergine","bg":"#f8f0fa","text":"#200828","accent":"#7b2d8b","header_bg":"#4a1258","header_text":"#ecd8f5","btn":"#6a2080","btn_text":"#ffffff","card_bg":"#ffffff","border":"#c898e0"},
    {"name":"terracotta","bg":"#fdf5f0","text":"#2a0c00","accent":"#c2703a","header_bg":"#8a3c18","header_text":"#f8e0d0","btn":"#b06030","btn_text":"#ffffff","card_bg":"#ffffff","border":"#e0b090"},
    {"name":"neon","bg":"#f0fff0","text":"#001800","accent":"#00e676","header_bg":"#004020","header_text":"#b0ffd8","btn":"#00c060","btn_text":"#000000","card_bg":"#ffffff","border":"#80e8b0"},
    {"name":"burgundy","bg":"#fff5f5","text":"#280010","accent":"#800020","header_bg":"#500010","header_text":"#ffe0e5","btn":"#700018","btn_text":"#ffffff","card_bg":"#ffffff","border":"#d08090"},
]

LAYOUT_THEMES = [
    "hero", "card", "split", "magazine", "minimal", "bold", "gradient", "vintage",
    "centered", "fullwidth", "stacked", "newspaper", "dark_card", "mosaic",
    "banner", "editorial", "asymmetric", "sidebar_left", "overlay", "portfolio",
]

FONT_PAIRS = [
    {"heading": "Georgia, serif", "body": "Arial, sans-serif", "import": ""},
    {"heading": "'Palatino Linotype', Palatino, serif", "body": "Verdana, sans-serif", "import": ""},
    {"heading": "Impact, Haettenschweiler, sans-serif", "body": "Tahoma, sans-serif", "import": ""},
    {"heading": "Garamond, serif", "body": "Trebuchet MS, sans-serif", "import": ""},
    {"heading": "Arial Black, sans-serif", "body": "Arial, sans-serif", "import": ""},
    {"heading": "'Times New Roman', Times, serif", "body": "Helvetica, sans-serif", "import": ""},
    {"heading": "Verdana, sans-serif", "body": "Georgia, serif", "import": ""},
    {"heading": "Courier New, Courier, monospace", "body": "Arial, sans-serif", "import": ""},
    {"heading": "Trebuchet MS, sans-serif", "body": "Verdana, sans-serif", "import": ""},
    {"heading": "'Century Gothic', sans-serif", "body": "Tahoma, sans-serif", "import": ""},
    {"heading": "Copperplate, fantasy", "body": "Optima, sans-serif", "import": ""},
    {"heading": "Didact Gothic, sans-serif", "body": "Lato, sans-serif", "import": ""},
    {"heading": "'Playfair Display', serif", "body": "'Lato', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Lato:wght@400;700&display=swap');"},
    {"heading": "'Merriweather', serif", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&family=Open+Sans&display=swap');"},
    {"heading": "'Raleway', sans-serif", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Raleway:wght@400;700&family=Roboto&display=swap');"},
    {"heading": "'Oswald', sans-serif", "body": "'Lato', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;700&family=Lato&display=swap');"},
    {"heading": "'Montserrat', sans-serif", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&family=Open+Sans&display=swap');"},
    {"heading": "'Lora', serif", "body": "'Source Sans Pro', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Lora:wght@400;700&family=Source+Sans+Pro&display=swap');"},
    {"heading": "'Libre Baskerville', serif", "body": "'Nunito', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=Nunito&display=swap');"},
    {"heading": "'Abril Fatface', serif", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Abril+Fatface&family=Roboto&display=swap');"},
    {"heading": "'Josefin Sans', sans-serif", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@400;700&family=Roboto&display=swap');"},
    {"heading": "'Cinzel', serif", "body": "'Lato', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Lato&display=swap');"},
    {"heading": "'Poppins', sans-serif", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;700&family=Open+Sans&display=swap');"},
    {"heading": "'Nunito', sans-serif", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;700&family=Open+Sans&display=swap');"},
    {"heading": "'Quicksand', sans-serif", "body": "'Raleway', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Quicksand:wght@400;700&family=Raleway&display=swap');"},
    {"heading": "'Exo 2', sans-serif", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@400;700&family=Roboto&display=swap');"},
    {"heading": "'Archivo', sans-serif", "body": "'Lato', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;700&family=Lato&display=swap');"},
    {"heading": "'Work Sans', sans-serif", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Work+Sans:wght@400;700&family=Roboto&display=swap');"},
    {"heading": "'DM Serif Display', serif", "body": "'DM Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans&display=swap');"},
    {"heading": "'Space Grotesk', sans-serif", "body": "'Inter', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700&family=Inter&display=swap');"},
    {"heading": "'Cormorant Garamond', serif", "body": "'Karla', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;700&family=Karla&display=swap');"},
    {"heading": "'Spectral', serif", "body": "'IBM Plex Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;700&family=IBM+Plex+Sans&display=swap');"},
    {"heading": "'Domine', serif", "body": "'Fira Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Domine:wght@400;700&family=Fira+Sans&display=swap');"},
    {"heading": "'Rokkitt', serif", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Rokkitt:wght@400;700&family=Open+Sans&display=swap');"},
    {"heading": "'Zilla Slab', serif", "body": "'Cabin', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@400;700&family=Cabin&display=swap');"},
    {"heading": "'Yeseva One', serif", "body": "'Josefin Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Yeseva+One&family=Josefin+Sans&display=swap');"},
    {"heading": "'Bebas Neue', sans-serif", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Open+Sans&display=swap');"},
    {"heading": "'Anton', sans-serif", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Anton&family=Roboto&display=swap');"},
    {"heading": "'Righteous', sans-serif", "body": "'Lato', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Righteous&family=Lato&display=swap');"},
    {"heading": "'Lobster', cursive", "body": "'Open Sans', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Lobster&family=Open+Sans&display=swap');"},
    {"heading": "'Pacifico', cursive", "body": "'Roboto', sans-serif", "import": "@import url('https://fonts.googleapis.com/css2?family=Pacifico&family=Roboto&display=swap');"},
]

IMAGE_KEYWORDS = [
    "nature","wellness","lifestyle","fitness","food","travel","technology","fashion","beauty",
    "home","garden","coffee","yoga","hiking","cooking","adventure","sunrise","ocean","forest",
    "mountains","city","flowers","autumn","winter","summer","spring","meditation","wellness",
    "health","organic","minimal","texture","abstract","architecture","interior","bookshelf",
    "candles","plants","herbs","fruit","smoothie","running","cycling","photography","art",
    "music","reading","writing","creativity","motivation","success","teamwork","culture",
    "landscape","beach","camping","climbing","surfing","skiing","dance","sport","workout",
    "skincare","haircare","perfume","vintage","retro","modern","rustic","cozy","elegant",
    "tropical","desert","farm","harvest","bakery","tea","herbs","spices","market","craft",
    "pottery","painting","drawing","sculpture","jewelry","fashion","shoes","accessories",
    "sunrise","sunset","sky","stars","moon","rain","snow","fog","wind","water","fire",
    "wood","stone","metal","glass","paper","fabric","silk","leather","cotton","wool",
]

DECORATIVE_BADGES = [
    "✦ Featured", "★ Editor's Pick", "◈ Trending", "❋ Popular", "⬡ Curated",
    "▸ Must Read", "◉ Staff Pick", "✿ Top Pick", "⬢ Highlighted", "◆ Premium",
    "⚡ Hot", "✔ Verified", "☀ Daily Pick", "♦ Exclusive", "✪ Top Rated",
    "→ New Arrival", "◐ Limited", "✵ Best Of", "◑ Fresh Pick", "⬛ Bold Choice",
    "⊕ Just In", "⊞ Community Pick", "✶ Spotlight", "◇ Hand Picked", "☆ Rising",
]

DIVIDER_STYLES = [
    "border-top: 2px solid {accent}; margin: 24px 0;",
    "border-top: 3px dashed {accent}; margin: 28px 0; opacity: 0.5;",
    "border-top: 4px double {accent}; margin: 24px 0;",
    "height: 3px; background: linear-gradient(to right, transparent, {accent}, transparent); margin: 28px 0;",
    "height: 2px; background: {accent}; margin: 24px 0; border-radius: 2px;",
    "border-top: 2px dotted {accent}; margin: 28px 0; opacity: 0.6;",
    "height: 4px; background: linear-gradient(to right, {accent}, transparent); margin: 24px 0; border-radius: 4px;",
    "border-top: 1px solid {accent}; margin: 20px 0; opacity: 0.4;",
    "height: 2px; background: repeating-linear-gradient(90deg, {accent} 0px, {accent} 8px, transparent 8px, transparent 16px); margin: 28px 0;",
    "height: 6px; background: {accent}; margin: 28px 0; border-radius: 3px; opacity: 0.35;",
]

TYPOGRAPHY_SCALES = [
    {"h1": "2em",   "h2": "1.4em", "p": "1.05em", "lh": "1.75"},
    {"h1": "2.5em", "h2": "1.6em", "p": "1em",    "lh": "1.70"},
    {"h1": "1.8em", "h2": "1.3em", "p": "1.1em",  "lh": "1.80"},
    {"h1": "3em",   "h2": "1.9em", "p": "0.95em", "lh": "1.65"},
    {"h1": "1.6em", "h2": "1.2em", "p": "1.15em", "lh": "1.85"},
    {"h1": "2.8em", "h2": "1.7em", "p": "1em",    "lh": "1.70"},
    {"h1": "2.2em", "h2": "1.5em", "p": "1.05em", "lh": "1.75"},
    {"h1": "1.4em", "h2": "1.1em", "p": "1.2em",  "lh": "1.90"},
    {"h1": "3.2em", "h2": "2em",   "p": "0.9em",  "lh": "1.60"},
    {"h1": "1.9em", "h2": "1.35em","p": "1.08em", "lh": "1.78"},
]

BG_PATTERNS = [
    "", "", "", "",
    "radial-gradient(circle, {accent}18 1px, transparent 1px) 0 0 / 22px 22px",
    "linear-gradient(45deg, {accent}10 25%, transparent 25%, transparent 75%, {accent}10 75%), linear-gradient(45deg, {accent}10 25%, transparent 25%, transparent 75%, {accent}10 75%) 15px 15px / 30px 30px",
    "repeating-linear-gradient(0deg, {accent}09, {accent}09 1px, transparent 1px, transparent 42px)",
    "repeating-linear-gradient(90deg, {accent}09, {accent}09 1px, transparent 1px, transparent 42px)",
    "repeating-linear-gradient(135deg, {accent}0c, {accent}0c 2px, transparent 2px, transparent 16px)",
    "radial-gradient(ellipse at 20% 50%, {accent}15 0%, transparent 60%), radial-gradient(ellipse at 80% 50%, {accent}10 0%, transparent 60%)",
]

def pick_image_url(width=800, height=420):
    seed = random.randint(1, 99999)
    keyword = random.choice(IMAGE_KEYWORDS)
    alt_keyword = random.choice(IMAGE_KEYWORDS)
    return f"https://picsum.photos/seed/{seed}/{width}/{height}", f"{keyword} {alt_keyword}"

def _rand_prefix():
    import string
    chars = string.ascii_lowercase
    return ''.join(random.choices(chars, k=random.randint(3, 5)))

def build_styled_page(inner_html, slug):
    random.seed(int.from_bytes(os.urandom(8), 'big') ^ hash(slug))
    px = _rand_prefix()
    palette = random.choice(COLOR_PALETTES)
    layout = random.choice(LAYOUT_THEMES)
    fonts = random.choice(FONT_PAIRS)
    typo = random.choice(TYPOGRAPHY_SCALES)
    bg_pat_tpl = random.choice(BG_PATTERNS)
    bg_pat = bg_pat_tpl.replace("{accent}", palette["accent"]) if bg_pat_tpl else ""
    badge = random.choice(DECORATIVE_BADGES)
    divider_tpl = random.choice(DIVIDER_STYLES)
    divider = divider_tpl.replace("{accent}", palette["accent"])
    br = random.choice(["4px", "8px", "12px", "16px", "0px", "6px", "20px", "24px"])
    img_url, img_alt = pick_image_url()
    img_url2, _ = pick_image_url(400, 300)
    img_h = random.choice([240, 280, 320, 360, 400])
    img_h2 = random.choice([180, 200, 220, 240])
    pad_x = random.choice([24, 28, 32, 36, 40])
    pad_y = random.choice([24, 28, 32, 40, 48])
    max_w = random.choice([700, 760, 820, 860, 900])
    h_align = random.choice(["left", "left", "left", "center"])
    cta_btn_pad = f"{random.choice([10,12,14])}px {random.choice([22,28,34])}px"
    cta_text = random.choice([
        "Explore More", "Learn More", "Discover More", "View More", "Read More",
        "Get Started", "Find Out More", "See More", "Continue Reading", "Dive In",
        "Start Here", "Go Deeper", "Take a Look", "Browse Now",
    ])
    grad_angle = random.choice([135, 120, 150, 160, 45, 90])
    col_ratio = random.choice(["2fr 1fr", "3fr 1fr", "1fr 1fr", "5fr 2fr"])
    shadow = random.choice([
        "0 2px 12px rgba(0,0,0,0.06)",
        "0 4px 24px rgba(0,0,0,0.10)",
        "0 6px 32px rgba(0,0,0,0.14)",
        "0 1px 6px rgba(0,0,0,0.08)",
    ])
    footer_texts = [
        "Curated with care", "Crafted for you", "Thoughtfully made",
        "Quality content", "Explore & discover", "Your trusted guide",
    ]
    footer_text = random.choice(footer_texts)

    # ── Optional modular components ──────────────────────────────────────────
    QUOTES = [
        "Every detail matters.",
        "Timeless wisdom, curated for you.",
        "Small steps lead to big changes.",
        "Quality over everything.",
        "The journey is the destination.",
        "Simplicity is the ultimate sophistication.",
        "Learn something new every day.",
        "The best time to start is now.",
        "Craft your own story.",
        "Made for the curious mind.",
        "Progress, not perfection.",
        "Start small, dream big.",
    ]

    def make_quote():
        q = random.choice(QUOTES)
        return (
            f'<blockquote style="border-left:4px solid {palette["accent"]};margin:24px 0;'
            f'padding:12px 20px;background:{palette["card_bg"]};border-radius:0 {br} {br} 0;'
            f'font-style:italic;color:{palette["accent"]};font-family:{fonts["heading"]};'
            f'font-size:1.1em;">&ldquo;{q}&rdquo;</blockquote>'
        )

    def make_stats():
        pool = [
            ("10K+", "Happy Readers"), ("500+", "Tips Shared"), ("5★", "Top Rated"),
            ("100%", "Verified Info"), ("Daily", "Updated"), ("Free", "Always"),
            ("Expert", "Reviewed"), ("#1", "Resource"), ("Trusted", "Source"),
            ("New", "Each Week"), ("Easy", "To Follow"), ("Proven", "Methods"),
        ]
        chosen = random.sample(pool, 3)
        cols = "".join(
            f'<div style="text-align:center;padding:10px;">'
            f'<div style="font-family:{fonts["heading"]};font-size:1.7em;font-weight:bold;'
            f'color:{palette["accent"]};">{v}</div>'
            f'<div style="font-size:0.82em;color:{palette["text"]};opacity:0.7;">{l}</div>'
            f'</div>'
            for v, l in chosen
        )
        return (
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;'
            f'background:{palette["card_bg"]};border:1px solid {palette["border"]};'
            f'border-radius:{br};padding:14px;margin:24px 0;">{cols}</div>'
        )

    def make_highlight():
        tips = [
            "Pro Tip: Consistency is the key to lasting results.",
            "Quick Tip: Start small and build momentum gradually.",
            "Did You Know? Small daily habits compound into big changes.",
            "Key Insight: Focus on progress, not perfection.",
            "Remember: Every expert was once a beginner.",
            "Top Tip: Track your progress to stay motivated.",
            "Reminder: Take it one step at a time.",
            "Quick Win: Set one small goal for today.",
            "Fun Fact: Learning something new rewires your brain.",
        ]
        tip = random.choice(tips)
        return (
            f'<div style="background:{palette["accent"]};color:{palette["btn_text"]};'
            f'padding:14px 20px;border-radius:{br};margin:24px 0;'
            f'font-family:{fonts["heading"]};font-size:0.96em;">{tip}</div>'
        )

    def make_tags():
        pool = [
            "Lifestyle", "Wellness", "Tips", "Guide", "How-To", "Beginner", "Advanced",
            "Trending", "Popular", "Featured", "Essential", "Must-Try", "Quick", "Easy",
            "Proven", "Curated", "Expert", "Fresh", "Classic", "Modern",
        ]
        tags = random.sample(pool, random.randint(3, 6))
        items = "".join(
            f'<span style="display:inline-block;background:{palette["card_bg"]};'
            f'border:1px solid {palette["border"]};color:{palette["text"]};'
            f'padding:4px 12px;border-radius:20px;font-size:0.82em;margin:3px;">{t}</span>'
            for t in tags
        )
        return f'<div style="margin:20px 0;">{items}</div>'

    def make_feature_row():
        items = [
            ("✓", "Easy to follow"), ("✓", "Beginner friendly"), ("✓", "Expert insights"),
            ("★", "Top rated"), ("★", "Community loved"), ("→", "Step by step"),
            ("→", "Proven approach"), ("◆", "Curated content"), ("◆", "Up to date"),
        ]
        chosen = random.sample(items, 3)
        cols = "".join(
            f'<div style="padding:12px;text-align:center;">'
            f'<div style="font-size:1.4em;color:{palette["accent"]};">{icon}</div>'
            f'<div style="font-size:0.9em;margin-top:4px;color:{palette["text"]};">{label}</div>'
            f'</div>'
            for icon, label in chosen
        )
        return (
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;'
            f'margin:24px 0;background:{palette["card_bg"]};border-radius:{br};'
            f'border:1px solid {palette["border"]};padding:8px;">{cols}</div>'
        )

    def make_testimonial():
        names = ["Sarah M.", "James T.", "Emily R.", "Carlos V.", "Lisa K.", "David H.", "Mia S.", "Tom B.", "Priya N.", "Alex W."]
        reviews = [
            "This completely changed how I approach it. Highly recommend!",
            "Exactly what I was looking for. Clear, simple, and effective.",
            "Incredibly helpful resource. Saved me so much time.",
            "Game changer for me. The tips are actionable and work.",
            "Loved every bit of it. Will share with my friends too.",
            "Couldn't believe how much I learned in such a short read.",
            "Simple, practical, and genuinely useful. Five stars.",
        ]
        name = random.choice(names)
        review = random.choice(reviews)
        stars = "★" * random.randint(4, 5)
        return (
            f'<div style="background:{palette["card_bg"]};border:1px solid {palette["border"]};'
            f'border-radius:{br};padding:16px 20px;margin:24px 0;">'
            f'<div style="color:#f4b400;font-size:1.1em;margin-bottom:6px;">{stars}</div>'
            f'<p style="margin:0 0 8px;font-style:italic;color:{palette["text"]};font-size:0.95em;">&ldquo;{review}&rdquo;</p>'
            f'<div style="font-family:{fonts["heading"]};font-size:0.82em;color:{palette["accent"]};font-weight:bold;">— {name}</div>'
            f'</div>'
        )

    def make_checklist():
        items = [
            "Easy to get started", "No experience required", "Practical advice included",
            "Beginner friendly", "Expert tips inside", "Fully up to date",
            "Trusted by thousands", "Step-by-step guidance", "Real results",
            "Actionable takeaways", "Saves time instantly", "Works for everyone",
        ]
        chosen = random.sample(items, random.randint(3, 5))
        rows = "".join(
            f'<div style="padding:6px 0;border-bottom:1px solid {palette["border"]};'
            f'color:{palette["text"]};font-size:0.95em;">'
            f'<span style="color:{palette["accent"]};margin-right:8px;font-weight:bold;">✓</span>{item}</div>'
            for item in chosen
        )
        return f'<div style="margin:20px 0;">{rows}</div>'

    def make_progress():
        items = [
            ("Beginner Friendly", random.randint(85, 99)),
            ("Expert Approved", random.randint(80, 97)),
            ("Community Rating", random.randint(88, 99)),
        ]
        rows = "".join(
            f'<div style="margin-bottom:12px;">'
            f'<div style="display:flex;justify-content:space-between;font-size:0.85em;'
            f'color:{palette["text"]};margin-bottom:4px;"><span>{label}</span><span>{pct}%</span></div>'
            f'<div style="background:{palette["border"]};border-radius:4px;height:8px;">'
            f'<div style="background:{palette["accent"]};width:{pct}%;height:8px;border-radius:4px;"></div>'
            f'</div></div>'
            for label, pct in items
        )
        return f'<div style="margin:20px 0;">{rows}</div>'

    # Randomly decide which extras appear and in what order
    extras = []
    if random.random() < 0.55: extras.append(make_quote())
    if random.random() < 0.40: extras.append(make_stats())
    if random.random() < 0.45: extras.append(make_highlight())
    if random.random() < 0.35: extras.append(make_tags())
    if random.random() < 0.30: extras.append(make_feature_row())
    if random.random() < 0.35: extras.append(make_testimonial())
    if random.random() < 0.30: extras.append(make_checklist())
    if random.random() < 0.28: extras.append(make_progress())
    random.shuffle(extras)
    split = random.randint(0, len(extras))
    extras_top = "".join(extras[:split])
    extras_bot = "".join(extras[split:])
    content = f"{extras_top}{inner_html}{extras_bot}"

    font_import = fonts.get("import", "")
    bg_image_css = f"background-image: {bg_pat};" if bg_pat else ""

    base_css = f"""<style>
{font_import}
.mexo-page {{
    font-family: {fonts["body"]};
    color: {palette["text"]};
    background: {palette["bg"]};
    {bg_image_css}
    max-width: {max_w}px;
    margin: 0 auto;
    padding: 0 0 40px 0;
    line-height: {typo["lh"]};
}}
.mexo-page h1, .mexo-page h2, .mexo-page h3 {{
    font-family: {fonts["heading"]};
    color: {palette["accent"]};
    line-height: 1.25;
    margin-bottom: 14px;
    text-align: {h_align};
}}
.mexo-page h1 {{ font-size: {typo["h1"]}; }}
.mexo-page h2 {{ font-size: {typo["h2"]}; }}
.mexo-page p {{ margin-bottom: 16px; font-size: {typo["p"]}; }}
.mexo-page ul {{ padding-left: 22px; }}
.mexo-page li {{ margin-bottom: 8px; }}
.mexo-badge {{
    display: inline-block;
    background: {palette["accent"]};
    color: {palette["btn_text"]};
    font-family: {fonts["heading"]};
    font-size: 0.75em;
    letter-spacing: 1px;
    padding: 4px 12px;
    border-radius: {br};
    margin-bottom: 16px;
    text-transform: uppercase;
}}
.mexo-divider {{ {divider} }}
.mexo-img-main {{
    width: 100%;
    height: {img_h}px;
    object-fit: cover;
    border-radius: {br};
    display: block;
}}
.mexo-img-side {{
    width: 100%;
    height: {img_h2}px;
    object-fit: cover;
    border-radius: {br};
    display: block;
    margin-bottom: 16px;
}}
.mexo-cta {{
    display: inline-block;
    background: {palette["btn"]};
    color: {palette["btn_text"]};
    font-family: {fonts["heading"]};
    padding: {cta_btn_pad};
    border-radius: {br};
    text-decoration: none;
    font-size: 1em;
    margin-top: 12px;
    cursor: pointer;
    letter-spacing: 0.5px;
}}
</style>
"""

    if layout == "hero":
        html = f"""{base_css}
<div class="mexo-page">
  <div style="background:{palette['header_bg']};padding:{pad_y}px {pad_x}px {pad_y-8}px;border-radius:{br} {br} 0 0;">
    <span class="mexo-badge">{badge}</span>
  </div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
  <div style="padding:{pad_y}px {pad_x}px;">
    <div class="mexo-divider"></div>
    {content}
    <div class="mexo-divider"></div>
    <span class="mexo-cta">{cta_text}</span>
  </div>
</div>"""

    elif layout == "card":
        html = f"""{base_css}
<div class="mexo-page">
  <div style="background:{palette['card_bg']};border:1px solid {palette['border']};border-radius:{br};box-shadow:{shadow};overflow:hidden;margin:16px;">
    <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
    <div style="padding:{pad_y}px {pad_x}px;">
      <span class="mexo-badge">{badge}</span>
      <div class="mexo-divider"></div>
      {content}
      <span class="mexo-cta">{cta_text}</span>
    </div>
  </div>
</div>"""

    elif layout == "split":
        left_img = f'<img class="mexo-img-side" src="{img_url}" alt="{img_alt}" /><img class="mexo-img-side" src="{img_url2}" alt="{img_alt}" />'
        right_content = f'<span class="mexo-badge">{badge}</span><div class="mexo-divider"></div>{content}<span class="mexo-cta">{cta_text}</span>'
        if random.random() < 0.5:
            left_col, right_col = left_img, right_content
        else:
            left_col, right_col = right_content, left_img
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_y}px {pad_x}px;">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{pad_x}px;align-items:start;">
    <div>{left_col}</div>
    <div>{right_col}</div>
  </div>
</div>"""

    elif layout == "magazine":
        html = f"""{base_css}
<div class="mexo-page">
  <div style="background:{palette['header_bg']};padding:{pad_y-8}px {pad_x}px;border-radius:{br} {br} 0 0;">
    <span class="mexo-badge">{badge}</span>
  </div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
  <div style="display:grid;grid-template-columns:{col_ratio};gap:{pad_x}px;padding:{pad_y}px {pad_x}px;background:{palette['card_bg']};">
    <div>{content}</div>
    <aside style="border-left:2px solid {palette['border']};padding-left:{pad_x-8}px;">
      <img class="mexo-img-side" src="{img_url2}" alt="{img_alt}" />
      <span class="mexo-cta" style="display:block;text-align:center;margin-top:8px;">{cta_text}</span>
    </aside>
  </div>
</div>"""

    elif layout == "minimal":
        html = f"""{base_css}
<div class="mexo-page" style="max-width:{max_w - 120}px;padding:{pad_y+8}px {pad_x}px;">
  <span class="mexo-badge">{badge}</span>
  <div class="mexo-divider"></div>
  {content}
  <div class="mexo-divider"></div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" />
  <div style="margin-top:{pad_y}px;">
    <span class="mexo-cta">{cta_text}</span>
  </div>
</div>"""

    elif layout == "bold":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;">
  <div style="background:{palette['header_bg']};color:{palette['header_text']};padding:{pad_y+8}px {pad_x}px {pad_y}px;border-radius:{br} {br} 0 0;">
    <span class="mexo-badge">{badge}</span>
    <div style="height:2px;background:{palette['accent']};margin:18px 0;opacity:0.6;"></div>
  </div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
  <div style="padding:{pad_y}px {pad_x}px;background:{palette['card_bg']};">
    {content}
    <span class="mexo-cta">{cta_text}</span>
  </div>
  <div style="background:{palette['header_bg']};padding:18px {pad_x}px;text-align:center;">
    <span style="color:{palette['header_text']};opacity:0.55;font-size:0.84em;font-family:{fonts['body']};">{footer_text}</span>
  </div>
</div>"""

    elif layout == "gradient":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;">
  <div style="background:linear-gradient({grad_angle}deg, {palette['header_bg']} 0%, {palette['accent']} 100%);padding:{pad_y+8}px {pad_x}px {pad_y}px;border-radius:{br} {br} 0 0;text-align:center;">
    <span class="mexo-badge" style="background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);">{badge}</span>
  </div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
  <div style="padding:{pad_y}px {pad_x}px;background:linear-gradient(to bottom, {palette['bg']}, {palette['card_bg']});">
    {content}
    <span class="mexo-cta">{cta_text}</span>
  </div>
</div>"""

    elif layout == "vintage":
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_x//2}px;">
  <div style="border:3px double {palette['accent']};padding:{pad_y}px;background:{palette['card_bg']};border-radius:{br};">
    <div style="text-align:center;margin-bottom:{pad_y-8}px;">
      <span class="mexo-badge">{badge}</span>
      <div class="mexo-divider"></div>
    </div>
    <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="margin-bottom:{pad_y-8}px;" />
    {content}
    <div class="mexo-divider"></div>
    <div style="text-align:center;margin-top:{pad_y-8}px;">
      <span class="mexo-cta">{cta_text}</span>
    </div>
  </div>
</div>"""

    elif layout == "centered":
        html = f"""{base_css}
<div class="mexo-page" style="text-align:center;padding:{pad_y+8}px {pad_x}px;">
  <span class="mexo-badge">{badge}</span>
  <div class="mexo-divider"></div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="margin-bottom:{pad_y}px;" />
  <div style="max-width:{max_w - 120}px;margin:0 auto;text-align:left;">
    {content}
  </div>
  <div class="mexo-divider"></div>
  <span class="mexo-cta">{cta_text}</span>
</div>"""

    elif layout == "fullwidth":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;max-width:100%;">
  <div style="position:relative;">
    <img src="{img_url}" alt="{img_alt}" style="width:100%;height:{img_h}px;object-fit:cover;display:block;" />
    <div style="position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent,rgba(0,0,0,0.65));padding:{pad_y}px {pad_x}px {pad_y-8}px;">
      <span class="mexo-badge">{badge}</span>
    </div>
  </div>
  <div style="max-width:{max_w}px;margin:0 auto;padding:{pad_y}px {pad_x}px;">
    {content}
    <span class="mexo-cta">{cta_text}</span>
  </div>
</div>"""

    elif layout == "stacked":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;">
  <div style="background:{palette['header_bg']};padding:{pad_y}px {pad_x}px;border-radius:{br} {br} 0 0;text-align:center;">
    <span class="mexo-badge">{badge}</span>
  </div>
  <div style="padding:{pad_y}px {pad_x}px;background:{palette['bg']};">
    {extras_top}{inner_html}
  </div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
  <div style="padding:{pad_y}px {pad_x}px;background:{palette['card_bg']};">
    {extras_bot}
    <span class="mexo-cta">{cta_text}</span>
  </div>
  <img class="mexo-img-main" src="{img_url2}" alt="{img_alt}" style="height:{img_h2}px;border-radius:0;" />
  <div style="background:{palette['header_bg']};padding:18px {pad_x}px;text-align:center;">
    <span style="color:{palette['header_text']};opacity:0.55;font-size:0.84em;">{footer_text}</span>
  </div>
</div>"""

    elif layout == "newspaper":
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_y}px {pad_x}px;">
  <div style="border-bottom:3px solid {palette['accent']};padding-bottom:{pad_y-16}px;margin-bottom:{pad_y-8}px;display:flex;justify-content:space-between;align-items:center;">
    <span class="mexo-badge">{badge}</span>
    <span style="font-family:{fonts['body']};font-size:0.82em;color:{palette['text']};opacity:0.6;">{footer_text}</span>
  </div>
  <div style="display:grid;grid-template-columns:{col_ratio};gap:{pad_x}px;">
    <div>
      <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="margin-bottom:{pad_y-8}px;" />
      {content}
      <span class="mexo-cta">{cta_text}</span>
    </div>
    <aside>
      <img class="mexo-img-side" src="{img_url2}" alt="{img_alt}" />
      <div style="background:{palette['card_bg']};border:1px solid {palette['border']};border-radius:{br};padding:16px;margin-top:{pad_y-16}px;">
        {make_highlight()}
      </div>
    </aside>
  </div>
</div>"""

    elif layout == "dark_card":
        html = f"""{base_css}
<div class="mexo-page" style="background:{palette['header_bg']};padding:{pad_y}px {pad_x}px;">
  <div style="background:{palette['card_bg']};border-radius:{br};box-shadow:{shadow};overflow:hidden;">
    <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="border-radius:0;" />
    <div style="padding:{pad_y}px {pad_x}px;">
      <span class="mexo-badge">{badge}</span>
      <div class="mexo-divider"></div>
      {content}
      <span class="mexo-cta">{cta_text}</span>
    </div>
  </div>
  <div style="text-align:center;padding:{pad_y-8}px 0 0;">
    <span style="color:{palette['header_text']};opacity:0.45;font-size:0.82em;font-family:{fonts['body']};">{footer_text}</span>
  </div>
</div>"""

    elif layout == "mosaic":
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_x//2}px;">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{pad_x//2}px;margin-bottom:{pad_x//2}px;">
    <div style="background:{palette['header_bg']};border-radius:{br};padding:{pad_y}px {pad_x-8}px;display:flex;align-items:center;justify-content:center;">
      <span class="mexo-badge" style="margin-bottom:0;">{badge}</span>
    </div>
    <img src="{img_url}" alt="{img_alt}" style="width:100%;height:{img_h}px;object-fit:cover;border-radius:{br};display:block;" />
  </div>
  <div style="background:{palette['card_bg']};border-radius:{br};padding:{pad_y}px {pad_x}px;box-shadow:{shadow};margin-bottom:{pad_x//2}px;">
    {content}
    <span class="mexo-cta">{cta_text}</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{pad_x//2}px;">
    <img src="{img_url2}" alt="{img_alt}" style="width:100%;height:{img_h2}px;object-fit:cover;border-radius:{br};display:block;" />
    <div style="background:{palette['accent']};border-radius:{br};padding:{pad_y}px {pad_x-8}px;display:flex;align-items:center;justify-content:center;">
      <span style="color:{palette['btn_text']};font-family:{fonts['heading']};font-size:1.1em;text-align:center;">{footer_text}</span>
    </div>
  </div>
</div>"""

    elif layout == "banner":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;">
  <div style="position:relative;overflow:hidden;border-radius:{br} {br} 0 0;">
    <img src="{img_url}" alt="{img_alt}" style="width:100%;height:{img_h+60}px;object-fit:cover;display:block;filter:brightness(0.75);" />
    <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:{pad_x}px;">
      <span class="mexo-badge" style="background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.5);margin-bottom:16px;">{badge}</span>
      <div style="color:#ffffff;font-family:{fonts['heading']};font-size:{typo['h1']};font-weight:bold;text-shadow:0 2px 12px rgba(0,0,0,0.5);max-width:600px;">{footer_text}</div>
    </div>
  </div>
  <div style="padding:{pad_y}px {pad_x}px;background:{palette['card_bg']};">
    <div class="mexo-divider"></div>
    {content}
    <span class="mexo-cta">{cta_text}</span>
  </div>
</div>"""

    elif layout == "editorial":
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_y}px {pad_x}px;">
  <div style="border-left:5px solid {palette['accent']};padding-left:{pad_x}px;margin-bottom:{pad_y}px;">
    <span class="mexo-badge">{badge}</span>
    <div style="font-family:{fonts['heading']};font-size:{typo['h1']};color:{palette['accent']};font-weight:bold;margin-top:8px;">{footer_text}</div>
  </div>
  <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="margin-bottom:{pad_y}px;" />
  <div class="mexo-divider"></div>
  {content}
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:{pad_x}px;margin-top:{pad_y}px;align-items:center;">
    <img src="{img_url2}" alt="{img_alt}" style="width:100%;height:{img_h2}px;object-fit:cover;border-radius:{br};display:block;" />
    <div>
      <span class="mexo-cta">{cta_text}</span>
    </div>
  </div>
</div>"""

    elif layout == "asymmetric":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;">
  <div style="display:grid;grid-template-columns:3fr 2fr;min-height:400px;">
    <div style="background:{palette['header_bg']};padding:{pad_y+8}px {pad_x}px;display:flex;flex-direction:column;justify-content:center;">
      <span class="mexo-badge">{badge}</span>
      <div style="color:{palette['header_text']};font-family:{fonts['heading']};font-size:{typo['h1']};font-weight:bold;margin:{pad_y-8}px 0;">{footer_text}</div>
      <span class="mexo-cta" style="align-self:flex-start;">{cta_text}</span>
    </div>
    <img src="{img_url}" alt="{img_alt}" style="width:100%;height:100%;object-fit:cover;display:block;" />
  </div>
  <div style="padding:{pad_y}px {pad_x}px;background:{palette['card_bg']};">
    <div class="mexo-divider"></div>
    {content}
  </div>
</div>"""

    elif layout == "sidebar_left":
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_y}px {pad_x}px;">
  <div style="display:grid;grid-template-columns:220px 1fr;gap:{pad_x+8}px;align-items:start;">
    <aside style="background:{palette['card_bg']};border:1px solid {palette['border']};border-radius:{br};padding:{pad_y-8}px {pad_x-8}px;box-shadow:{shadow};">
      <span class="mexo-badge" style="display:block;text-align:center;margin-bottom:{pad_y-8}px;">{badge}</span>
      <img src="{img_url2}" alt="{img_alt}" style="width:100%;height:{img_h2}px;object-fit:cover;border-radius:{br};display:block;margin-bottom:{pad_y-8}px;" />
      <div class="mexo-divider"></div>
      <span class="mexo-cta" style="display:block;text-align:center;">{cta_text}</span>
    </aside>
    <main>
      <img class="mexo-img-main" src="{img_url}" alt="{img_alt}" style="margin-bottom:{pad_y-8}px;" />
      {content}
    </main>
  </div>
</div>"""

    elif layout == "overlay":
        html = f"""{base_css}
<div class="mexo-page" style="padding:0;">
  <div style="position:relative;overflow:hidden;">
    <img src="{img_url}" alt="{img_alt}" style="width:100%;height:{img_h+80}px;object-fit:cover;display:block;" />
    <div style="position:absolute;bottom:0;left:0;right:0;background:linear-gradient(transparent 0%, {palette['header_bg']}ee 70%);padding:{pad_y+16}px {pad_x}px {pad_y}px;">
      <span class="mexo-badge" style="background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.4);">{badge}</span>
    </div>
  </div>
  <div style="background:{palette['header_bg']};padding:{pad_y}px {pad_x}px;">
    <div style="background:{palette['card_bg']};border-radius:{br};padding:{pad_y}px {pad_x}px;box-shadow:{shadow};">
      <div class="mexo-divider"></div>
      {content}
      <span class="mexo-cta">{cta_text}</span>
    </div>
  </div>
  <div style="background:{palette['header_bg']};padding:16px {pad_x}px;text-align:center;">
    <span style="color:{palette['header_text']};opacity:0.5;font-size:0.82em;font-family:{fonts['body']};">{footer_text}</span>
  </div>
</div>"""

    else:  # portfolio
        img_url3, _ = pick_image_url(400, 300)
        html = f"""{base_css}
<div class="mexo-page" style="padding:{pad_y}px {pad_x}px;">
  <div style="text-align:center;margin-bottom:{pad_y}px;">
    <span class="mexo-badge">{badge}</span>
    <div class="mexo-divider"></div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:{pad_x//2}px;margin-bottom:{pad_y}px;">
    <img src="{img_url}" alt="{img_alt}" style="width:100%;height:{img_h2}px;object-fit:cover;border-radius:{br};display:block;" />
    <img src="{img_url2}" alt="{img_alt}" style="width:100%;height:{img_h2}px;object-fit:cover;border-radius:{br};display:block;margin-top:{pad_x}px;" />
    <img src="{img_url3}" alt="{img_alt}" style="width:100%;height:{img_h2}px;object-fit:cover;border-radius:{br};display:block;" />
  </div>
  <div style="background:{palette['card_bg']};border:1px solid {palette['border']};border-radius:{br};padding:{pad_y}px {pad_x}px;box-shadow:{shadow};">
    {content}
    <span class="mexo-cta">{cta_text}</span>
  </div>
</div>"""

    return html.replace("mexo-", f"{px}-")

def generate_page_content(slug):
    topic = random.choice(PAGE_TOPICS)
    style = random.choice(PAGE_STYLES)

    if not openai_client:
        inner = (
            f"<h1>{topic.title()}</h1>"
            f"<p>Discover everything you need to know about {topic}. "
            f"Our comprehensive guide covers the essentials to get you started.</p>"
            f"<p>Whether you're a complete beginner or looking to refresh your knowledge, "
            f"this page has something for everyone.</p>"
        )
        return build_styled_page(inner, slug)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": (
                    f"Write a short, engaging {style} about '{topic}'. "
                    "This is for a lifestyle/wellness website. Make it feel authentic and "
                    "interesting — like a real blog or magazine page. Include a creative heading, "
                    "2-3 paragraphs of genuine helpful content, and optionally a short bullet list. "
                    "Keep it under 220 words. Output ONLY the inner HTML body content "
                    "(no <html>/<head>/<body>/<style> tags). "
                    "Use <h1>, <h2>, <p>, and optionally <ul>/<li> tags only. "
                    "Do NOT include any CSS, inline styles, classes, or attributes. "
                    "Do NOT mention any brand names, prices, or shopping. "
                    "Keep it wholesome and family-friendly."
                )
            }],
            max_tokens=500
        )
        if response and response.choices:
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = re.sub(r'^```(?:html)?\n?', '', content)
                content = re.sub(r'\n?```$', '', content)
            return build_styled_page(content, slug)
    except Exception as e:
        print(f"❌ Error generating page content: {e}")

    inner = (
        f"<h1>{topic.title()}</h1>"
        f"<p>Explore our guide to {topic}. We've gathered the best tips and insights "
        f"to help you on your journey.</p>"
        f"<p>From beginners to enthusiasts, there's something here for everyone. "
        f"Start exploring today!</p>"
    )
    return build_styled_page(inner, slug)

def create_shopify_page(slug):
    if not SHOPIFY_ACCESS_TOKEN:
        print(f"⚠️ SHOPIFY_ACCESS_TOKEN not set - skipping page creation for '{slug}'")
        return False
    
    try:
        check_url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/pages.json?handle={slug}"
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }
        check_resp = requests.get(check_url, headers=headers)
        if check_resp.status_code == 200:
            pages = check_resp.json().get("pages", [])
            if any(p.get("handle") == slug for p in pages):
                print(f"✅ Page '{slug}' already exists on Shopify")
                CREATED_PAGES_CACHE.add(slug)
                save_created_pages()
                return True
    except Exception as e:
        print(f"⚠️ Error checking page existence: {e}")
    
    topic = random.choice(PAGE_TOPICS)
    body_html = generate_page_content(slug)
    title_template = random.choice(PAGE_TITLE_TEMPLATES)
    page_title = title_template.format(topic=topic.title())
    
    create_url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/pages.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    data = {
        "page": {
            "title": page_title,
            "handle": slug,
            "body_html": body_html,
            "published": True
        }
    }
    
    try:
        resp = requests.post(create_url, json=data, headers=headers)
        if resp.status_code == 201:
            print(f"✅ Created Shopify page: /pages/{slug}")
            CREATED_PAGES_CACHE.add(slug)
            save_created_pages()
            return True
        else:
            print(f"❌ Failed to create page '{slug}': {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Error creating Shopify page: {e}")
        return False

def set_slug_config(slug, offer, source=None):
    """Set per-slug offer/source config on the Worker."""
    try:
        r = requests.post(
            f"{WORKER_URL}/api/config",
            headers={
                "Authorization": f"Bearer {UPLOAD_SECRET}",
                "Content-Type": "application/json",
            },
            json={"slug": slug, "offer": offer, "source": source},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[setlink failed] {slug}: {e}")
        return None

def get_slug_config(slug):
    """Read per-slug config from the Worker."""
    try:
        r = requests.get(
            f"{WORKER_URL}/api/config/{slug}",
            headers={"Authorization": f"Bearer {UPLOAD_SECRET}"},
            timeout=10,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[getlink failed] {slug}: {e}")
        return None

def clear_slug_config(slug):
    """Remove per-slug config from the Worker."""
    try:
        r = requests.delete(
            f"{WORKER_URL}/api/config/{slug}",
            headers={"Authorization": f"Bearer {UPLOAD_SECRET}"},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[clearlink failed] {slug}: {e}")
        return False

def set_bypass(slug):
    """Disable cloaking for a slug — all visitors get redirected."""
    try:
        r = requests.post(
            f"{WORKER_URL}/api/bypass",
            headers={
                "Authorization": f"Bearer {UPLOAD_SECRET}",
                "Content-Type": "application/json",
            },
            json={"slug": slug},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[bypass failed] {slug}: {e}")
        return False

def remove_bypass(slug):
    """Re-enable cloaking for a slug."""
    try:
        r = requests.delete(
            f"{WORKER_URL}/api/bypass/{slug}",
            headers={"Authorization": f"Bearer {UPLOAD_SECRET}"},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"[unbypass failed] {slug}: {e}")
        return False

def register_split(s, buckets):
    """Register a split: fan subid s out to N equal-weighted buckets."""
    try:
        r = requests.post(
            f"{WORKER_URL}/api/split",
            headers={
                "Authorization": f"Bearer {UPLOAD_SECRET}",
                "Content-Type": "application/json",
            },
            json={"s": s, "buckets": buckets},
            timeout=10,
        )
        if not r.ok:
            try:
                err = r.json().get("error", r.text)
            except Exception:
                err = r.text
            return None, err
        return r.json(), None
    except Exception as e:
        print(f"[split failed] {s}: {e}")
        return None, str(e)

def delete_split(s):
    """Remove a split registration for subid s."""
    try:
        r = requests.delete(
            f"{WORKER_URL}/api/split/{s}",
            headers={"Authorization": f"Bearer {UPLOAD_SECRET}"},
            timeout=10,
        )
        if not r.ok:
            try:
                err = r.json().get("error", r.text)
            except Exception:
                err = r.text
            return False, err
        return True, None
    except Exception as e:
        print(f"[splitdel failed] {s}: {e}")
        return False, str(e)

def create_cloak_page(slug):
    """Generate page HTML via existing generate_page_content() and
    upload to Cloudflare Worker KV. Returns (url, error_str) tuple."""
    html = generate_page_content(slug)
    if not html:
        return None, "generate_page_content returned empty"
    try:
        from curl_cffi import requests as cf_requests
        import json as _json
        r = cf_requests.post(
            f"{WORKER_URL}/api/pages",
            headers={
                "Authorization": f"Bearer {UPLOAD_SECRET}",
                "Content-Type": "application/json",
            },
            data=_json.dumps({"slug": slug, "html": html}),
            timeout=30,
            impersonate="chrome110",
        )
        status = r.status_code
        body = r.text[:300]
        if status >= 400:
            return None, f"HTTP {status}: {body}"
        data = r.json()
        url = data.get("url") or f"{WORKER_URL}/{slug}"
        return url, None
    except Exception as e:
        return None, str(e)

# Valid offer codes (33 total, alphabetical) — keep in sync with the cloaker's
# OFFERS table in geofiltering/index.js. Includes the tsla* campaign family
# and aryanfc/oil/onlyfans/gravypass/pcp.
ALLOWED_OFFERS = [
    "amazon", "apple", "aritzia", "aryanfc", "auto", "bizzop", "cash",
    "coinbase", "cpi", "doordash", "freecash", "gravypass", "oil",
    "onlyfans", "pcp", "playful", "plt", "sephora", "shein", "starbucks", "swagbucks",
    "testerup", "teststar", "tslaapple", "tslafc", "tslamabfc", "tslashein",
    "tslatapfc", "tslatp", "ttshop", "venmo", "wellsfargo", "zara", "zelle"
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions(users=True))

# Message deduplication to prevent double responses
COOLDOWN_SECONDS = 60.0  # Prevent processing same message within 60 seconds
INSTANCE_ID = f"bot_{random.randint(1000, 9999)}"
DEDUP_FILE = f"message_dedup_{INSTANCE_ID}.json"  # Use instance-specific dedup file

# Check if this is a deployment vs development environment
IS_DEPLOYMENT = os.environ.get("REPLIT_DEPLOYMENT") == "1"
print(f"🔧 Starting bot - Deployment: {IS_DEPLOYMENT}, Instance: {INSTANCE_ID}")

def load_processed_messages():
    """Load processed messages from file"""
    try:
        if os.path.exists(DEDUP_FILE):
            with open(DEDUP_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_processed_messages(processed_messages):
    """Save processed messages to file"""
    try:
        with open(DEDUP_FILE, 'w') as f:
            json.dump(processed_messages, f)
    except:
        pass

def cleanup_old_messages(processed_messages):
    """Remove old processed messages to prevent memory buildup"""
    current_time = time.time()
    to_remove = []
    for msg_id, timestamp in processed_messages.items():
        if current_time - timestamp > COOLDOWN_SECONDS:
            to_remove.append(msg_id)
    
    if to_remove:
        print(f"🔧 Debug [{INSTANCE_ID}] - Cleaning up {len(to_remove)} old messages")
        for msg_id in to_remove:
            del processed_messages[msg_id]

# ~280 evocative adjectives across color, nature, texture, emotion, abstraction
_NAME_ADJ = [
    # Color / shade (60)
    "Amber", "Ashen", "Azure", "Bone", "Bronze", "Burgundy", "Cerise", "Cerulean",
    "Champagne", "Charcoal", "Chartreuse", "Cobalt", "Copper", "Coral", "Cream",
    "Crimson", "Ecru", "Ember", "Fawn", "Flaxen", "Frost", "Fuchsia", "Gilded",
    "Golden", "Indigo", "Ivory", "Jade", "Khaki", "Lavender", "Lilac", "Lime",
    "Magenta", "Maroon", "Mauve", "Mint", "Mulberry", "Navy", "Obsidian", "Ochre",
    "Olive", "Onyx", "Peach", "Pearl", "Periwinkle", "Pewter", "Russet", "Sable",
    "Sage", "Salmon", "Scarlet", "Sienna", "Silver", "Slate", "Tan", "Taupe",
    "Teal", "Turquoise", "Umber", "Vermillion", "Violet", "Viridian",
    # Nature / weather (55)
    "Abyssal", "Alpine", "Arctic", "Arid", "Astral", "Auroral", "Autumnal",
    "Boreal", "Briny", "Celestial", "Cinder", "Coastal", "Crepuscular",
    "Equinox", "Estuarine", "Fluvial", "Glacial", "Igneous", "Karst",
    "Lacustrine", "Lithic", "Lunar", "Magmatic", "Marine", "Monsoon",
    "Nebular", "Nocturnal", "Pelagic", "Petrified", "Polar", "Riparian",
    "Solar", "Solstice", "Stormy", "Subalpine", "Subterranean", "Sylvan",
    "Tempest", "Thermal", "Tidal", "Torrid", "Tundral", "Twilight",
    "Vernal", "Verdant", "Volcanic", "Windward", "Zenith",
    "Boiling", "Frozen", "Sunken", "Risen", "Hollow", "Dusk",
    # Texture / intensity (55)
    "Adamant", "Aged", "Austere", "Bare", "Barren", "Brazen", "Brittle",
    "Burnished", "Coarse", "Corroded", "Cracked", "Dense", "Etched",
    "Fibrous", "Forged", "Fractured", "Graven", "Gritty", "Hammered",
    "Hushed", "Iron", "Jagged", "Keen", "Knotted", "Lacquered", "Molten",
    "Muted", "Ossified", "Porous", "Raw", "Rugged", "Scored", "Serene",
    "Sharp", "Sheer", "Silent", "Sinewed", "Smooth", "Stark", "Still",
    "Tarnished", "Tempered", "Tensile", "Twisted", "Veined", "Vivid",
    "Weathered", "Wild", "Worn", "Woven", "Dense", "Hollow", "Lean", "Sheer",
    # Poetic / abstract (60)
    "Alchemic", "Ancient", "Arcane", "Archaic", "Astral", "Auric",
    "Binary", "Boundless", "Brazen", "Broken", "Brutal", "Cardinal",
    "Chromatic", "Cryptic", "Cursed", "Cyclic", "Dark", "Dire",
    "Doomed", "Dread", "Eldritch", "Elusive", "Endemic", "Endless",
    "Ephemeral", "Eternal", "Exiled", "Feral", "Fleeting", "Forsaken",
    "Hermetic", "Hollow", "Infinite", "Liminal", "Lost", "Mercurial",
    "Monastic", "Mystic", "Nomadic", "Ominous", "Oracular", "Paradox",
    "Pastoral", "Phantom", "Primal", "Primeval", "Rogue", "Sacred",
    "Savage", "Sealed", "Sovereign", "Stygian", "Sundered", "Tenebrous",
    "Umbral", "Untamed", "Veiled", "Venerable", "Void", "Woven",
    # Short punchy (50)
    "Bare", "Bleak", "Bold", "Bright", "Calm", "Cold", "Dead", "Deep",
    "Dim", "Dry", "Dull", "Eerie", "Faint", "Far", "Fine", "Flat",
    "Free", "Full", "Gone", "Gray", "Grim", "Hard", "Hazy", "High",
    "Low", "Mute", "New", "Old", "Open", "Pale", "Plain", "Pure",
    "Red", "Rich", "Rough", "Safe", "Slow", "Soft", "Sure", "Swift",
    "Tall", "Thin", "True", "Vast", "Warm", "Wide", "Wise", "Young",
    "Grim", "Blunt",
]

# ~280 evocative nouns across abstraction, nature, mythology, geography, creatures
_NAME_NOUN = [
    # Abstract / conceptual (90)
    "Abysm", "Accord", "Advent", "Aegis", "Arc", "Aura", "Axis",
    "Beacon", "Bloom", "Brink", "Cadence", "Cascade", "Chasm",
    "Chronicle", "Cipher", "Codex", "Conduit", "Confluence", "Contour",
    "Core", "Covenant", "Crest", "Crown", "Crucible", "Current",
    "Domain", "Drift", "Ebb", "Echo", "Edge", "Eddy", "Emblem",
    "Engine", "Epoch", "Expanse", "Facet", "Fathom", "Fissure",
    "Flare", "Flow", "Flux", "Forge", "Fracture", "Fulcrum",
    "Gale", "Gate", "Glyph", "Gradient", "Grid", "Grove",
    "Gulf", "Haven", "Haze", "Helix", "Horizon", "Husk",
    "Index", "Inferno", "Influx", "Interface", "Kernel", "Knot",
    "Labyrinth", "Lattice", "Layer", "Ledge", "Locus", "Loom",
    "Mantle", "Margin", "Matrix", "Meridian", "Mosaic", "Nexus",
    "Node", "Notch", "Orbit", "Origin", "Passage", "Pattern",
    "Pendulum", "Phase", "Pillar", "Pivot", "Portal", "Prism",
    "Pulse", "Pyre", "Radius", "Realm", "Refuge", "Remnant",
    # Abstract cont. (30)
    "Ridge", "Rift", "Root", "Rune", "Scale", "Scaffold", "Schema",
    "Seam", "Sector", "Sequence", "Shard", "Shore", "Signal",
    "Solace", "Span", "Spectrum", "Spine", "Spire", "Spiral",
    "Stratum", "Summit", "Surge", "Syntax", "Tether", "Thread",
    "Threshold", "Tide", "Tome", "Torrent", "Trace",
    # Abstract cont. (20)
    "Trail", "Trench", "Vector", "Vault", "Veil", "Vein", "Verge",
    "Vertex", "Vista", "Void", "Wake", "Watershed", "Wave",
    "Web", "Well", "Zone", "Arc", "Conduit", "Channel", "Current",
    # Creatures / animals (45)
    "Badger", "Beetle", "Bison", "Boar", "Cobra", "Condor",
    "Coyote", "Crane", "Crow", "Deer", "Drake", "Eagle",
    "Egret", "Elk", "Ermine", "Falcon", "Ferret", "Finch",
    "Fox", "Gannet", "Gecko", "Goshawk", "Grouse", "Harrier",
    "Hawk", "Heron", "Ibis", "Jackal", "Jaguar", "Kestrel",
    "Kingfisher", "Kite", "Lemur", "Leopard", "Lynx", "Marten",
    "Merlin", "Mink", "Mongoose", "Moose", "Nightjar", "Osprey",
    "Otter", "Panther", "Peregrine", "Python", "Raccoon", "Raptor",
    "Raven", "Salamander", "Scorpion", "Serval", "Shrike",
    "Sparrow", "Stag", "Stoat", "Swallow", "Tiger", "Viper",
    "Vole", "Vulture", "Wolf", "Wolverine", "Wren",
    # Mythological / ancient (40)
    "Aeon", "Altar", "Anvil", "Augur", "Brand", "Cairn",
    "Citadel", "Codex", "Crypt", "Crux", "Decree", "Dominion",
    "Effigy", "Elegy", "Epitaph", "Fable", "Harbinger", "Herald",
    "Icon", "Idol", "Lament", "Monolith", "Mythos", "Omen",
    "Oracle", "Pact", "Pantheon", "Prophecy", "Psalm", "Relic",
    "Requiem", "Rite", "Saga", "Sanctum", "Seal", "Shrine",
    "Sigil", "Specter", "Testament", "Throne", "Totem", "Valor",
    "Vigil", "Ward", "Wraith",
    # Landscape / geography (50)
    "Atoll", "Basin", "Bight", "Bluff", "Bog", "Brook",
    "Butte", "Canyon", "Cape", "Cavern", "Channel", "Cleft",
    "Combe", "Cove", "Crag", "Creek", "Delta", "Dune",
    "Escarpment", "Estuary", "Fen", "Fjord", "Ford", "Glen",
    "Gorge", "Gully", "Harbor", "Headland", "Heath", "Highland",
    "Inlet", "Isle", "Knoll", "Lagoon", "Loch", "Mesa",
    "Moor", "Moraine", "Narrows", "Pass", "Pinnacle",
    "Plateau", "Promontory", "Ravine", "Reef", "Scarp",
    "Scree", "Sound", "Steppe", "Strand", "Taiga",
    "Tarn", "Terrace", "Tor", "Vale", "Weald",
]

def generate_random_identity_name():
    """Generate a unique identity name using 7 structural patterns — ~93M combinations."""
    pattern = random.choices(
        ["adj_noun", "merged", "noun_noun", "noun_merged"],
        weights=[35, 25, 25, 15],
        k=1
    )[0]

    adj   = random.choice(_NAME_ADJ)
    noun  = random.choice(_NAME_NOUN)
    noun2 = random.choice(_NAME_NOUN)
    while noun2 == noun:
        noun2 = random.choice(_NAME_NOUN)

    if pattern == "adj_noun":
        return f"{adj} {noun}"
    elif pattern == "merged":
        return f"{adj}{noun}"
    elif pattern == "noun_noun":
        return f"{noun} {noun2}"
    elif pattern == "noun_merged":
        return f"{noun}{noun2}"
    else:
        return f"{adj} {noun}"

async def generate_random_identity_with_caption():
    """Generate a random identity name with AI-generated caption"""
    # Generate random product name
    random_name = generate_random_identity_name()
    
    # Varied fallback captions for different product types
    fallback_captions = [
        "Experience premium quality", "Your perfect everyday companion", "Designed for modern living",
        "Innovative technology meets style", "Crafted with precision", "Built to last forever",
        "Elevate your daily routine", "Where function meets beauty", "Professional grade performance",
        "Seamless integration guaranteed", "Unmatched durability tested", "Smart design solutions",
        "Enhanced performance delivered", "Trusted by professionals", "Revolutionary breakthrough technology",
        "Comfort redefined completely", "Efficiency at its finest", "Quality you can trust",
        "Advanced features included", "Superior craftsmanship evident", "Next generation innovation",
        "Reliable performance always", "Sleek modern aesthetics", "Engineered for perfection",
        "Maximum convenience provided", "Exceptional value offered", "Industry leading standards",
        "Breakthrough design excellence", "Optimized for daily use", "Premium materials used"
    ]
    
    if not openai_client:
        # Use varied fallback captions
        return random_name, random.choice(fallback_captions)
    
    try:
        # Generate caption using AI
        caption_styles = [
            "inspiring and uplifting", "mysterious and intriguing", "poetic and artistic",
            "adventurous and exciting", "peaceful and calming", "dramatic and intense",
            "whimsical and playful", "philosophical and deep", "energetic and vibrant",
            "mystical and ethereal", "bold and confident", "dreamy and surreal"
        ]
        selected_style = random.choice(caption_styles)
        
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        caption_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": f"Generate a short, {selected_style} product caption for '{random_name}'. Keep it 3-7 words, focus on the product's appeal and benefits. Make it catchy and engaging."
            }],
            max_tokens=50
        )
        
        if not caption_response or not caption_response.choices:
            return random_name, random.choice(fallback_captions)
            
        caption_content = caption_response.choices[0].message.content
        caption = caption_content.strip() if caption_content else random.choice(fallback_captions)
        
        return random_name, caption
        
    except Exception as e:
        print(f"❌ Error generating random caption: {e}")
        return random_name, random.choice(fallback_captions)

def generate_contextual_product_name(prompt):
    """Generate a product name that matches the image prompt"""
    prompt_lower = prompt.lower()
    
    # Define comprehensive product categories with their related adjectives and specific names
    product_mappings = {
        # Electronics & Tech
        'smartphone': ['Smart', 'Advanced', 'Pro', 'Ultra', 'Premium', 'Digital'],
        'phone': ['Smart', 'Advanced', 'Pro', 'Ultra', 'Premium', 'Digital'],
        'smartwatch': ['Smart', 'Digital', 'Pro', 'Advanced', 'Wireless', 'Premium'],
        'watch': ['Smart', 'Digital', 'Pro', 'Advanced', 'Wireless', 'Premium'],
        'headphones': ['Wireless', 'Premium', 'Pro', 'Advanced', 'Digital', 'Smart'],
        'speaker': ['Wireless', 'Smart', 'Premium', 'Pro', 'Portable', 'Digital'],
        'laptop': ['Pro', 'Ultra', 'Premium', 'Advanced', 'Portable', 'Smart'],
        'tablet': ['Pro', 'Ultra', 'Premium', 'Advanced', 'Portable', 'Smart'],
        'camera': ['Pro', 'Digital', 'Advanced', 'Premium', 'Professional', 'Smart'],
        'charger': ['Wireless', 'Fast', 'Quick', 'Premium', 'Portable', 'Smart'],
        'gaming': ['Pro', 'Elite', 'Premium', 'Advanced', 'Ultimate', 'Smart'],
        
        # Kitchen & Dining - Expanded
        'coffee': ['Premium', 'Pro', 'Advanced', 'Smart', 'Professional', 'Elite'],
        'blender': ['Pro', 'Premium', 'Smart', 'Advanced', 'Professional', 'Ultra'],
        'knife': ['Pro', 'Premium', 'Sharp', 'Professional', 'Ultra', 'Advanced'],
        'cookware': ['Pro', 'Premium', 'Professional', 'Advanced', 'Elite', 'Ultra'],
        'kitchen': ['Modern', 'Premium', 'Professional', 'Designer', 'Stylish', 'Elite'],
        'utensils': ['Premium', 'Professional', 'Stainless', 'Designer', 'Modern', 'Elite'],
        'tableware': ['Premium', 'Designer', 'Elegant', 'Modern', 'Professional', 'Luxury'],
        'bowl': ['Designer', 'Premium', 'Ceramic', 'Modern', 'Elegant', 'Artisan'],
        'plate': ['Designer', 'Premium', 'Ceramic', 'Modern', 'Elegant', 'Fine'],
        'cup': ['Premium', 'Designer', 'Ceramic', 'Modern', 'Elegant', 'Travel'],
        'mug': ['Premium', 'Designer', 'Ceramic', 'Modern', 'Insulated', 'Travel'],
        'bottle': ['Premium', 'Insulated', 'Stainless', 'Smart', 'Travel', 'Sports'],
        
        # Furniture & Home - Significantly Expanded
        'chair': ['Modern', 'Designer', 'Ergonomic', 'Premium', 'Luxury', 'Comfort'],
        'furniture': ['Modern', 'Designer', 'Premium', 'Luxury', 'Contemporary', 'Elegant'],
        'table': ['Modern', 'Designer', 'Premium', 'Elegant', 'Contemporary', 'Luxury'],
        'desk': ['Modern', 'Executive', 'Premium', 'Professional', 'Designer', 'Smart'],
        'shelf': ['Modern', 'Designer', 'Premium', 'Floating', 'Contemporary', 'Minimalist'],
        'cabinet': ['Modern', 'Designer', 'Premium', 'Storage', 'Contemporary', 'Luxury'],
        'storage': ['Modern', 'Designer', 'Premium', 'Smart', 'Organizational', 'Stylish'],
        'organizer': ['Premium', 'Smart', 'Designer', 'Modern', 'Functional', 'Elegant'],
        'container': ['Premium', 'Smart', 'Modern', 'Designer', 'Airtight', 'Glass'],
        'box': ['Premium', 'Designer', 'Storage', 'Modern', 'Elegant', 'Luxury'],
        'basket': ['Premium', 'Woven', 'Designer', 'Natural', 'Modern', 'Stylish'],
        
        # Home & Living - Expanded
        'lamp': ['Modern', 'Designer', 'Premium', 'Stylish', 'Contemporary', 'Elite'],
        'light': ['Modern', 'Designer', 'Smart', 'LED', 'Contemporary', 'Premium'],
        'lighting': ['Modern', 'Designer', 'Smart', 'LED', 'Contemporary', 'Premium'],
        'candle': ['Premium', 'Luxury', 'Aromatic', 'Designer', 'Elegant', 'Natural'],
        'pillow': ['Premium', 'Luxury', 'Comfort', 'Designer', 'Soft', 'Elegant'],
        'vase': ['Designer', 'Premium', 'Elegant', 'Artistic', 'Modern', 'Luxury'],
        'mirror': ['Designer', 'Premium', 'Modern', 'Elegant', 'Luxury', 'Decorative'],
        'clock': ['Modern', 'Designer', 'Smart', 'Digital', 'Elegant', 'Premium'],
        'frame': ['Designer', 'Premium', 'Modern', 'Elegant', 'Photo', 'Art'],
        'decor': ['Designer', 'Premium', 'Modern', 'Elegant', 'Artistic', 'Luxury'],
        'textile': ['Premium', 'Luxury', 'Designer', 'Soft', 'Natural', 'Elegant'],
        'bedding': ['Premium', 'Luxury', 'Comfort', 'Designer', 'Soft', 'Hotel'],
        
        # Fashion & Accessories
        'bag': ['Premium', 'Luxury', 'Designer', 'Stylish', 'Elite', 'Modern'],
        'wallet': ['Premium', 'Luxury', 'Leather', 'Classic', 'Elite', 'Designer'],
        'sunglasses': ['Premium', 'Designer', 'Stylish', 'Classic', 'Luxury', 'Pro'],
        'shoes': ['Premium', 'Designer', 'Stylish', 'Professional', 'Luxury', 'Elite'],
        'jewelry': ['Premium', 'Luxury', 'Designer', 'Elegant', 'Classic', 'Elite'],
        
        # Tools & Hardware
        'tool': ['Professional', 'Pro', 'Heavy-Duty', 'Premium', 'Industrial', 'Advanced'],
        'drill': ['Professional', 'Pro', 'Heavy-Duty', 'Premium', 'Industrial', 'Cordless'],
        'hammer': ['Professional', 'Pro', 'Heavy-Duty', 'Premium', 'Industrial', 'Steel'],
        
        # Sports & Fitness
        'yoga': ['Premium', 'Pro', 'Professional', 'Eco-Friendly', 'Advanced', 'Ultra'],
        'fitness': ['Pro', 'Premium', 'Professional', 'Advanced', 'Elite', 'Smart'],
        'gym': ['Pro', 'Premium', 'Professional', 'Advanced', 'Elite', 'Heavy-Duty'],
        
        # Beauty & Personal Care
        'beauty': ['Premium', 'Luxury', 'Professional', 'Advanced', 'Elite', 'Organic'],
        'skincare': ['Premium', 'Luxury', 'Professional', 'Advanced', 'Natural', 'Organic'],
        'makeup': ['Premium', 'Professional', 'Luxury', 'Advanced', 'Designer', 'Pro']
    }
    
    # Extract main product type from prompt
    detected_product = None
    detected_adjectives = []
    
    # Check for specific products in the prompt
    for product_key, adjectives in product_mappings.items():
        if product_key in prompt_lower:
            detected_product = product_key
            detected_adjectives = adjectives
            break
    
    # If no specific product found, try to identify by category with expanded detection
    if not detected_product:
        if any(word in prompt_lower for word in ['electronics', 'gadgets', 'tech', 'digital', 'smart', 'wireless', 'bluetooth']):
            detected_product = random.choice(['smartphone', 'smartwatch', 'headphones', 'speaker', 'tablet', 'camera', 'charger'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['kitchen', 'cooking', 'food', 'dining', 'tableware', 'utensils', 'culinary']):
            detected_product = random.choice(['coffee', 'blender', 'cookware', 'kitchen', 'utensils', 'tableware', 'bowl', 'plate', 'cup', 'mug', 'bottle'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['furniture', 'seating', 'chair', 'table', 'desk', 'shelf', 'cabinet', 'storage']):
            detected_product = random.choice(['chair', 'furniture', 'table', 'desk', 'shelf', 'cabinet', 'storage', 'organizer'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['home', 'living', 'decor', 'interior', 'decorative', 'lighting', 'textile']):
            detected_product = random.choice(['lamp', 'candle', 'pillow', 'vase', 'mirror', 'clock', 'frame', 'decor', 'light', 'textile', 'bedding'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['fashion', 'clothing', 'accessories', 'wearable', 'jewelry']):
            detected_product = random.choice(['bag', 'wallet', 'sunglasses', 'shoes', 'jewelry'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['tool', 'hardware', 'work', 'industrial', 'professional']):
            detected_product = random.choice(['tool', 'drill', 'hammer'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['fitness', 'sports', 'gym', 'yoga', 'exercise', 'workout']):
            detected_product = random.choice(['yoga', 'fitness', 'gym'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['beauty', 'skincare', 'makeup', 'cosmetic', 'personal care']):
            detected_product = random.choice(['beauty', 'skincare', 'makeup'])
            detected_adjectives = product_mappings[detected_product]
        elif any(word in prompt_lower for word in ['container', 'box', 'basket', 'organizer', 'organization']):
            detected_product = random.choice(['container', 'box', 'basket', 'organizer', 'storage'])
            detected_adjectives = product_mappings[detected_product]
    
    # Generate name based on detected product
    if detected_product and detected_adjectives:
        adjective = random.choice(detected_adjectives)
        
        # Create appropriate noun based on product type - Significantly Expanded
        if detected_product in ['smartphone', 'phone']:
            noun = random.choice(['Phone', 'Smartphone', 'Device'])
        elif detected_product in ['smartwatch', 'watch']:
            noun = random.choice(['Watch', 'Smartwatch', 'Timepiece'])
        elif detected_product == 'headphones':
            noun = random.choice(['Headphones', 'Earbuds', 'Audio'])
        elif detected_product == 'speaker':
            noun = random.choice(['Speaker', 'Audio', 'Sound'])
        elif detected_product == 'laptop':
            noun = random.choice(['Laptop', 'Computer', 'Notebook'])
        elif detected_product == 'tablet':
            noun = random.choice(['Tablet', 'Pad', 'Device'])
        elif detected_product == 'camera':
            noun = random.choice(['Camera', 'Lens', 'Photo'])
        elif detected_product == 'charger':
            noun = random.choice(['Charger', 'Power', 'Battery'])
        elif detected_product == 'coffee':
            noun = random.choice(['Coffee', 'Brew', 'Espresso'])
        elif detected_product == 'blender':
            noun = random.choice(['Blender', 'Mixer', 'Smoothie'])
        elif detected_product == 'knife':
            noun = random.choice(['Knife', 'Blade', 'Cutter'])
        elif detected_product == 'cookware':
            noun = random.choice(['Cookware', 'Pan', 'Pot'])
        elif detected_product == 'kitchen':
            noun = random.choice(['Kitchen', 'Appliance', 'Set'])
        elif detected_product == 'utensils':
            noun = random.choice(['Utensils', 'Set', 'Collection'])
        elif detected_product == 'tableware':
            noun = random.choice(['Tableware', 'Dinnerware', 'Set'])
        elif detected_product == 'bowl':
            noun = random.choice(['Bowl', 'Dish', 'Basin'])
        elif detected_product == 'plate':
            noun = random.choice(['Plate', 'Dish', 'Platter'])
        elif detected_product == 'cup':
            noun = random.choice(['Cup', 'Mug', 'Tumbler'])
        elif detected_product == 'mug':
            noun = random.choice(['Mug', 'Cup', 'Tumbler'])
        elif detected_product == 'bottle':
            noun = random.choice(['Bottle', 'Flask', 'Container'])
        elif detected_product == 'chair':
            noun = random.choice(['Chair', 'Seat', 'Seating'])
        elif detected_product == 'furniture':
            noun = random.choice(['Furniture', 'Piece', 'Set'])
        elif detected_product == 'table':
            noun = random.choice(['Table', 'Desk', 'Surface'])
        elif detected_product == 'desk':
            noun = random.choice(['Desk', 'Table', 'Workstation'])
        elif detected_product == 'shelf':
            noun = random.choice(['Shelf', 'Shelving', 'Unit'])
        elif detected_product == 'cabinet':
            noun = random.choice(['Cabinet', 'Storage', 'Unit'])
        elif detected_product == 'storage':
            noun = random.choice(['Storage', 'Solution', 'System'])
        elif detected_product == 'organizer':
            noun = random.choice(['Organizer', 'Storage', 'System'])
        elif detected_product == 'container':
            noun = random.choice(['Container', 'Storage', 'Box'])
        elif detected_product == 'box':
            noun = random.choice(['Box', 'Container', 'Storage'])
        elif detected_product == 'basket':
            noun = random.choice(['Basket', 'Container', 'Storage'])
        elif detected_product == 'bag':
            noun = random.choice(['Bag', 'Handbag', 'Tote'])
        elif detected_product == 'wallet':
            noun = random.choice(['Wallet', 'Purse', 'Billfold'])
        elif detected_product == 'sunglasses':
            noun = random.choice(['Sunglasses', 'Shades', 'Eyewear'])
        elif detected_product == 'shoes':
            noun = random.choice(['Shoes', 'Sneakers', 'Footwear'])
        elif detected_product == 'jewelry':
            noun = random.choice(['Jewelry', 'Accessory', 'Piece'])
        elif detected_product == 'lamp':
            noun = random.choice(['Lamp', 'Light', 'Fixture'])
        elif detected_product in ['light', 'lighting']:
            noun = random.choice(['Light', 'Lighting', 'Fixture'])
        elif detected_product == 'candle':
            noun = random.choice(['Candle', 'Scent', 'Fragrance'])
        elif detected_product == 'pillow':
            noun = random.choice(['Pillow', 'Cushion', 'Throw'])
        elif detected_product == 'vase':
            noun = random.choice(['Vase', 'Vessel', 'Decor'])
        elif detected_product == 'mirror':
            noun = random.choice(['Mirror', 'Glass', 'Reflector'])
        elif detected_product == 'clock':
            noun = random.choice(['Clock', 'Timer', 'Timepiece'])
        elif detected_product == 'frame':
            noun = random.choice(['Frame', 'Display', 'Holder'])
        elif detected_product == 'decor':
            noun = random.choice(['Decor', 'Decoration', 'Accent'])
        elif detected_product == 'textile':
            noun = random.choice(['Textile', 'Fabric', 'Material'])
        elif detected_product == 'bedding':
            noun = random.choice(['Bedding', 'Linen', 'Set'])
        elif detected_product in ['tool', 'drill', 'hammer']:
            noun = random.choice(['Tool', 'Equipment', 'Gear'])
        elif detected_product in ['yoga', 'fitness', 'gym']:
            noun = random.choice(['Gear', 'Equipment', 'Accessory'])
        elif detected_product in ['beauty', 'skincare', 'makeup']:
            noun = random.choice(['Beauty', 'Care', 'Essential'])
        else:
            noun = random.choice(NOUNS)  # Fallback to random noun
        
        return f"{adjective} {noun}"
    
    # Fallback to completely random name if no context found
    return generate_random_identity_name()



# Business-focused prompt categories for professional image generation
PROMPT_THEMES = [
    "business", "technology", "office", "startup", "corporate", "innovation", 
    "ecommerce", "marketing", "finance", "success", "teamwork", "leadership"
]

# Generate massive product prompt pool programmatically for maximum variety
def generate_product_prompts():
    """Generate 10,000+ product-focused prompts dynamically"""
    
    # Expanded product categories (50+ categories)
    product_categories = [
        "electronics", "gadgets", "accessories", "home goods", "kitchen items", "tools", "toys", "games",
        "fashion", "jewelry", "sports equipment", "outdoor gear", "beauty products", "health items",
        "office supplies", "art supplies", "books", "music items", "automotive", "pet supplies",
        "garden tools", "cleaning supplies", "storage solutions", "decorative items", "lighting",
        "furniture", "bedding", "textiles", "appliances", "cookware", "tableware", "glassware",
        "ceramics", "pottery", "sculptures", "paintings", "photographs", "crafts", "collectibles",
        "vintage items", "antiques", "modern art", "technology gadgets", "smart devices", "wearables",
        "fitness gear", "yoga equipment", "camping gear", "hiking accessories", "water sports",
        "winter sports", "board games", "card games", "puzzles", "educational toys", "baby products"
    ]
    
    # Expanded environments/settings (60+ environments)
    environments = [
        "modern studio", "minimalist background", "white backdrop", "wooden table", "marble surface",
        "glass display", "retail shelf", "product showcase", "professional setup", "clean environment",
        "natural lighting setup", "lifestyle setting", "home environment", "office desk",
        "outdoor setting", "kitchen counter", "bathroom vanity", "bedroom nightstand", "living room",
        "workshop table", "garage setup", "garden setting", "beach scene", "mountain backdrop",
        "urban rooftop", "forest clearing", "lakeside dock", "desert landscape", "snow-covered ground",
        "studio apartment", "luxury penthouse", "cozy cabin", "modern loft", "vintage shop",
        "art gallery", "museum display", "showroom floor", "conference room", "hotel lobby",
        "restaurant table", "cafe counter", "library shelf", "bookstore display", "market stall",
        "festival booth", "trade show", "popup shop", "warehouse space", "factory floor",
        "laboratory bench", "medical office", "spa setting", "gym environment", "school classroom",
        "children's playroom", "teen bedroom", "nursery", "elderly care facility", "pet store"
    ]
    
    # Expanded styles and aesthetics (40+ styles)
    styles = [
        "minimalist", "modern", "sleek", "elegant", "futuristic", "vintage", "retro", "classic",
        "industrial", "rustic", "luxury", "premium", "professional", "casual", "sporty", "artistic",
        "tech-focused", "eco-friendly", "colorful", "monochrome", "transparent", "metallic",
        "bohemian", "scandinavian", "mediterranean", "asian-inspired", "african-inspired", "tribal",
        "gothic", "steampunk", "cyberpunk", "art deco", "bauhaus", "mid-century", "contemporary",
        "traditional", "cultural", "ethnic", "handcrafted", "mass-produced", "limited-edition", "custom"
    ]
    
    # Expanded product features (50+ features)
    features = [
        "high-quality materials", "innovative design", "ergonomic shape", "compact size", "durable construction",
        "wireless technology", "smart features", "eco-friendly materials", "premium finish", "user-friendly interface",
        "versatile functionality", "portable design", "energy-efficient", "water-resistant", "scratch-resistant",
        "anti-slip surface", "foldable design", "stackable form", "magnetic attachment", "LED indicators",
        "touch-sensitive controls", "voice activation", "bluetooth connectivity", "wifi enabled", "app controlled",
        "rechargeable battery", "solar powered", "USB charging", "fast charging", "wireless charging",
        "antimicrobial coating", "stain-resistant", "odor-resistant", "UV protection", "thermal insulation",
        "noise cancellation", "shock absorption", "vibration dampening", "temperature control", "humidity control",
        "air purification", "water filtration", "self-cleaning", "automatic operation", "manual controls",
        "adjustable settings", "customizable options", "modular components", "interchangeable parts", "expandable system"
    ]
    
    # Expanded usage scenarios (40+ scenarios)
    scenarios = [
        "daily use", "professional work", "home organization", "outdoor adventures", "fitness activities",
        "creative projects", "entertainment", "cooking", "cleaning", "studying", "gaming", "traveling",
        "gardening", "pet care", "self-care", "home improvement", "gift giving", "collecting",
        "meditation", "relaxation", "party hosting", "holiday celebrations", "special occasions",
        "emergency preparedness", "disaster relief", "first aid", "medical care", "elderly care",
        "child care", "education", "learning", "skill development", "hobby pursuits", "artistic expression",
        "music making", "photography", "videography", "content creation", "social media", "business meetings",
        "remote work", "collaboration", "presentation", "demonstration", "training", "workshops"
    ]
    
    # Massive specific product list (200+ products)
    specific_products = [
        # Electronics & Tech
        "wireless headphones", "smartphone", "laptop", "smartwatch", "camera", "speaker", "tablet",
        "gaming console", "VR headset", "drone", "robot vacuum", "smart TV", "streaming device",
        "wireless charger", "power bank", "bluetooth earbuds", "smart home hub", "security camera",
        "doorbell camera", "smart lock", "smart thermostat", "smart light bulb", "smart switch",
        
        # Kitchen & Dining
        "coffee maker", "espresso machine", "blender", "food processor", "air fryer", "instant pot",
        "toaster", "microwave", "rice cooker", "slow cooker", "stand mixer", "hand mixer",
        "juicer", "smoothie maker", "coffee grinder", "tea kettle", "french press", "pour over",
        "cutting board", "knife set", "kitchen scale", "measuring cups", "mixing bowls", "cookware set",
        
        # Home & Living
        "throw pillow", "blanket", "area rug", "wall art", "picture frame", "vase", "candle",
        "diffuser", "humidifier", "air purifier", "fan", "heater", "lamp", "chandelier",
        "mirror", "clock", "storage box", "organizer", "basket", "shelf", "bookend",
        
        # Fashion & Accessories
        "handbag", "wallet", "sunglasses", "watch", "jewelry", "scarf", "hat", "belt",
        "shoes", "sneakers", "boots", "sandals", "slippers", "socks", "gloves", "tie",
        "cufflinks", "necklace", "bracelet", "earrings", "ring", "brooch", "hair accessory",
        
        # Sports & Fitness
        "yoga mat", "dumbbells", "resistance bands", "exercise ball", "foam roller", "water bottle",
        "gym bag", "fitness tracker", "running shoes", "workout clothes", "towel", "protein shaker",
        "bike helmet", "cycling gloves", "tennis racket", "golf clubs", "basketball", "soccer ball",
        
        # Tools & Hardware
        "screwdriver set", "hammer", "drill", "saw", "pliers", "wrench set", "measuring tape",
        "level", "toolbox", "work gloves", "safety glasses", "flashlight", "multitool", "utility knife",
        
        # Beauty & Personal Care
        "skincare set", "makeup brush", "hair dryer", "curling iron", "straightener", "electric toothbrush",
        "facial cleanser", "moisturizer", "perfume", "cologne", "nail polish", "lipstick", "foundation",
        
        # Office & Stationery
        "notebook", "planner", "pen set", "pencil case", "stapler", "paper clips", "folders",
        "binders", "calculator", "desk organizer", "mouse pad", "keyboard", "monitor stand",
        
        # Baby & Kids
        "baby bottle", "pacifier", "diaper bag", "car seat", "stroller", "high chair", "crib",
        "toy car", "doll", "puzzle", "building blocks", "educational toy", "stuffed animal",
        
        # Pet Supplies
        "dog leash", "cat toy", "pet bed", "food bowl", "water fountain", "carrier", "collar",
        "pet grooming kit", "aquarium", "bird cage", "hamster wheel", "pet food", "treats"
    ]
    
    # Expanded materials (30+ materials)
    materials = [
        "wood", "metal", "glass", "plastic", "fabric", "leather", "ceramic", "silicone", "carbon fiber",
        "bamboo", "cork", "rubber", "steel", "aluminum", "copper", "brass", "titanium", "gold",
        "silver", "platinum", "marble", "granite", "concrete", "stone", "crystal", "acrylic",
        "vinyl", "cotton", "linen", "wool", "silk", "cashmere", "denim", "canvas"
    ]
    
    # Expanded colors (50+ colors)
    colors = [
        "black", "white", "gray", "silver", "gold", "rose gold", "copper", "bronze",
        "red", "crimson", "burgundy", "pink", "fuchsia", "coral", "salmon", "peach",
        "orange", "amber", "yellow", "lime", "green", "emerald", "mint", "teal",
        "blue", "navy", "royal blue", "sky blue", "turquoise", "cyan", "purple",
        "violet", "lavender", "magenta", "brown", "tan", "beige", "cream", "ivory",
        "charcoal", "slate", "pewter", "champagne", "mahogany", "walnut", "oak", "pine",
        "olive", "forest green", "sage", "seafoam", "periwinkle", "dusty rose"
    ]
    
    # Photography styles (30+ styles)
    photo_styles = [
        "studio photography", "lifestyle photography", "macro photography", "portrait style",
        "documentary style", "artistic photography", "commercial photography", "product photography",
        "fashion photography", "architectural photography", "landscape style", "abstract photography",
        "minimalist photography", "dramatic photography", "soft photography", "bright photography",
        "moody photography", "vintage photography", "modern photography", "clean photography",
        "detailed photography", "wide angle photography", "close-up photography", "overhead photography",
        "side angle photography", "diagonal composition", "symmetrical composition", "asymmetrical composition",
        "rule of thirds", "golden ratio composition", "negative space photography", "texture focus"
    ]
    
    # Lighting conditions (25+ lighting types)
    lighting_conditions = [
        "natural lighting", "studio lighting", "soft lighting", "dramatic lighting", "bright lighting",
        "moody lighting", "golden hour lighting", "blue hour lighting", "sunset lighting", "sunrise lighting",
        "overcast lighting", "direct sunlight", "diffused lighting", "backlighting", "side lighting",
        "front lighting", "rim lighting", "ambient lighting", "artificial lighting", "LED lighting",
        "fluorescent lighting", "incandescent lighting", "candlelight", "firelight", "neon lighting"
    ]
    
    # Generate prompts by combining elements
    prompts = []
    
    # Basic product showcase prompts (50 * 60 * 40 = 120,000 combinations, sample 2000)
    for i, category in enumerate(product_categories):
        for j, environment in enumerate(environments):
            for k, style in enumerate(styles):
                if (i + j + k) % 60 == 0:  # Sample every 60th combination
                    prompt = f"{style.title()} {category} product displayed in {environment} with professional photography and clean composition"
                    prompts.append(prompt)
    
    # Feature-focused prompts (50 * 50 * 60 = 150,000 combinations, sample 2500)
    for i, feature in enumerate(features):
        for j, category in enumerate(product_categories):
            for k, environment in enumerate(environments):
                if (i + j + k) % 60 == 0:
                    prompt = f"High-end {category} showcasing {feature} in {environment} with detailed product photography"
                    prompts.append(prompt)
    
    # Lifestyle and usage prompts (40 * 50 * 40 = 80,000 combinations, sample 1500)
    for i, scenario in enumerate(scenarios):
        for j, category in enumerate(product_categories):
            for k, style in enumerate(styles):
                if (i + j + k) % 53 == 0:
                    prompt = f"{style.title()} {category} designed for {scenario} with modern aesthetic and premium quality"
                    prompts.append(prompt)
    
    # Specific product prompts (200 * 60 * 30 = 360,000 combinations, sample 3000)
    for i, product in enumerate(specific_products):
        for j, environment in enumerate(environments):
            for k, photo_style in enumerate(photo_styles):
                if (i + j + k) % 120 == 0:
                    prompt = f"{photo_style.title()} of {product} in {environment} with professional composition"
                    prompts.append(prompt)
    
    # Material and color combinations (30 * 50 * 50 = 75,000 combinations, sample 1500)
    for i, material in enumerate(materials):
        for j, color in enumerate(colors):
            for k, category in enumerate(product_categories):
                if (i + j + k) % 50 == 0:
                    prompt = f"Premium {color} {material} {category} with elegant design and modern styling in professional product photography"
                    prompts.append(prompt)
    
    # Lighting and style combinations (25 * 200 * 30 = 150,000 combinations, sample 2000)
    for i, lighting in enumerate(lighting_conditions):
        for j, product in enumerate(specific_products):
            for k, photo_style in enumerate(photo_styles):
                if (i + j + k) % 75 == 0:
                    prompt = f"{photo_style.title()} of {product} with {lighting} and professional composition"
                    prompts.append(prompt)
    
    # Complex combination prompts (material + color + product + environment + lighting)
    for i, material in enumerate(materials[:20]):
        for j, color in enumerate(colors[:30]):
            for k, product in enumerate(specific_products[:100]):
                for l, environment in enumerate(environments[:30]):
                    for m, lighting in enumerate(lighting_conditions[:15]):
                        if (i + j + k + l + m) % 200 == 0:
                            prompt = f"Professional product photography of {color} {material} {product} in {environment} with {lighting} and clean composition"
                            prompts.append(prompt)
    
    # Style and feature combinations
    for i, style in enumerate(styles):
        for j, feature in enumerate(features):
            for k, product in enumerate(specific_products[:150]):
                if (i + j + k) % 80 == 0:
                    prompt = f"{style.title()} {product} featuring {feature} with professional product photography and studio lighting"
                    prompts.append(prompt)
    
    # Scenario-based detailed prompts
    for i, scenario in enumerate(scenarios):
        for j, product in enumerate(specific_products):
            for k, environment in enumerate(environments[:40]):
                if (i + j + k) % 100 == 0:
                    prompt = f"Lifestyle product photography showing {product} in use for {scenario} in {environment} setting"
                    prompts.append(prompt)
    
    return prompts

# Generate the massive product prompt pool
ALL_PROMPTS = generate_product_prompts()

async def generate_ai_image_with_caption():
    """Generate a random AI image with descriptive caption and identity name"""
    if not openai_client:
        return None, None, "OpenAI API not configured"
    
    try:
        # Select product prompt first, then generate contextual name
        base_prompt = random.choice(ALL_PROMPTS)
        identity_name = generate_contextual_product_name(base_prompt)
        
        # Add randomization elements to make each image unique
        style_modifiers = [
            "photorealistic", "digital art", "oil painting", "watercolor", 
            "pencil sketch", "acrylic painting", "impressionist", "surreal",
            "minimalist", "hyper-detailed", "vintage", "modern", "artistic"
        ]
        
        lighting_modifiers = [
            "dramatic lighting", "soft lighting", "golden hour", "blue hour",
            "studio lighting", "natural lighting", "moody lighting", "bright lighting",
            "cinematic lighting", "ethereal glow", "warm tones", "cool tones"
        ]
        
        # Randomly add style and lighting modifiers (30% chance each)
        prompt_parts = [base_prompt]
        if random.random() < 0.3:
            prompt_parts.append(random.choice(style_modifiers))
        if random.random() < 0.3:
            prompt_parts.append(random.choice(lighting_modifiers))
        
        # Combine all parts for final prompt
        prompt = ", ".join(prompt_parts)
        
        # Generate image and caption simultaneously for faster performance
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        
        # Pre-select caption style to reduce processing time
        caption_styles = [
            "inspiring and uplifting", "mysterious and intriguing", "poetic and artistic",
            "adventurous and exciting", "peaceful and calming", "dramatic and intense",
            "whimsical and playful", "philosophical and deep", "energetic and vibrant",
            "mystical and ethereal", "bold and confident", "dreamy and surreal"
        ]
        selected_style = random.choice(caption_styles)
        
        # Run image generation and caption generation concurrently
        import asyncio
        
        async def generate_image():
            if not openai_client:
                raise Exception("OpenAI API key not configured")
            return openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024",
                quality="standard"
            )
        
        async def generate_caption():
            if not openai_client:
                raise Exception("OpenAI API key not configured")
            return openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"You are a creative writer. Create a short, engaging caption for an AI-generated image. Use exactly 5-7 words. Make it {selected_style}. Vary your language and avoid repetitive phrases. IMPORTANT: Avoid all finance-related words like cash, money, dollar, payment, finance, banking, salary, income, revenue, profit, cost, price, budget, investment, wealth, rich, expensive, cheap, pay, buy, sell, purchase, transaction, credit, debit, loan, mortgage, interest, currency, tax, billing, account, balance, fund."
                    },
                    {
                        "role": "user",
                        "content": f"Create a unique 5-7 word caption for this image: {prompt}"
                    }
                ],
                max_tokens=30,  # Reduced for faster response
                temperature=0.9  # Slightly higher for more variety
            )
        
        # Execute both API calls concurrently
        image_task = asyncio.create_task(generate_image())
        caption_task = asyncio.create_task(generate_caption())
        
        # Wait for both to complete
        image_response, caption_response = await asyncio.gather(image_task, caption_task)
        
        if not image_response or not image_response.data:
            raise Exception("Failed to generate image")
        image_url = image_response.data[0].url
        
        if not caption_response or not caption_response.choices:
            raise Exception("Failed to generate caption")
        caption_content = caption_response.choices[0].message.content
        caption = caption_content.strip() if caption_content else "AI Generated Product"
        
        return identity_name, image_url, caption
        
    except Exception as e:
        print(f"❌ Error generating AI image: {e}")
        return None, None, f"Error generating image: {str(e)}"

@client.event
async def on_ready():
    print(f"✅ Bot is online as {client.user} (Instance: {INSTANCE_ID})")

def compress_video(input_path, target_mb=23):
    import subprocess, shutil
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return None
    try:
        # Get duration
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ], capture_output=True, text=True, timeout=30)
        duration = float(probe.stdout.strip())
        if duration <= 0:
            return None

        target_bits = target_mb * 1024 * 1024 * 8
        audio_bitrate = 96  # kbps
        video_bitrate = int(target_bits / duration / 1000) - audio_bitrate
        if video_bitrate < 100:
            return None  # Too long to compress meaningfully

        output_path = input_path.replace(".mp4", "_compressed.mp4")
        result = subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-b:v", f"{video_bitrate}k", "-b:a", f"{audio_bitrate}k",
            "-maxrate", f"{video_bitrate * 2}k", "-bufsize", f"{video_bitrate * 4}k",
            "-vf", "scale=-2:720",
            "-c:v", "libx264", "-c:a", "aac",
            "-preset", "fast", output_path
        ], capture_output=True, text=True, timeout=120)

        if result.returncode == 0 and os.path.exists(output_path):
            compressed_size = os.path.getsize(output_path)
            if compressed_size <= target_mb * 1024 * 1024:
                return output_path
    except Exception as e:
        print(f"⚠️ Compression error: {e}")
    return None


def ensure_h264(input_path):
    """Convert video to H.264/AAC MP4 if it's HEVC — needed for iOS Photos compatibility."""
    import subprocess, shutil
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        return input_path
    if not input_path.lower().endswith(('.mp4', '.mov', '.mkv', '.webm')):
        return input_path
    try:
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ], capture_output=True, text=True, timeout=15)
        codec = probe.stdout.strip().lower()
        if codec not in ("hevc", "h265", "vp9", "av1"):
            return input_path  # Already H.264 or compatible, no conversion needed
        print(f"🔄 Converting {codec} → H.264 for iOS compatibility...")
        output_path = input_path.rsplit(".", 1)[0] + "_h264.mp4"
        result = subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path
        ], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(output_path):
            try:
                os.remove(input_path)
            except Exception:
                pass
            return output_path
    except Exception as e:
        print(f"⚠️ H.264 conversion error: {e}")
    return input_path


class InstagramSessionExpired(Exception):
    pass


def download_instagram_url(url):
    import tempfile
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget

    tmpdir = tempfile.mkdtemp(prefix="instagram_")

    # Build cookies.txt from INSTAGRAM_SESSIONID secret if available
    cookies_file = None
    session_id = os.environ.get("INSTAGRAM_SESSIONID", "").strip()
    if session_id:
        cookies_file = os.path.join(tmpdir, "instagram_cookies.txt")
        with open(cookies_file, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(f".instagram.com\tTRUE\t/\tTRUE\t9999999999\tsessionid\t{session_id}\n")
        print(f"✅ Using Instagram session cookie")

    try:
        ydl_opts = {
            'outtmpl': os.path.join(tmpdir, '%(autonumber)s_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'impersonate': ImpersonateTarget('chrome', None, 'windows', None),
            # Grab Instagram's combined H.264 MP4 first (pre-merged, fast, iOS-compatible)
            # Fall back to H.264 DASH, then anything non-VP9, then anything
            'format': (
                'best[ext=mp4][vcodec^=avc1]'
                '/best[ext=mp4][vcodec^=avc]'
                '/best[ext=mp4][vcodec!*=vp9][vcodec!*=hevc][vcodec!*=av01]'
                '/bestvideo[vcodec^=avc1]+bestaudio'
                '/bestvideo[vcodec^=avc]+bestaudio'
                '/bestvideo[vcodec!*=vp9][vcodec!*=hevc][vcodec!*=av01]+bestaudio'
                '/best[ext=mp4]'
                '/best'
            ),
        }
        if cookies_file:
            ydl_opts['cookiefile'] = cookies_file

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        files = sorted([
            os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
            if os.path.isfile(os.path.join(tmpdir, f)) and not f.endswith('.txt')
        ])
        print(f"📥 Instagram downloaded {len(files)} file(s): {[os.path.basename(f) for f in files]}")
        # Fallback: convert any remaining HEVC/VP9/AV1 to H.264 for iOS compatibility
        files = [ensure_h264(f) for f in files]
        return files if files else []
    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ("login required", "checkpoint_required", "not logged in",
                                   "login_required", "loginrequired", "please log in",
                                   "bad cookies", "cookie", "session")):
            print(f"⚠️ Instagram session expired for {url}")
            raise InstagramSessionExpired("Instagram session expired")
        print(f"⚠️ Instagram yt-dlp error for {url}: {e}")
        return []


def download_tiktok_url(url):
    import tempfile
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget

    tmpdir = tempfile.mkdtemp(prefix="tiktok_")

    try:
        ydl_opts = {
            'outtmpl': os.path.join(tmpdir, '%(autonumber)s_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'impersonate': ImpersonateTarget('chrome', None, 'windows', None),
            'extractor_args': {'tiktok': {'api_hostname': 'api22-normal-c-useast2a.tiktokv.com'}},
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        files = sorted([
            os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
            if os.path.isfile(os.path.join(tmpdir, f))
        ])
        return files if files else []
    except Exception as e:
        print(f"⚠️ yt-dlp error for {url}: {e}")
        return []


def spidey_request(method, path, payload=None):
    """Make a request to the Spidey Comment Bot API."""
    import json
    from curl_cffi import requests as cf_requests
    api_key = os.environ.get("SPIDEY_API_KEY", "")
    url = f"https://spideyscommentbot.com{path}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        if method == "GET":
            resp = cf_requests.get(url, headers=headers, timeout=15, impersonate="chrome110")
        else:
            resp = cf_requests.post(url, headers=headers, json=payload or {}, timeout=15, impersonate="chrome110")
        try:
            return resp.json()
        except Exception:
            return {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}


def resolve_tiktok_post_id(url):
    """Follow redirects and extract TikTok post ID from any TikTok URL."""
    import urllib.request, re as _re
    final_url = url
    try:
        req = urllib.request.Request(url.strip(), headers={
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            final_url = resp.url
    except Exception:
        pass
    match = _re.search(r'/(?:video|photo)/(\d+)', final_url)
    if match:
        clean_url = final_url.split('?')[0]
        return match.group(1), clean_url
    return None, final_url


# ── Interactive Boost UI ──────────────────────────────────────────────────────

class BoostListSelect(discord.ui.Select):
    def __init__(self, campaigns):
        options = []
        for c in sorted(campaigns, key=lambda x: x.get("user_list_num", x.get("id", 0)))[:24]:
            cnum = c.get("user_list_num", c.get("id"))
            name = c.get("name", "Unnamed")[:80]
            options.append(discord.SelectOption(label=f"#{cnum} — {name}", value=str(cnum)))
        options.insert(0, discord.SelectOption(label="— No comments (likes only) —", value="none", default=False))
        super().__init__(
            placeholder="Pick comment list(s)…",
            min_values=0,
            max_values=min(len(options), 25),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_lists = [int(v) for v in self.values if v != "none"]
        if self.view.selected_lists:
            selected_text = ", ".join(f"#{x}" for x in self.view.selected_lists)
            await interaction.response.send_message(
                f"✅ Lists selected: {selected_text} — now click **Submit ▶**",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ No list selected (likes only) — click **Submit ▶** to continue.",
                ephemeral=True,
            )


class BoostLikeModal(discord.ui.Modal, title="Boost — Like Quantity"):
    qty = discord.ui.TextInput(
        label="Like quantity (leave blank for no likes)",
        placeholder="e.g. 500",
        required=False,
        max_length=6,
    )

    def __init__(self, boost_view):
        super().__init__()
        self._boost_view = boost_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = self._boost_view
        quantity = None
        if self.qty.value.strip():
            try:
                quantity = int(self.qty.value.strip())
            except ValueError:
                await interaction.followup.send("❌ Quantity must be a number.", ephemeral=True)
                return

        selected_lists = view.selected_lists
        if not selected_lists and not quantity:
            await interaction.followup.send(
                "❌ Pick at least one comment list or enter a like quantity.", ephemeral=True
            )
            return

        payload = {"video_ids": view.video_ids, "video_links": view.video_links}
        if selected_lists:
            payload["comment_list_ids"] = selected_lists
        if quantity:
            payload["likes"] = {"service": "7990", "quantity": quantity}

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, spidey_request, "POST", "/api/jobs/submit", payload)

        if "error" in result:
            await interaction.followup.send(f"❌ API error: {result['error']}", ephemeral=True)
            return

        jobs_returned = result if isinstance(result, list) else result.get("jobs", [])
        job_nums = []
        if jobs_returned:
            for j in jobs_returned:
                jnum = j.get("user_job_num", j.get("id")) if isinstance(j, dict) else j
                if jnum:
                    job_nums.append(f"#{jnum}")

        lines = [f"✅ **{len(view.video_ids)} job(s) submitted**", "━━━━━━━━━━━━━━━━━"]
        if selected_lists:
            lines.append(f"💬 Lists: {', '.join('#' + str(x) for x in selected_lists)}")
        if quantity:
            lines.append(f"❤️ Likes: **{quantity}** per video")
        if job_nums:
            lines.append(f"🆔 Jobs: {', '.join(job_nums)}")

        view.stop()
        try:
            await view.message.delete()
        except Exception:
            pass
        await interaction.followup.send(f"{interaction.user.mention}\n" + "\n".join(lines))


class BoostSubmitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Submit ▶", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BoostLikeModal(self.view))


class BoostCancelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Cancel ✕", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        self.view.stop()
        await interaction.response.edit_message(content="❌ Boost cancelled.", view=None)


class BoostView(discord.ui.View):
    def __init__(self, video_ids, video_links, campaigns):
        super().__init__(timeout=120)
        self.video_ids = video_ids
        self.video_links = video_links
        self.selected_lists = []
        self.message = None
        self.add_item(BoostListSelect(campaigns))
        self.add_item(BoostSubmitButton())
        self.add_item(BoostCancelButton())

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏱️ Boost form expired.", view=self)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────

@client.event
async def on_message(message):
    try:
        # Ignore messages from bots
        if message.author.bot:
            return
        
        # Check if the bot is mentioned
        if client.user in message.mentions:
            # Additional check for private bot - ensure bot has proper permissions
            if not message.guild:
                print(f"🔧 Debug [{INSTANCE_ID}] - Private message detected")
                return
            
            # Check if bot has permission to send messages in this channel
            if not message.channel.permissions_for(message.guild.me).send_messages:
                print(f"🔧 Debug [{INSTANCE_ID}] - No permission to send messages in this channel")
                return
            # Load processed messages and cleanup old ones
            processed_messages = load_processed_messages()
            cleanup_old_messages(processed_messages)
            
            # Deduplication check - prevent processing same message multiple times
            message_key = str(message.id)
            current_time = time.time()
            
            # Check if this exact message was already processed recently
            if message_key in processed_messages and (current_time - processed_messages[message_key]) < COOLDOWN_SECONDS:
                time_since = current_time - processed_messages[message_key]
                print(f"🔧 Debug [{INSTANCE_ID}] - Skipping duplicate message: {message_key} (processed {time_since:.1f}s ago)")
                return
            
            # Mark message as processed
            processed_messages[message_key] = current_time
            save_processed_messages(processed_messages)
            
            print(f"🔧 Debug [{INSTANCE_ID}] - Processing message: {message_key}")
            
            # Extract the message content without the mention
            content = message.content
            # Remove the mention from the content
            content = re.sub(r'<@!?\d+>', '', content).strip()
            
            parts = content.split()
            print(f"🔧 Debug [{INSTANCE_ID}] - Content: '{content}'")
            print(f"🔧 Debug [{INSTANCE_ID}] - Parts: {parts}")
            
            # If no parts (just a mention), show help
            if not parts:
                print(f"🔧 Debug [{INSTANCE_ID}] - Just a mention, showing help")
                await message.channel.send(
                    "━━━━━━━━━━━━━━━━━\n"
                    "**🛍️ Shopify**\n"
                    "`@Mexo shopify slug subid offer` — Generate page link\n"
                    "`@Mexo cloak slug source offer [domain]` — Generate cloak link\n"
                    "`@Mexo setlink slug source offer [domain]` — Set default source/offer for slug\n"
                    "`@Mexo getlink slug` — View current slug config\n"
                    "`@Mexo clearlink slug` — Clear slug config\n"
                    "`@Mexo bypass slug` — Disable cloaking (redirect all visitors)\n"
                    "`@Mexo unbypass slug` — Re-enable cloaking\n"
                    "`@Mexo split s bucket1 bucket2 [...]` — Fan subid out to N buckets\n"
                    "`@Mexo splitdel s` — Remove a split registration\n"
                    "`@Mexo offers` — Show valid offer codes\n"
                    "\n**📥 Downloads**\n"
                    "`@Mexo tiktok URL1 URL2 ...` — Download TikTok videos\n"
                    "`@Mexo instagram URL1 URL2 ...` — Download Instagram Reels\n"
                    "`@Mexo postid URL1 URL2 ...` — Get clean TikTok links\n"
                    "\n**🚀 Boost**\n"
                    "`@Mexo boost URL1 URL2` — Add comments/likes (interactive form)\n"
                    "`@Mexo jobs` — View all boost jobs\n"
                    "`@Mexo stopjob ID` — Stop a running job\n"
                    "`@Mexo lists` — View comment lists\n"
                    "`@Mexo balance` — Check JAP balance\n"
                    "\n**📊 Revenue**\n"
                    "`@Mexo rev` — Today's revenue report\n"
                    "`@Mexo rev subid` — Breakdown for a subid\n"
                    "\n**🎨 AI**\n"
                    "`@Mexo identity` — Generate AI product image\n"
                    "`@Mexo random` — Generate random name\n"
                    "━━━━━━━━━━━━━━━━━"
                )
                return
            
            # Handle specific commands first
            if len(parts) >= 1:
                command = parts[0].lower()
                
                # Handle "identity" command for AI image generation
                if command == 'identity':
                    print(f"🔧 Debug [{INSTANCE_ID}] - Processing identity command")
                    
                    if not openai_client:
                        await message.channel.send("❌ AI image generation not available - OpenAI API key not configured")
                        return
                    
                    try:
                        # Generate AI image with caption and identity name
                        identity_name, image_url, caption = await generate_ai_image_with_caption()
                        
                        if image_url:
                            # Format the response as requested:
                            # Just the name - Captions of 5-7 words on same line with image in same message
                            response_text = f"{message.author.mention} **{identity_name}** - {caption}"
                            
                            # Download image and send as file attachment with caption
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                async with session.get(image_url) as resp:
                                    if resp.status == 200:
                                        image_data = await resp.read()
                                        file = discord.File(io.BytesIO(image_data), filename="brand-logo.png")
                                        await message.channel.send(response_text, file=file)
                                    else:
                                        # Fallback to URL if download fails
                                        await message.channel.send(f"{response_text}\n{image_url}")
                            
                            print(f"🔧 Debug [{INSTANCE_ID}] - AI image sent successfully")
                        else:
                            await message.channel.send(f"❌ Failed to generate image: {caption}")
                            
                    except Exception as e:
                        error_msg = str(e)
                        if "billing_hard_limit_reached" in error_msg:
                            await message.channel.send("❌ **OpenAI billing limit reached**\n\nTo use AI image generation, you need to:\n1. Go to https://platform.openai.com/settings/billing\n2. Add credits to your OpenAI account\n3. Try the `@bot identity` command again")
                        else:
                            await message.channel.send(f"❌ Error generating AI image: {error_msg}")
                        print(f"🔧 Debug [{INSTANCE_ID}] - Error in AI generation: {e}")
                    
                    return
                
                # Handle "cloak" command
                elif command == "cloak":
                    # Generate Cloudflare Worker cloak link
                    if len(parts) >= 4:
                        slug = parts[1]
                        source = parts[2]
                        offer = parts[3].lower()

                        # Validate offer
                        if offer not in ALLOWED_OFFERS:
                            await message.channel.send(f"{message.author.mention} ❌ Invalid offer code: `{offer}`\nUse `@Mexo offers` to see valid offers.")
                            return

                        # Optional domain override (5th arg)
                        if len(parts) >= 5:
                            base_domain = resolve_domain(parts[4])
                            if base_domain is None:
                                domain_list = ", ".join(d.replace("https://", "") for d in WORKER_DOMAINS)
                                await message.channel.send(
                                    f"{message.author.mention} ❌ Unknown domain `{parts[4]}`.\n"
                                    f"Available: `{domain_list}`"
                                )
                                return
                        else:
                            base_domain = next_domain()

                        thinking_msg = await message.channel.send(f"{message.author.mention} ⏳ Creating cloak page...")
                        worker_url, upload_error = create_cloak_page(slug)
                        await thinking_msg.delete()

                        if not worker_url:
                            await message.channel.send(
                                f"{message.author.mention} ❌ Failed to create cloak page for `{slug}`.\n"
                                f"```{upload_error}```"
                            )
                            return

                        cloak_url = f"{base_domain}/{slug}?s={source}&o={offer}&placement=__PLACEMENT__&tt_cid=__CAMPAIGN_ID__&campaign_name=__CAMPAIGN_NAME__"
                        privacy_url = f"{base_domain}/privacy/{slug}"
                        await message.channel.send(
                            f"{message.author.mention}\n🔗 **Cloak Link**\n━━━━━━━━━━━━━━━━━\n{cloak_url}\n\n"
                            f"🔒 **Privacy**\n━━━━━━━━━━━━━━━━━\n{privacy_url}"
                        )
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo cloak slug source offer [domain]`\nExample: `@Mexo cloak my-page test123 cash dewleaf.shop`")
                    return
                
                # Handle "stats" command
                elif command == "stats":
                    await message.channel.send(f"{message.author.mention} 📊 **Bot Stats:**\n• Identity names: 8,858+ combinations\n• Image prompts: 48 themes\n• Valid offers: {len(ALLOWED_OFFERS)}\n• Uptime: 24/7 on Replit")
                    return
                
                # Handle "offers" command
                elif command == "offers":
                    # Show valid offers grouped by type
                    offers_text = (
                        f"{message.author.mention}\n✅ **Valid Offer Codes**\n━━━━━━━━━━━━━━━━━\n"
                        + "  ".join(f"`{o}`" for o in ALLOWED_OFFERS)
                    )
                    await message.channel.send(offers_text)
                    return
                
                elif command == "rev":
                    now_est = datetime.now(EST)
                    time_label = now_est.strftime('%I:%M %p EST')
                    
                    subid_filter = parts[1] if len(parts) >= 2 else None
                    
                    if subid_filter:
                        result = get_maxconv_subid_offers(subid_filter)
                        
                        if result == "no_api_key":
                            await message.reply("❌ MaxConv API key not configured.", mention_author=True)
                            return
                        
                        if not result or (isinstance(result, list) and len(result) == 0):
                            await message.reply(f"📊 **{subid_filter} — Offer Breakdown**\nNo data found.\n⏰ {time_label}", mention_author=True)
                            return
                        
                        parsed_rows = []
                        for row in result:
                            if isinstance(row, dict):
                                offer_name = row.get("offer_name", "unknown")
                                clicks = int(row.get("uniq_clicks_ip", 0))
                                convs = int(row.get("convs", 0))
                                rev = float(row.get("revenue", 0))
                                if rev > 0 or clicks > 0 or convs > 0:
                                    parsed_rows.append((offer_name, clicks, convs, rev))
                        
                        parsed_rows.sort(key=lambda x: x[3], reverse=True)
                        
                        rev_text = f"📊 **{subid_filter} — Offer Breakdown**\n⏰ {time_label}\n━━━━━━━━━━━━━━━━━\n"

                        if parsed_rows:
                            t_clicks = sum(r[1] for r in parsed_rows)
                            t_convs = sum(r[2] for r in parsed_rows)
                            t_rev = sum(r[3] for r in parsed_rows)
                            t_uepc = t_rev / t_clicks if t_clicks > 0 else 0
                            t_ucvr = t_convs / t_clicks * 100 if t_clicks > 0 else 0
                            rev_text += f"**Total: {t_clicks:,} clicks · ${t_uepc:.2f} uEPC · {t_ucvr:.2f}% uCVR · ${t_rev:,.2f}**\n━━━━━━━━━━━━━━━━━\n"
                            for offer_name, clicks, convs, rev in parsed_rows:
                                uepc = rev / clicks if clicks > 0 else 0
                                ucvr = convs / clicks * 100 if clicks > 0 else 0
                                line = f"**{offer_name}** — {clicks:,} clicks · ${uepc:.2f} uEPC · {ucvr:.2f}% uCVR · ${rev:,.2f}\n"
                                if len(rev_text) + len(line) > 1950:
                                    rev_text += "_...more offers not shown_"
                                    break
                                rev_text += line
                        else:
                            rev_text += "No data found."

                        await message.reply(rev_text, mention_author=True)
                        return
                    
                    result = get_maxconv_revenue()
                    
                    if result == "no_api_key":
                        await message.reply("❌ MaxConv API key not configured.", mention_author=True)
                        return
                    
                    if not result or (isinstance(result, list) and len(result) == 0):
                        await message.reply(f"📊 **Revenue Report**\nNo data found.\n⏰ {time_label}", mention_author=True)
                        return
                    
                    rows = result if isinstance(result, list) else [result]
                    
                    parsed_rows = []
                    
                    for row in rows:
                        if isinstance(row, dict):
                            subid = row.get("ct1", "") or ""
                            # Skip unknown/empty ct1 entirely — don't show or count
                            if not subid.strip() or subid.strip().lower() == "unknown":
                                continue
                            visits = int(row.get("uniq_visits_ip", 0))
                            clicks = int(row.get("uniq_clicks_ip", 0))
                            convs = int(row.get("convs", 0))
                            rev = float(row.get("revenue", 0))
                        else:
                            continue
                        
                        if rev > 0 or clicks > 0 or convs > 0:
                            parsed_rows.append((subid, visits, clicks, convs, rev))
                    
                    parsed_rows.sort(key=lambda x: x[4], reverse=True)
                    
                    rev_text = f"📊 **Revenue Report**\n⏰ {time_label}\n━━━━━━━━━━━━━━━━━\n"

                    if parsed_rows:
                        t_clicks = sum(r[2] for r in parsed_rows)
                        t_convs = sum(r[3] for r in parsed_rows)
                        t_rev = sum(r[4] for r in parsed_rows)
                        t_uepc = t_rev / t_clicks if t_clicks > 0 else 0
                        t_ucvr = t_convs / t_clicks * 100 if t_clicks > 0 else 0
                        rev_text += f"**Total: {t_clicks:,} clicks · ${t_uepc:.2f} uEPC · {t_ucvr:.2f}% uCVR · ${t_rev:,.2f}**\n━━━━━━━━━━━━━━━━━\n"
                        for subid, visits, clicks, convs, rev in parsed_rows:
                            uepc = rev / clicks if clicks > 0 else 0
                            ucvr = convs / clicks * 100 if clicks > 0 else 0
                            line = f"**{subid}** — {clicks:,} clicks · ${uepc:.2f} uEPC · {ucvr:.2f}% uCVR · ${rev:,.2f}\n"
                            if len(rev_text) + len(line) > 1950:
                                rev_text += "_...more subids not shown_"
                                break
                            rev_text += line
                    else:
                        rev_text += "No data for today."

                    await message.reply(rev_text, mention_author=True)
                    return
                
                # Handle "random" command
                elif command == "random":
                    # Generate random identity name with caption
                    try:
                        random_name, caption = await generate_random_identity_with_caption()
                        await message.channel.send(f"{message.author.mention}\n🎲 **{random_name}**\n_{caption}_")
                    except Exception as e:
                        random_name = generate_random_identity_name()
                        await message.channel.send(f"{message.author.mention}\n🎲 **{random_name}**")
                    return

                # Handle "postid" command — extract TikTok post IDs from URLs
                elif command == "postid":
                    raw = message.content
                    urls = re.findall(r'https?://\S+tiktok\.com/\S+', raw)
                    urls = [u.rstrip('.,;)>') for u in urls]
                    if not urls:
                        await message.reply(
                            "Send TikTok URLs after the command, e.g.:\n"
                            "`@Mexo postid https://vt.tiktok.com/ZSu5KDXnV/ https://www.tiktok.com/@user/video/123`",
                            mention_author=True
                        )
                        return
                    loop = asyncio.get_event_loop()
                    lines = []
                    ids = []
                    resolved_links = []
                    for url in urls:
                        post_id, resolved = await loop.run_in_executor(None, resolve_tiktok_post_id, url)
                        if post_id:
                            lines.append(f"`{post_id}` — {resolved}")
                            ids.append(post_id)
                            resolved_links.append(resolved)
                        else:
                            lines.append(f"⚠️ Could not extract ID from: {url}")
                    if resolved_links:
                        await message.reply(
                            f"🔗 **{len(resolved_links)} TikTok Link(s)**\n━━━━━━━━━━━━━━━━━\n"
                            f"```\n{chr(10).join(resolved_links)}\n```",
                            mention_author=True
                        )
                    else:
                        await message.reply("⚠️ Could not resolve any TikTok links.", mention_author=True)
                    return

                # Handle "tiktok" command — mass download TikTok videos
                elif command == "tiktok":
                    # Extract TikTok URLs from the remaining parts
                    raw = message.content
                    urls = re.findall(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/\S+', raw)
                    urls = [u.rstrip('.,;)>') for u in urls]

                    if not urls:
                        await message.reply("Send TikTok URLs after the command, e.g.:\n`@Mexo tiktok https://tiktok.com/... https://tiktok.com/...`", mention_author=True)
                        return

                    status_msg = await message.reply(f"⬇️ Downloading **{len(urls)}** video(s)...", mention_author=True)
                    loop = asyncio.get_event_loop()
                    ok, fail = 0, 0

                    for i, url in enumerate(urls):
                        try:
                            await status_msg.edit(content=f"⬇️ Downloading post **{i+1}/{len(urls)}**...")
                            if i > 0:
                                await asyncio.sleep(2)
                            files = await loop.run_in_executor(None, download_tiktok_url, url)
                            if not files:
                                # Retry once after a longer pause
                                await status_msg.edit(content=f"⬇️ Retrying post **{i+1}/{len(urls)}**...")
                                await asyncio.sleep(5)
                                files = await loop.run_in_executor(None, download_tiktok_url, url)
                            if not files:
                                if "/photo/" in url:
                                    await message.channel.send(
                                        f"❌ Post {i+1} is a **photo slideshow** (`/photo/` link) — TikTok blocks slideshow downloads from bots.\n"
                                        f"Download it manually at <https://ssstik.io> or <https://snaptik.app>"
                                    )
                                else:
                                    await message.channel.send(f"⚠️ Post {i+1} failed to download — may be private or unavailable")
                                fail += 1
                                continue

                            # Separate sendable from oversized
                            sendable = [f for f in files if os.path.getsize(f) <= 24 * 1024 * 1024]
                            oversized = [f for f in files if os.path.getsize(f) > 24 * 1024 * 1024]

                            # Try compressing oversized video files
                            compressed_files = []
                            for f in oversized:
                                if f.endswith('.mp4'):
                                    await status_msg.edit(content=f"🗜️ Compressing post **{i+1}** to fit Discord limit...")
                                    compressed = await loop.run_in_executor(None, compress_video, f)
                                    if compressed:
                                        sendable.append(compressed)
                                        compressed_files.append(compressed)
                                    else:
                                        await message.channel.send(f"⚠️ Post {i+1}: video too long to compress under 24MB")
                                else:
                                    await message.channel.send(f"⚠️ Post {i+1}: 1 file skipped — over 24MB")

                            if sendable:
                                # Send up to 10 files per Discord message (Discord limit)
                                for chunk_start in range(0, len(sendable), 10):
                                    chunk = sendable[chunk_start:chunk_start+10]
                                    await message.channel.send(files=[discord.File(f) for f in chunk])
                                ok += 1

                            # Clean up all downloaded and compressed files
                            for f in files + compressed_files:
                                try:
                                    os.remove(f)
                                except Exception:
                                    pass
                        except Exception as e:
                            print(f"TikTok error for {url}: {e}")
                            fail += 1

                    lines = [f"⬇️ **TikTok Download Complete**", "━━━━━━━━━━━━━━━━━", f"✅ Sent: **{ok}**"]
                    if fail:
                        lines.append(f"⚠️ Failed: **{fail}**")
                    await status_msg.edit(content=f"{message.author.mention}\n" + "\n".join(lines))
                    return

                # Handle "instagram" command — download Instagram Reels/posts
                elif command == "instagram":
                    raw = message.content
                    urls = re.findall(r'https?://(?:www\.)?instagram\.com/\S+', raw)
                    urls = [u.rstrip('.,;)>') for u in urls]

                    if not urls:
                        await message.reply(
                            "Send Instagram Reel or post URLs after the command, e.g.:\n"
                            "`@Mexo instagram https://instagram.com/reel/... https://instagram.com/reel/...`",
                            mention_author=True
                        )
                        return

                    status_msg = await message.reply(f"⬇️ Downloading **{len(urls)}** Instagram post(s)...", mention_author=True)
                    loop = asyncio.get_event_loop()
                    ok, fail = 0, 0

                    session_expired = False
                    for i, url in enumerate(urls):
                        try:
                            await status_msg.edit(content=f"⬇️ Downloading post **{i+1}/{len(urls)}**...")
                            files = await loop.run_in_executor(None, download_instagram_url, url)
                            if not files:
                                await message.channel.send(
                                    f"⚠️ Post {i+1} failed — may be private or unavailable"
                                )
                                fail += 1
                                continue

                            sendable = [f for f in files if os.path.getsize(f) <= 24 * 1024 * 1024]
                            oversized = [f for f in files if os.path.getsize(f) > 24 * 1024 * 1024]

                            # Try compressing oversized video files
                            compressed_files = []
                            for f in oversized:
                                if f.endswith('.mp4'):
                                    await status_msg.edit(content=f"🗜️ Compressing post **{i+1}** to fit Discord limit...")
                                    compressed = await loop.run_in_executor(None, compress_video, f)
                                    if compressed:
                                        sendable.append(compressed)
                                        compressed_files.append(compressed)
                                    else:
                                        await message.channel.send(f"⚠️ Post {i+1}: video too long to compress under 24MB")
                                else:
                                    await message.channel.send(f"⚠️ Post {i+1}: 1 file skipped — over 24MB")

                            if sendable:
                                for chunk_start in range(0, len(sendable), 10):
                                    chunk = sendable[chunk_start:chunk_start+10]
                                    await message.channel.send(files=[discord.File(f) for f in chunk])
                                ok += 1

                            for f in files + compressed_files:
                                try:
                                    os.remove(f)
                                except Exception:
                                    pass
                        except InstagramSessionExpired:
                            session_expired = True
                            fail += 1
                            break
                        except Exception as e:
                            print(f"Instagram error for {url}: {e}")
                            fail += 1

                    if session_expired:
                        await status_msg.edit(content=(
                            f"{message.author.mention} ❌ **Instagram session expired** — downloads won't work until the session is refreshed.\n"
                            f"1. Open Instagram in Chrome on desktop\n"
                            f"2. Press F12 → Application → Cookies → `instagram.com`\n"
                            f"3. Copy the `sessionid` cookie value\n"
                            f"4. Update `INSTAGRAM_SESSIONID` in Replit Secrets"
                        ))
                        return

                    lines = [f"📸 **Instagram Download Complete**", "━━━━━━━━━━━━━━━━━", f"✅ Sent: **{ok}**"]
                    if fail:
                        lines.append(f"⚠️ Failed: **{fail}**")
                    await status_msg.edit(content=f"{message.author.mention}\n" + "\n".join(lines))
                    return

                # Handle "boost" command — submit comment/like jobs via Spidey API
                elif command == "boost":
                    raw = message.content
                    urls = re.findall(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/\S+', raw)
                    urls = [u.rstrip('.,;)>') for u in urls]

                    if not urls:
                        await message.reply(
                            "Provide one or more TikTok URLs:\n"
                            "`@Mexo boost URL1 URL2`\n"
                            "A form will appear to pick your comment list and like quantity.",
                            mention_author=True
                        )
                        return

                    status_msg = await message.reply(
                        f"⏳ Resolving **{len(urls)}** URL(s)…", mention_author=True
                    )
                    loop = asyncio.get_event_loop()

                    # Resolve URLs and fetch lists in parallel
                    video_ids, video_links, failed = [], {}, []
                    for url in urls:
                        pid, clean = await loop.run_in_executor(None, resolve_tiktok_post_id, url)
                        if pid:
                            video_ids.append(pid)
                            video_links[pid] = clean
                        else:
                            failed.append(url)

                    if not video_ids:
                        await status_msg.edit(content=f"{message.author.mention} ❌ Could not resolve any TikTok URLs.")
                        return

                    campaigns_result = await loop.run_in_executor(None, spidey_request, "GET", "/api/campaigns", None)
                    campaigns = (
                        campaigns_result if isinstance(campaigns_result, list)
                        else campaigns_result.get("campaigns", [])
                    ) if "error" not in campaigns_result else []

                    view = BoostView(video_ids, video_links, campaigns)
                    note = f"⚠️ Could not resolve **{len(failed)}** URL(s)\n" if failed else ""
                    form_msg = await message.reply(
                        f"{message.author.mention}\n"
                        f"{note}"
                        f"**{len(video_ids)} video(s) ready.** Pick a comment list then click **Submit ▶** to enter like quantity.",
                        view=view,
                        mention_author=False
                    )
                    view.message = form_msg
                    await status_msg.delete()
                    return

                # Handle "jobs" command — list all jobs
                elif command == "jobs":
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, spidey_request, "GET", "/api/jobs", None)
                    if "error" in result:
                        await message.reply(f"❌ API error: {result['error']}", mention_author=True)
                        return
                    jobs = result if isinstance(result, list) else result.get("jobs", [])
                    if not jobs:
                        await message.reply("No jobs found.", mention_author=True)
                        return
                    status_icons = {"running": "🟢", "queued": "🟡", "done": "✅", "stopped": "⛔", "error": "🔴"}
                    lines = ["📋 **Your Jobs**", "━━━━━━━━━━━━━━━━━"]
                    import json as _json
                    for j in jobs[:20]:
                        jnum = j.get("user_job_num", j.get("id", "?"))
                        status = j.get("status", "?")
                        icon = status_icons.get(status, "⚪")
                        comments_sent = j.get("comments_sent", 0)
                        replies_sent = j.get("replies_sent", 0)
                        failed = j.get("failed", 0)
                        list_names = j.get("comment_list_names")
                        try:
                            names = _json.loads(list_names) if isinstance(list_names, str) else (list_names or [])
                            names_str = f"\n　　📝 {', '.join(names)}" if names else ""
                        except Exception:
                            names_str = ""
                        lines.append(f"{icon} **#{jnum}** · {status}\n　　💬 {comments_sent} comments · ↩️ {replies_sent} replies · ❌ {failed} failed{names_str}")
                    await message.reply("\n".join(lines), mention_author=True)
                    return

                # Handle "stopjob" command — stop a job by ID
                elif command == "stopjob":
                    if not parts:
                        await message.reply("Provide a job ID: `@Mexo stopjob 123`", mention_author=True)
                        return
                    job_id = parts[0]
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, spidey_request, "POST", f"/api/jobs/{job_id}/stop", {})
                    if "error" in result:
                        await message.reply(f"❌ Could not stop job `#{job_id}`\n_{result['error']}_", mention_author=True)
                    else:
                        await message.reply(f"⛔ **Job #{job_id} stopped.**", mention_author=True)
                    return

                # Handle "lists" command — show available comment lists
                elif command == "lists":
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, spidey_request, "GET", "/api/campaigns", None)
                    if "error" in result:
                        await message.reply(f"❌ API error: {result['error']}", mention_author=True)
                        return
                    campaigns = result if isinstance(result, list) else result.get("campaigns", [])
                    if not campaigns:
                        await message.reply("No comment lists found.", mention_author=True)
                        return
                    lines = ["📝 **Comment Lists**", "━━━━━━━━━━━━━━━━━"]
                    for c in sorted(campaigns, key=lambda x: x.get('user_list_num', x.get('id', 0))):
                        name = c.get('name', 'Unnamed')
                        cnum = c.get('user_list_num', c.get('id'))
                        comment_count = c.get('comment_count')
                        reply_count = c.get('reply_count')
                        if comment_count is not None:
                            count_str = f"💬 {comment_count} comments · ↩️ {reply_count} replies"
                        else:
                            raw = c.get('comments', [])
                            count = len(raw) if isinstance(raw, list) else 0
                            count_str = f"💬 {count} comments"
                        lines.append(f"**#{cnum}** · {name}\n　　{count_str}")
                    await message.reply("\n".join(lines), mention_author=True)
                    return

                # Handle "link" command — generate Shopify page link
                elif command == "shopify":
                    if len(parts) >= 4:
                        slug = parts[1]
                        subid = parts[2]
                        offer = parts[3].lower()

                        if offer not in ALLOWED_OFFERS:
                            await message.channel.send(f"{message.author.mention} ❌ Invalid offer code: `{offer}`\nUse `@Mexo offers` to see valid offers.")
                            return

                        try:
                            page_created = create_shopify_page(slug)
                            if page_created:
                                print(f"✅ Page ready: /pages/{slug}")
                            else:
                                print(f"⚠️ Page creation skipped or failed for '{slug}'")
                        except Exception as e:
                            print(f"⚠️ Page creation error: {e}")

                        final_url = f"{SHOPIFY_BASE_URL}pages/{slug}?s={subid}&o={offer}&tt_cid=__CAMPAIGN_ID__&campaign_name=__CAMPAIGN_NAME__"

                        await message.channel.send(f"{message.author.mention}\n🔗 **Shopify Link**\n━━━━━━━━━━━━━━━━━\n{final_url}")
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo shopify slug subid offer`\nExample: `@Mexo shopify my-page ct123 cash`")
                    return

                # Handle "setlink" command — set per-slug offer/source config on Worker
                elif command == "setlink":
                    if len(parts) >= 3:
                        slug = parts[1]
                        source = parts[2]
                        offer = parts[3].lower() if len(parts) >= 4 else None
                        if offer and offer not in ALLOWED_OFFERS:
                            await message.channel.send(
                                f"{message.author.mention} ❌ `{offer}` is not a valid offer. "
                                f"Use `@Mexo offers` to see the full list."
                            )
                            return
                        # Optional domain override (5th arg, after slug source offer)
                        if len(parts) >= 5:
                            base_domain = resolve_domain(parts[4])
                            if base_domain is None:
                                domain_list = ", ".join(d.replace("https://", "") for d in WORKER_DOMAINS)
                                await message.channel.send(
                                    f"{message.author.mention} ❌ Unknown domain `{parts[4]}`.\n"
                                    f"Available: `{domain_list}`"
                                )
                                return
                        else:
                            base_domain = next_domain()
                        result = set_slug_config(slug, offer, source)
                        if result is not None:
                            src_display = source if source else "_(not set)_"
                            url = f"{base_domain}/{slug}"
                            await message.channel.send(
                                f"{message.author.mention}\n✅ **Config Updated**\n━━━━━━━━━━━━━━━━━\n"
                                f"**Slug:** `{slug}`\n**Offer:** `{offer}`\n**Source:** `{src_display}`\n"
                                f"**URL:** {url}"
                            )
                        else:
                            await message.channel.send(f"{message.author.mention} ❌ Failed to update config for `{slug}`. Check bot logs.")
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo setlink slug source offer [domain]`\nExample: `@Mexo setlink my-page scale cash dewleaf.shop`")
                    return

                # Handle "getlink" command — read per-slug config from Worker
                elif command == "getlink":
                    if len(parts) >= 2:
                        slug = parts[1]
                        config = get_slug_config(slug)
                        if config:
                            inner = config.get("config", {})
                            offer = inner.get("offer") or "_(not set)_"
                            source = inner.get("source") or "_(not set)_"
                            url = f"{WORKER_URL}/{slug}"
                            await message.channel.send(
                                f"{message.author.mention}\n🔍 **Slug Config**\n━━━━━━━━━━━━━━━━━\n"
                                f"**Slug:** `{slug}`\n**Offer:** `{offer}`\n**Source:** `{source}`\n"
                                f"**URL:** {url}"
                            )
                        else:
                            await message.channel.send(
                                f"{message.author.mention} ℹ️ No config set for `{slug}` — using query params (`?o=` / `?s=`) as fallback."
                            )
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo getlink slug`\nExample: `@Mexo getlink my-page`")
                    return

                # Handle "clearlink" command — remove per-slug config from Worker
                elif command == "clearlink":
                    if len(parts) >= 2:
                        slug = parts[1]
                        ok = clear_slug_config(slug)
                        if ok:
                            await message.channel.send(
                                f"{message.author.mention}\n🗑️ **Config Cleared**\n━━━━━━━━━━━━━━━━━\n"
                                f"Cleared config for `{slug}` — falling back to `?o=` / `?s=` query params."
                            )
                        else:
                            await message.channel.send(f"{message.author.mention} ❌ Failed to clear config for `{slug}`. Check bot logs.")
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo clearlink slug`\nExample: `@Mexo clearlink my-page`")
                    return

                # Handle "bypass" command — disable cloaking for a slug
                elif command == "bypass":
                    if len(parts) >= 2:
                        slug = parts[1]
                        ok = set_bypass(slug)
                        if ok:
                            await message.channel.send(
                                f"{message.author.mention}\n⚡ **Bypass Enabled**\n━━━━━━━━━━━━━━━━━\n"
                                f"Bypass enabled for `{slug}` — all visitors will be redirected, cloaking is OFF"
                            )
                        else:
                            await message.channel.send(f"{message.author.mention} ❌ Failed to enable bypass for `{slug}`. Check bot logs.")
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo bypass slug`\nExample: `@Mexo bypass my-page`")
                    return

                # Handle "unbypass" command — re-enable cloaking for a slug
                elif command == "unbypass":
                    if len(parts) >= 2:
                        slug = parts[1]
                        ok = remove_bypass(slug)
                        if ok:
                            await message.channel.send(
                                f"{message.author.mention}\n🛡️ **Bypass Removed**\n━━━━━━━━━━━━━━━━━\n"
                                f"Bypass removed for `{slug}` — cloaking is back ON"
                            )
                        else:
                            await message.channel.send(f"{message.author.mention} ❌ Failed to remove bypass for `{slug}`. Check bot logs.")
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo unbypass slug`\nExample: `@Mexo unbypass my-page`")
                    return

                # Handle "split" command — register subid fan-out buckets on Worker
                elif command == "split":
                    if len(parts) >= 4:
                        s = parts[1]
                        buckets = parts[2:]
                        data, err = register_split(s, buckets)
                        if data:
                            bucket_display = "  ".join(f"`{b}`" for b in buckets)
                            await message.channel.send(
                                f"{message.author.mention}\n✅ **Split Registered**\n━━━━━━━━━━━━━━━━━\n"
                                f"**Subid:** `{s}`\n**Buckets ({len(buckets)}):** {bucket_display}"
                            )
                        else:
                            await message.channel.send(f"{message.author.mention} ❌ Split failed: {err}")
                    else:
                        await message.channel.send(
                            f"{message.author.mention} ❌ Usage: `@Mexo split <s> <bucket1> <bucket2> [bucket3...]`\n"
                            f"Example: `@Mexo split thumbsUP thumbsUP_a thumbsUP_b`\n"
                            f"_(minimum 2 buckets required)_"
                        )
                    return

                # Handle "splitdel" command — remove a split registration
                elif command == "splitdel":
                    if len(parts) >= 2:
                        s = parts[1]
                        ok, err = delete_split(s)
                        if ok:
                            await message.channel.send(
                                f"{message.author.mention}\n🗑️ **Split Removed**\n━━━━━━━━━━━━━━━━━\n"
                                f"Split for `{s}` deleted — subid will no longer fan out."
                            )
                        else:
                            await message.channel.send(f"{message.author.mention} ❌ splitdel failed: {err}")
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Usage: `@Mexo splitdel <s>`\nExample: `@Mexo splitdel thumbsUP`")
                    return

                # Handle "balance" command — check JAP balance
                elif command == "balance":
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, spidey_request, "GET", "/api/jap/balance", None)
                    if "error" in result:
                        await message.reply(f"❌ Could not fetch balance: {result['error']}", mention_author=True)
                    else:
                        balance = result.get("balance", result)
                        await message.reply(f"💰 **JAP Balance**\n━━━━━━━━━━━━━━━━━\n**{balance}**", mention_author=True)
                    return

            
            # If not a recognized command or valid Shopify link format, show help
            await message.channel.send(
                f"{message.author.mention} ❌ Unknown command. Here's what I can do:\n\n"
                "━━━━━━━━━━━━━━━━━\n"
                "**🛍️ Shopify**\n"
                "`@Mexo shopify slug subid offer` — Generate page link\n"
                "`@Mexo cloak slug source offer [domain]` — Generate cloak link\n"
                "`@Mexo setlink slug source offer [domain]` — Set default source/offer for slug\n"
                "`@Mexo getlink slug` — View current slug config\n"
                "`@Mexo clearlink slug` — Clear slug config\n"
                "`@Mexo bypass slug` — Disable cloaking (redirect all visitors)\n"
                "`@Mexo unbypass slug` — Re-enable cloaking\n"
                "`@Mexo split s bucket1 bucket2 [...]` — Fan subid out to N buckets\n"
                "`@Mexo splitdel s` — Remove a split registration\n"
                "`@Mexo offers` — Show valid offer codes\n"
                "\n**📥 Downloads**\n"
                "`@Mexo tiktok URL1 URL2 ...` — Download TikTok videos\n"
                "`@Mexo instagram URL1 URL2 ...` — Download Instagram Reels\n"
                "`@Mexo postid URL1 URL2 ...` — Get clean TikTok links\n"
                "\n**🚀 Boost**\n"
                "`@Mexo boost URL1 URL2` — Add comments/likes (interactive form)\n"
                "`@Mexo jobs` — View all boost jobs\n"
                "`@Mexo stopjob ID` — Stop a running job\n"
                "`@Mexo lists` — View comment lists\n"
                "`@Mexo balance` — Check JAP balance\n"
                "\n**📊 Revenue**\n"
                "`@Mexo rev` — Today's revenue report\n"
                "`@Mexo rev subid` — Breakdown for a subid\n"
                "\n**🎨 AI**\n"
                "`@Mexo identity` — Generate AI product image\n"
                "`@Mexo random` — Generate random name\n"
                "━━━━━━━━━━━━━━━━━"
            )
    except Exception as e:
        print(f"❌ Error in on_message: {e}")
        print(f"❌ Error details: {type(e).__name__}: {str(e)}")
        try:
            await message.channel.send("❌ Something went wrong. Please try again.")
        except Exception as send_error:
            print(f"❌ Failed to send error message: {send_error}")
            pass

def get_maxconv_clicks():
    if not MAXCONV_API_KEY:
        return {"error": "no_api_key", "rows": []}
    target_date = datetime.now(EST).strftime('%Y-%m-%d')
    try:
        headers = {"X-Api-Key": MAXCONV_API_KEY, "Content-Type": "application/json"}
        payload = {
            "group_by": ["ct1"],
            "metrics": ["uniq_clicks_ip", "uniq_visits_ip", "convs", "revenue"],
            "start_time": f"{target_date} 00:00:00",
            "end_time": f"{target_date} 23:59:59",
            "timezone": "America/New_York",
            "page_size": 500
        }
        resp = requests.post(f"{MAXCONV_API_BASE}/report", json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("suc"):
                rows = data.get("data", [])
                result = []
                total_clicks = 0
                for row in rows:
                    clicks = int(row.get("uniq_clicks_ip", 0))
                    visits = int(row.get("uniq_visits_ip", 0))
                    convs = int(row.get("convs", 0))
                    rev = float(row.get("revenue", 0))
                    source = row.get("ct1") or row.get("subid") or "—"
                    if clicks > 0 or visits > 0:
                        result.append({"source": source, "clicks": clicks, "visits": visits, "convs": convs, "revenue": rev})
                        total_clicks += clicks
                result.sort(key=lambda x: x["clicks"], reverse=True)
                return {"rows": result, "total": total_clicks, "date": target_date, "fetched_at": datetime.now(EST).strftime('%H:%M:%S EST')}
        return {"rows": [], "total": 0, "date": target_date, "fetched_at": datetime.now(EST).strftime('%H:%M:%S EST'), "error": "api_error"}
    except Exception as e:
        return {"rows": [], "total": 0, "error": str(e)}


CLICKS_CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clicks Monitor</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background:#0a0a0a;
  font-family:'Courier New', monospace;
  color:#00ff88;
  height:100vh;
  overflow:hidden;
  display:flex;
  flex-direction:column;
}
.topbar {
  background:#111;
  border-bottom:1px solid #00ff88;
  padding:10px 20px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  flex-shrink:0;
}
.topbar-title { font-size:16px; font-weight:bold; letter-spacing:2px; color:#00ff88; text-shadow:0 0 8px #00ff88; }
.topbar-right { display:flex; align-items:center; gap:20px; font-size:12px; color:#888; }
.live-dot { width:8px; height:8px; background:#00ff88; border-radius:50%; display:inline-block; margin-right:6px; animation:blink 1s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
.summary-bar {
  background:#111;
  padding:8px 20px;
  display:flex;
  gap:30px;
  border-bottom:1px solid #1a1a1a;
  flex-shrink:0;
  font-size:13px;
}
.summary-item span { color:#00ff88; font-weight:bold; font-size:15px; }
.summary-item label { color:#555; margin-left:5px; }
.console-wrap {
  flex:1;
  overflow-y:auto;
  padding:0;
  scrollbar-width:thin;
  scrollbar-color:#00ff88 #0a0a0a;
}
.console-wrap::-webkit-scrollbar { width:8px; }
.console-wrap::-webkit-scrollbar-track { background:#0a0a0a; }
.console-wrap::-webkit-scrollbar-thumb { background:#00ff88; border-radius:4px; }
table {
  width:100%;
  border-collapse:collapse;
  font-size:13px;
}
thead th {
  background:#0d1a12;
  color:#00ff88;
  padding:8px 16px;
  text-align:left;
  font-size:11px;
  letter-spacing:1px;
  text-transform:uppercase;
  border-bottom:1px solid #1a3a25;
  position:sticky;
  top:0;
  z-index:1;
}
tbody tr {
  border-bottom:1px solid #0f1f14;
  transition:background 0.15s;
}
tbody tr:hover { background:#0d1f15; }
tbody tr.highlight { background:#0a2a15; animation:flashrow 0.4s ease; }
@keyframes flashrow { 0%{background:#003319} 100%{background:#0a2a15} }
td { padding:7px 16px; color:#ccc; }
td.src { color:#fff; font-weight:bold; }
td.num { color:#00ff88; font-weight:bold; font-size:14px; text-align:right; }
td.dim { color:#555; text-align:right; }
td.rev { color:#ffcc00; text-align:right; }
.bar-cell { padding:7px 16px; width:140px; }
.bar-bg { background:#1a1a1a; border-radius:2px; height:6px; overflow:hidden; }
.bar-fill { height:100%; background:linear-gradient(90deg,#00ff88,#00cc66); border-radius:2px; transition:width 0.4s ease; }
.rank { color:#333; font-size:11px; text-align:center; padding:7px 10px; }
.no-data { text-align:center; color:#333; padding:60px; font-size:14px; }
.fetch-line {
  font-size:11px;
  color:#1a3a25;
  padding:4px 16px;
  border-top:1px solid #0d1a12;
  background:#090909;
  flex-shrink:0;
}
.fetch-line span { color:#2a5a35; }
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-title">▸ UNIQUE CLICKS — BY SOURCE</div>
  <div class="topbar-right">
    <span id="date-label" style="color:#2a5a35;"></span>
    <span><span class="live-dot"></span>LIVE</span>
    <span id="countdown" style="color:#2a5a35;">next refresh in 5s</span>
  </div>
</div>

<div class="summary-bar">
  <div class="summary-item"><span id="total-clicks">—</span><label>total uniq clicks</label></div>
  <div class="summary-item"><span id="total-sources">—</span><label>sources</label></div>
  <div class="summary-item"><span id="total-convs">—</span><label>convs</label></div>
  <div class="summary-item"><span id="total-rev">—</span><label>revenue</label></div>
</div>

<div class="console-wrap">
  <table>
    <thead>
      <tr>
        <th style="width:36px;">#</th>
        <th>Source</th>
        <th style="text-align:right;">Uniq Clicks</th>
        <th style="text-align:right;">Visits</th>
        <th style="text-align:right;">Convs</th>
        <th style="text-align:right;">Revenue</th>
        <th style="width:140px;">Share</th>
      </tr>
    </thead>
    <tbody id="table-body">
      <tr><td colspan="7" class="no-data">Connecting to MaxConv...</td></tr>
    </tbody>
  </table>
</div>

<div class="fetch-line">Last fetched: <span id="fetch-time">—</span></div>

<script>
let prevClicks = {};
let countdown = 5;
let interval;

function fmt(n) { return n.toLocaleString(); }
function fmtRev(n) { return '$' + n.toFixed(2); }

async function refresh() {
  try {
    const res = await fetch('/api/clicks');
    const data = await res.json();

    if (data.error === 'no_api_key') {
      document.getElementById('table-body').innerHTML =
        '<tr><td colspan="7" class="no-data">⚠ MAXCONV_API_KEY not configured</td></tr>';
      return;
    }

    const rows = data.rows || [];
    const maxClicks = rows.length > 0 ? rows[0].clicks : 1;

    let totalClicks = 0, totalConvs = 0, totalRev = 0;
    rows.forEach(r => { totalClicks += r.clicks; totalConvs += r.convs; totalRev += r.revenue; });

    document.getElementById('total-clicks').textContent = fmt(totalClicks);
    document.getElementById('total-sources').textContent = rows.length;
    document.getElementById('total-convs').textContent = fmt(totalConvs);
    document.getElementById('total-rev').textContent = fmtRev(totalRev);
    document.getElementById('date-label').textContent = data.date || '';
    document.getElementById('fetch-time').textContent = data.fetched_at || '';

    if (rows.length === 0) {
      document.getElementById('table-body').innerHTML =
        '<tr><td colspan="7" class="no-data">No click data yet for today</td></tr>';
      prevClicks = {};
      return;
    }

    let html = '';
    rows.forEach((r, i) => {
      const pct = maxClicks > 0 ? (r.clicks / maxClicks) * 100 : 0;
      const changed = prevClicks[r.source] !== undefined && prevClicks[r.source] !== r.clicks;
      const cls = changed ? 'highlight' : '';
      html += `<tr class="${cls}">
        <td class="rank">${i + 1}</td>
        <td class="src">${r.source}</td>
        <td class="num">${fmt(r.clicks)}</td>
        <td class="dim">${fmt(r.visits)}</td>
        <td class="dim">${fmt(r.convs)}</td>
        <td class="rev">${fmtRev(r.revenue)}</td>
        <td class="bar-cell">
          <div class="bar-bg"><div class="bar-fill" style="width:${pct.toFixed(1)}%"></div></div>
        </td>
      </tr>`;
      prevClicks[r.source] = r.clicks;
    });

    document.getElementById('table-body').innerHTML = html;
  } catch(e) {
    console.error('Fetch error:', e);
  }
}

function startCountdown() {
  clearInterval(interval);
  countdown = 5;
  document.getElementById('countdown').textContent = 'next refresh in 5s';
  interval = setInterval(() => {
    countdown--;
    if (countdown <= 0) {
      document.getElementById('countdown').textContent = 'refreshing...';
      refresh().then(() => {
        countdown = 5;
        document.getElementById('countdown').textContent = 'next refresh in 5s';
      });
    } else {
      document.getElementById('countdown').textContent = `next refresh in ${countdown}s`;
    }
  }, 1000);
}

refresh();
startCountdown();
</script>
</body>
</html>"""


class ShopifyOAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global SHOPIFY_ACCESS_TOKEN
        parsed = urlparse(self.path)
        
        if parsed.path == "/shopify/auth":
            if not SHOPIFY_CLIENT_ID:
                self.send_response(500)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Error: SHOPIFY_CLIENT_ID not set</h1>")
                return
            
            redirect_uri = f"https://{os.environ.get('REPLIT_DEV_DOMAIN', os.environ.get('REPLIT_DOMAINS', 'localhost'))}/shopify/callback"
            scopes = "write_content,read_content"
            nonce = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
            
            auth_url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/oauth/authorize?" + urlencode({
                "client_id": SHOPIFY_CLIENT_ID,
                "scope": scopes,
                "redirect_uri": redirect_uri,
                "state": nonce
            })
            
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            return
        
        elif parsed.path == "/shopify/callback":
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            
            if not code:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Error: No authorization code received</h1>")
                return
            
            token_url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/oauth/access_token"
            token_data = {
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET,
                "code": code
            }
            
            try:
                resp = requests.post(token_url, json=token_data)
                if resp.status_code == 200:
                    access_token = resp.json().get("access_token")
                    SHOPIFY_ACCESS_TOKEN = access_token
                    save_token(access_token)
                    print(f"✅ Successfully obtained Shopify access token via OAuth!")
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>Success! Shopify connected.</h1><p>The bot can now auto-create pages. You can close this window.</p>")
                else:
                    print(f"❌ Token exchange failed: {resp.status_code} - {resp.text}")
                    self.send_response(500)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"<h1>Error exchanging token</h1><p>{resp.text}</p>".encode())
            except Exception as e:
                print(f"❌ OAuth error: {e}")
                self.send_response(500)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<h1>Error: {str(e)}</h1>".encode())
            return
        
        elif parsed.path == "/shopify/status":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            status = "Connected" if SHOPIFY_ACCESS_TOKEN else "Not connected"
            self.wfile.write(f"<h1>Shopify Status: {status}</h1>".encode())
            return

        elif parsed.path == "/api/clicks":
            try:
                data = get_maxconv_clicks()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        elif parsed.path == "/clicks":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(CLICKS_CONSOLE_HTML.encode())
            return

        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Discord Bot Running</h1><p>Visit /shopify/auth to connect Shopify.</p>")
    
    def log_message(self, format, *args):
        pass

def run_discord_bot():
    if TOKEN:
        try:
            client.run(TOKEN)
        except discord.errors.PrivilegedIntentsRequired:
            print("❌ Error: This bot requires the 'Message Content Intent' to be enabled.")
        except discord.errors.LoginFailure:
            print("❌ Error: Invalid bot token or bot is disabled.")
        except Exception as e:
            print(f"❌ Bot startup error: {type(e).__name__}: {str(e)}")
    else:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not found!")

if __name__ == "__main__":
    # Start Discord in background thread so HTTP server can bind immediately
    discord_thread = threading.Thread(target=run_discord_bot, daemon=True)
    discord_thread.start()

    # HTTP server runs in main thread — binds to port right away for Replit detection
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 HTTP server starting on port {port}")
    server = HTTPServer(("0.0.0.0", port), ShopifyOAuthHandler)
    print(f"🌐 HTTP server listening on port {port}")
    server.serve_forever()
