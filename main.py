import sys
import argparse
import asyncio
from datetime import datetime

from config import (
    AUDIO_DIR,
    RAW_CLIPS_DIR,
    OUTPUT_DIR,
    GDRIVE_FOLDER_ID,
    slugify_filename
)
from modules.script_gen import generate_trending_script
from modules.audio_engine import process_json_to_audio
from modules.visual_fetcher import fetch_broll_clips
from modules.video_assembler import render_full_tiktok, generate_video_cover
from modules.drive_uploader import upload_file_to_drive, save_metadata_file

async def run_pipeline(niche: str, title: str = None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n================ START PIPELINE [{timestamp}] ================")
    print(f"🎯 Target Niche : {niche}")
    print(f"📌 Judul Fokus  : {title if title else '(Otomatis cari tren via Google)'}")

    # 1. Riset & Naskah
    print("\n[Langkah 1/5] Meriset topik & menyusun naskah via Gemini...")
    script_data = generate_trending_script(niche=niche, specific_title=title)
    print(f"✅ Topik Terpilih : {script_data.metadata.source_topic}")
    print(f"✅ Cover Headline : {script_data.metadata.cover_headline}")

    file_slug = slugify_filename(script_data.metadata.source_topic)
    if not file_slug or len(file_slug) < 3:
        file_slug = f"konten_{timestamp}"

    # 2. Audio Voiceover
    print("\n[Langkah 2/5] Memproses audio voiceover (Edge-TTS)...")
    scenes_with_audio = await process_json_to_audio(script_data.model_dump(), str(AUDIO_DIR))

    # 3. Visual Pexels
    print("\n[Langkah 3/5] Mengunduh aset visual klip dari Pexels...")
    scenes_ready = fetch_broll_clips(scenes_with_audio, str(RAW_CLIPS_DIR))

    # 4. Render Video & Cover Thumbnail
    output_video_path = OUTPUT_DIR / f"{file_slug}.mp4"
    output_cover_path = OUTPUT_DIR / f"{file_slug}_cover.jpg"
    output_metadata_path = OUTPUT_DIR / f"{file_slug}_metadata.txt"

    print(f"\n[Langkah 4/5] Merender video 9:16 & cover thumbnail ({output_video_path.name})...")
    render_full_tiktok(scenes_ready, output_filename=str(output_video_path))

    first_clip_path = scenes_ready[0].get("video_path")
    if first_clip_path:
        generate_video_cover(
            first_video_path=first_clip_path,
            headline_text=script_data.metadata.cover_headline,
            output_path=str(output_cover_path)
        )

    # 5. Metadata & Upload Drive
    print("\n[Langkah 5/5] Menyimpan metadata & mengunggah ke Google Drive...")
    metadata_path = save_metadata_file(script_data.metadata, str(output_metadata_path))

    if GDRIVE_FOLDER_ID:
        clean_folder_id = GDRIVE_FOLDER_ID.split("?")[0].strip()
        print(f"☁️ Mengunggah video ke Drive...")
        video_id = upload_file_to_drive(str(output_video_path), clean_folder_id)

        if output_cover_path.exists():
            print(f"☁️ Mengunggah cover thumbnail ke Drive...")
            upload_file_to_drive(str(output_cover_path), clean_folder_id)

        print(f"☁️ Mengunggah caption metadata ke Drive...")
        upload_file_to_drive(str(metadata_path), clean_folder_id)
        print(f"✅ Seluruh berkas berhasil masuk Drive (ID: {video_id})")
    else:
        print("⚠️ GDRIVE_FOLDER_ID belum disetel di .env. Berkas tersimpan lokal di assets/output.")

    print(f"\n================ PIPELINE SELESAI ================")
    print(f"📹 Video    : {output_video_path}")
    print(f"🖼️ Cover    : {output_cover_path}")
    print(f"📝 Metadata : {output_metadata_path}\n")

def parse_args():
    parser = argparse.ArgumentParser(description="TikTok Content Auto Generator")
    parser.add_argument("--niche", type=str, help="Kategori / Niche konten")
    parser.add_argument("--title", type=str, default=None, help="Judul atau topik spesifik konten")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    niche_input = args.niche
    title_input = args.title

    if not niche_input:
        print("\n=== PENGATURAN KONTEN BARU ===")
        niche_input = input("👉 Masukkan Niche (contoh: Finansial, Kuliner, AI Tools): ").strip()
        while not niche_input:
            niche_input = input("⚠️ Niche wajib diisi: ").strip()

        title_input = input("👉 Masukkan Judul/Topik (Tekan Enter jika ingin otomatis cari tren): ").strip()
        if not title_input:
            title_input = None

    asyncio.run(run_pipeline(niche=niche_input, title=title_input))