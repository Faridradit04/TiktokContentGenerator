import os
import requests
import random
from config import JAMENDO_CLIENT_ID, BGM_DIR

def fetch_jamendo_bgm(niche: str = "education") -> str:
    """Mengunduh trek instrumental legal dari Jamendo API berdasarkan parameter filter."""
    os.makedirs(BGM_DIR, exist_ok=True)
    
    # Tag suasana disesuaikan dengan niche konten
    tag_map = {
        "finansial": "ambient+minimal",
        "psikologi": "lofi+chill",
        "affiliate": "upbeat+chill",
        "education": "lofi+chill"
    }
    fuzzy_tag = tag_map.get(niche.lower(), "lofi+chill")

    if not JAMENDO_CLIENT_ID:
        # Fallback: gunakan file lokal yang ada di assets/bgm jika client_id belum disetel
        existing = [os.path.join(BGM_DIR, f) for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
        return random.choice(existing) if existing else ""

    url = "https://api.jamendo.com/v3.0/tracks/"
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": 10,
        "vocal": "none",              # Wajib instrumental murni
        "fuzzytags": fuzzy_tag,       # Suasana lofi/ambient
        "speed": "medium",            # Tempo sedang/santai
        "audioformat": "mp32"
    }

    try:
        res = requests.get(url, params=params, timeout=15)
        if res.status_code == 200:
            tracks = res.json().get("results", [])
            if tracks:
                chosen = random.choice(tracks)
                audio_url = chosen.get("audio")
                track_id = chosen.get("id")
                target_path = os.path.join(BGM_DIR, f"jamendo_{track_id}.mp3")

                if os.path.exists(target_path):
                    return target_path

                with requests.get(audio_url, stream=True, timeout=30) as stream_res:
                    if stream_res.status_code == 200:
                        with open(target_path, "wb") as f:
                            for chunk in stream_res.iter_content(chunk_size=1024 * 64):
                                if chunk:
                                    f.write(chunk)
                        return target_path
    except Exception as e:
        print(f"⚠️ Gagal mengunduh Jamendo BGM: {e}")

    existing = [os.path.join(BGM_DIR, f) for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
    return random.choice(existing) if existing else ""