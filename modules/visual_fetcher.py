import os
import requests
from config import PEXELS_API_KEY

def search_pexels_video(keywords: list[str]) -> str:
    """Mencari video di Pexels berdasarkan daftar variasi keyword."""
    if not PEXELS_API_KEY:
        return ""

    headers = {"Authorization": PEXELS_API_KEY}
    for kw in keywords:
        try:
            url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(kw)}&per_page=5&orientation=portrait"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                videos = data.get("videos", [])
                for vid in videos:
                    files = vid.get("video_files", [])
                    # Prioritaskan HD portrait
                    for f in sorted(files, key=lambda x: x.get("width", 0), reverse=True):
                        if f.get("link") and f.get("file_type") == "video/mp4":
                            return f["link"]
        except Exception:
            continue
    return ""

def download_video_file(url: str, output_path: str) -> str:
    res = requests.get(url, stream=True, timeout=30)
    if res.status_code == 200:
        with open(output_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        return output_path
    raise RuntimeError(f"Gagal mengunduh video dari Pexels (HTTP {res.status_code})")

def fetch_broll_clips(scenes: list, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    for idx, scene in enumerate(scenes):
        s_id = scene["scene_id"]
        # Jika adegan menggunakan aset produk lokal, lewati unduhan Pexels
        if scene.get("video_path") and os.path.exists(scene["video_path"]):
            continue

        keywords = scene.get("stock_keywords", [])
        if not keywords and scene.get("stock_keyword"):
            keywords = [scene["stock_keyword"]]

        print(f"🎬 Mencari klip adegan {s_id} (Keywords: {keywords[:2]})...")
        video_url = search_pexels_video(keywords)
        
        target_file = os.path.join(output_dir, f"clip_scene_{s_id}_{idx}.mp4")
        if video_url:
            download_video_file(video_url, target_file)
            scene["video_path"] = target_file
        else:
            print(f"⚠️ Klip tidak ditemukan untuk adegan {s_id}, mencoba keyword umum...")
            fallback_url = search_pexels_video(["lifestyle portrait", "happy person", "urban people"])
            if fallback_url:
                download_video_file(fallback_url, target_file)
                scene["video_path"] = target_file
    return scenes