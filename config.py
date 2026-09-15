import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

ASSETS_DIR = BASE_DIR / "assets"
AUDIO_DIR = ASSETS_DIR / "audio"
RAW_CLIPS_DIR = ASSETS_DIR / "raw_clips"
OUTPUT_DIR = ASSETS_DIR / "output"
BGM_DIR = ASSETS_DIR / "bgm"
UPLOADS_DIR = ASSETS_DIR / "uploads"
DB_PATH = ASSETS_DIR / "history.db"

for directory in [ASSETS_DIR, AUDIO_DIR, RAW_CLIPS_DIR, OUTPUT_DIR, BGM_DIR, UPLOADS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Membaca format multi-key koma atau fallback ke format single key lama
raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY") or ""
GEMINI_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_TELEGRAM_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID")
JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID", "")
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

def slugify_filename(text: str, max_length: int = 50) -> str:
    if not text:
        return "konten"
    clean = re.sub(r'[\\/*?:"<>|.,!@#$%^&()+=]', "", text)
    clean = re.sub(r"[\s\-_]+", "_", clean).strip("_")
    return clean[:max_length].lower()