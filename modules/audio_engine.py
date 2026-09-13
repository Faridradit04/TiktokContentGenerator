import os
import re
import asyncio
from edge_tts import Communicate
from mutagen.mp3 import MP3

def clean_voiceover_text(raw_text: str) -> str:
    """Membersihkan simbol formatting sebelum diproses ke Edge-TTS."""
    text = re.sub(r"[\(\[].*?[\)\]]", "", raw_text)
    text = re.sub(r"[#*_~`]", "", text)
    return " ".join(text.split()).strip()

async def generate_single_audio(
    text: str,
    output_path: str,
    voice: str = "id-ID-ArdiNeural",
    rate: str = "+12%",
    pitch: str = "+0Hz"
):
    """Sintesis teks menjadi file MP3 artikulasi alami."""
    cleaned = clean_voiceover_text(text)
    communicate = Communicate(text=cleaned, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)

def get_audio_duration(file_path: str) -> float:
    audio = MP3(file_path)
    return round(audio.info.length, 2)

async def process_json_to_audio(project_dict: dict, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    processed_scenes = []

    print("🎙️ Memulai pembuatan suara narasi (Edge-TTS)...")
    for scene in project_dict.get("scenes", []):
        s_id = scene["scene_id"]
        raw_text = scene["voiceover_text"]
        out_file = os.path.join(output_dir, f"scene_{s_id}.mp3")

        await generate_single_audio(raw_text, out_file)
        duration = get_audio_duration(out_file)

        scene_data = scene.copy()
        scene_data["audio_path"] = out_file
        scene_data["duration_seconds"] = duration
        processed_scenes.append(scene_data)

        print(f"  -> Scene {s_id} selesai ({duration}s)")

    return processed_scenes