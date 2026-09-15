import os
import requests
import random
from config import JAMENDO_CLIENT_ID, BGM_DIR

def fetch_jamendo_bgm(niche: str = "education") -> str:
    """Mengunduh trek instrumental legal dari Jamendo API dengan filter ketat."""
    os.makedirs(BGM_DIR, exist_ok=True)
    
    tag_map = {
        "finansial": "ambient+minimal",
        "psikologi": "lofi+chill",
        "affiliate": "upbeat+chill",
        "education": "lofi+chill"
    }
    fuzzy_tag = tag_map.get(str(niche).lower(), "lofi+chill")

    if not JAMENDO_CLIENT_ID:
        print("⚠️ JAMENDO_CLIENT_ID belum disetel di .env. Menggunakan folder lokal BGM...")
        existing = [os.path.join(BGM_DIR, f) for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
        return random.choice(existing) if existing else ""

    url = "https://api.jamendo.com/v3.0/tracks/"
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": 15,
        "vocal": "none",
        "fuzzytags": fuzzy_tag,
        "speed": "medium",
        "audioformat": "mp32"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        print(f"🎵 Mencari BGM instrumental Jamendo (Tag: {fuzzy_tag})...")
        res = requests.get(url, params=params, headers=headers, timeout=15)
        if res.status_code == 200:
            tracks = res.json().get("results", [])
            if tracks:
                chosen = random.choice(tracks)
                # Jamendo menyediakan audio stream atau audio_download
                audio_url = chosen.get("audio") or chosen.get("audio_download") or chosen.get("audiodownload")
                track_id = chosen.get("id")
                target_path = os.path.join(BGM_DIR, f"jamendo_{track_id}.mp3")

                # Jika file sudah pernah terunduh dan valid (> 50KB)
                if os.path.exists(target_path) and os.path.getsize(target_path) > 50000:
                    print(f"✅ BGM Jamendo siap dipakai: {os.path.basename(target_path)}")
                    return target_path

                if audio_url:
                    print(f"⬇️ Mengunduh audio BGM Jamendo #{track_id}...")
                    with requests.get(audio_url, headers=headers, stream=True, timeout=30) as stream_res:
                        if stream_res.status_code == 200:
                            with open(target_path, "wb") as f:
                                for chunk in stream_res.iter_content(chunk_size=1024 * 64):
                                    if chunk:
                                        f.write(chunk)

                            if os.path.exists(target_path) and os.path.getsize(target_path) > 50000:
                                print(f"✅ Unduh BGM berhasil ({os.path.basename(target_path)})")
                                return target_path
                            else:
                                if os.path.exists(target_path):
                                    os.remove(target_path)
    except Exception as e:
        print(f"⚠️ Gagal mendapatkan BGM dari Jamendo: {e}")

    # Fallback jika Jamendo gagal/offline: pakai file mp3 yang ada di assets/bgm
    existing = [os.path.join(BGM_DIR, f) for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
    if existing:
        fallback_file = random.choice(existing)
        print(f"ℹ️ Menggunakan fallback BGM lokal: {os.path.basename(fallback_file)}")
        return fallback_file

    print("⚠️ Peringatan: Tidak ada BGM Jamendo ataupun berkas MP3 di assets/bgm!")
    return ""