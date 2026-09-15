import os
import time
import requests
from config import PEXELS_API_KEY

def search_pexels_video_candidates(keywords: list[str]) -> list[str]:
    """Mencari video di Pexels dan mengembalikan daftar link video MP4 sebagai kandidat unduhan."""
    if not PEXELS_API_KEY:
        return []

    headers = {
        "Authorization": PEXELS_API_KEY,
        "User-Agent": "TikTokAutoGenerator/1.0"
    }
    candidate_links = []

    for kw in keywords:
        try:
            url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(kw)}&per_page=5&orientation=portrait"
            res = requests.get(url, headers=headers, timeout=(10, 20))
            if res.status_code == 200:
                data = res.json()
                videos = data.get("videos", [])
                for vid in videos:
                    files = vid.get("video_files", [])
                    # Urutkan berdasarkan lebar piksel tertinggi
                    sorted_files = sorted(files, key=lambda x: x.get("width", 0), reverse=True)
                    for f in sorted_files:
                        link = f.get("link")
                        if link and f.get("file_type") == "video/mp4" and link not in candidate_links:
                            candidate_links.append(link)
                if candidate_links:
                    return candidate_links
        except Exception as e:
            print(f"⚠️ Pencarian keyword '{kw}' gagal atau timeout: {e}")
            continue
    return candidate_links

def download_video_file_with_retry(urls: list[str], output_path: str, max_retries: int = 3) -> str:
    """Mengunduh video MP4 dengan stream chunk, timeout adaptif, dan fallback ke kandidat lain."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for url in urls:
        for attempt in range(1, max_retries + 1):
            try:
                # timeout=(connection_timeout, read_timeout)
                with requests.get(url, headers=headers, stream=True, timeout=(15, 90)) as res:
                    if res.status_code == 200:
                        with open(output_path, "wb") as f:
                            for chunk in res.iter_content(chunk_size=1024 * 512):
                                if chunk:
                                    f.write(chunk)
                        
                        # Validasi ukuran file bukan 0 byte
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 10240:
                            return output_path
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                print(f"⏳ Unduhan timeout (Percobaan {attempt}/{max_retries}) untuk link CDN: {e}")
                time.sleep(2)
            except Exception as e:
                print(f"⚠️ Galat unduhan (Percobaan {attempt}/{max_retries}): {e}")
                time.sleep(2)

            # Bersihkan file rusak jika unduhan putus di tengah jalan
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass

    raise RuntimeError(f"Gagal mengunduh berkas video dari Pexels setelah mencoba seluruh kandidat.")

def fetch_broll_clips(scenes: list, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    for idx, scene in enumerate(scenes):
        s_id = scene.get("scene_id", idx + 1)

        # Jika adegan menggunakan aset produk lokal atau file sudah ada, lewati
        if scene.get("video_path") and os.path.exists(scene["video_path"]):
            continue

        keywords = scene.get("stock_keywords", [])
        if not keywords and scene.get("stock_keyword"):
            keywords = [scene["stock_keyword"]]

        print(f"🎬 Mencari klip adegan {s_id} (Keywords: {keywords[:2]})...")
        candidates = search_pexels_video_candidates(keywords)
        
        target_file = os.path.join(output_dir, f"clip_scene_{s_id}_{idx}.mp4")

        if not candidates:
            print(f"⚠️ Klip spesifik tidak ditemukan untuk adegan {s_id}, beralih ke keyword umum...")
            candidates = search_pexels_video_candidates(["lifestyle portrait", "happy person", "urban people", "technology mobile"])

        if candidates:
            try:
                download_video_file_with_retry(candidates, target_file)
                scene["video_path"] = target_file
            except Exception as e:
                print(f"⚠️ Gagal mendapatkan klip adegan {s_id}: {e}")
        else:
            print(f"❌ Tidak ada kandidat klip video yang ditemukan untuk adegan {s_id}.")

    return scenes