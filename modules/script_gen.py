import os
import re
import time
from typing import Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from modules.db_manager import get_recent_topics, save_topic

class Scene(BaseModel):
    scene_id: int
    role: str = Field(description="hook, step_1, step_2, step_3, step_4, step_5, atau cta")
    voiceover_text: str = Field(
        description="Narasi bahasa Indonesia santai, padat, dan to-the-point. Wajib eja angka secara kata penuh (contoh: 'sepuluh juta rupiah', bukan '10jt'). Hindari sapaan 'halo guys'. Kalimat pendek dengan tanda koma teratur."
    )
    visual_prompt: str = Field(description="Deskripsi visual adegan aksi nyata 9:16")
    stock_keywords: list[str] = Field(
        description="Daftar 3-5 variasi keyword bahasa Inggris yang sinkron dengan judul konten dan aksi manusia nyata (contoh: ['worried man checking phone screen', 'counting cash money rupiah', 'typing laptop night'])."
    )
    text_overlay: str = Field(
        description="Punchline teks kapital maksimal 3-4 kata (contoh: '1. STOP PINJOL', '2. AUTO DEBET')"
    )

class VideoMetadata(BaseModel):
    tiktok_caption: str = Field(description="Caption TikTok menarik yang memicu rasa penasaran")
    hashtags: list[str] = Field(description="5 hashtag relevan")
    source_topic: str = Field(description="Isu atau judul inti topik")
    cover_headline: str = Field(description="Headline cover thumbnail provokatif (maksimal 5 kata kapital)")

class VideoProject(BaseModel):
    project_title: str
    metadata: VideoMetadata
    scenes: list[Scene]

class TopicItem(BaseModel):
    niche: str = Field(description="Niche bahasan (contoh: Finansial, Karir, Psikologi, AI & Tools, Bisnis)")
    title: str = Field(description="Judul konten TikTok yang sangat menarik dan viral")

class BulkTopics(BaseModel):
    topics: list[TopicItem]

def _clean_json_string(raw_text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()

def _research_topic_with_fallback(client: genai.Client, model: str, prompt: str) -> str:
    """
    Mencoba riset via Google Search Grounding terlebih dahulu.
    Jika error / kuota habis, otomatis fallback ke internal knowledge Gemini.
    """
    # 1. Coba via Google Search Grounding
    try:
        print("🌐 Mencoba riset via Google Search Grounding...")
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                system_instruction="Anda adalah periset tren terpercaya di Indonesia."
            )
        )
        text_res = getattr(response, "text", "")
        if text_res and text_res.strip():
            print("✅ Berhasil mendapatkan referensi via Search Grounding.")
            return text_res
    except Exception as e:
        print(f"⚠️ Search Grounding tidak tersedia ({e}). Mengalihkan ke riset internal Gemini...")

    # 2. Fallback: Gunakan kemampuan internal Gemini tanpa tools eksternal
    try:
        print("🧠 Menjalankan riset berbasis basis pengetahuan internal Gemini...")
        fallback_prompt = (
            f"Berdasarkan pemahaman dan pengetahuan mendalam Anda:\n"
            f"{prompt}\n\n"
            f"Berikan fakta, analogi praktis, data realistis, dan langkah konkret untuk audiens Indonesia."
        )
        response = client.models.generate_content(
            model=model,
            contents=fallback_prompt,
            config=types.GenerateContentConfig(
                system_instruction="Anda adalah periset tren dan edukator finansial/konten Indonesia yang berwawasan luas."
            )
        )
        fallback_text = getattr(response, "text", "")
        if fallback_text and fallback_text.strip():
            print("✅ Riset internal Gemini selesai digunakan.")
            return fallback_text
    except Exception as e:
        print(f"⚠️ Gagal melakukan riset internal: {e}")

    return "Berikan panduan edukasi aplikatif, angka realistis, dan langkah terstruktur yang relevan untuk audiens Indonesia."

def generate_trending_script(niche: str, specific_title: Optional[str] = None) -> VideoProject:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY belum disetel di .env.")

    client = genai.Client(api_key=api_key)
    TARGET_MODEL = "gemini-2.5-flash"

    past_topics = get_recent_topics(niche)
    blacklist_instruction = ""
    if past_topics:
        past_list_str = "\n- ".join(past_topics)
        blacklist_instruction = f"\nJANGAN MEMBUAT TOPIK YANG SAMA ATAU MIRIP DENGAN DAFTAR INI:\n- {past_list_str}\n"

    if specific_title and specific_title.strip():
        fokus_bahasan = f"Niche: '{niche}', Topik: '{specific_title.strip()}'"
        research_prompt = f"Cari panduan praktis dan angka nyata seputar: '{specific_title}' di niche {niche} Indonesia. Maksimal 200 kata.{blacklist_instruction}"
    else:
        fokus_bahasan = f"Niche: '{niche}'"
        research_prompt = f"Cari 1 masalah atau tren viral ekonomi/finansial terbaru seputar {niche} di Indonesia. Maksimal 200 kata.{blacklist_instruction}"

    print(f"🔍 [1/2] Menelusuri informasi ({fokus_bahasan})...")
    researched_info = _research_topic_with_fallback(client, TARGET_MODEL, research_prompt)

    time.sleep(1)

    print("📝 [2/2] Merumuskan naskah JSON dan adegan...")
    formatting_prompt = f"""
    Referensi Riset:
    {researched_info[:1500]}

    Target Konten:
    - Niche: {niche}
    - Judul Fokus: {specific_title if specific_title else 'Topik Baru Bebas Duplikasi'}
    {blacklist_instruction}

    TUGAS:
    Susun naskah video TikTok dengan durasi MINIMAL 60 DETIK (6-7 adegan).
    1. HOOK (Scene 1): Menusuk masalah nyata tanpa sapaan 'halo guys'.
    2. ISI (Scene 2 s/d 5): 25-35 kata narasi per adegan berisi langkah konkret.
    3. CTA (Scene Terakhir): Pertanyaan pemantik debat di kolom komentar.
    4. KEYWORDS PEXELS: Pada setiap adegan, berikan 3-5 keyword bahasa Inggris yang sinkron dengan judul konten ({specific_title or niche}) dan berupa aksi manusia nyata.
    5. ANGKA: Eja semua nominal angka penuh ('lima ratus ribu rupiah').
    """

    response = client.models.generate_content(
        model=TARGET_MODEL,
        contents=formatting_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoProject,
            max_output_tokens=4000,
            temperature=0.7,
            system_instruction="Anda adalah sutradara video pendek TikTok profesional. Hasilkan HANYA JSON valid."
        )
    )

    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        proj = parsed_obj if isinstance(parsed_obj, VideoProject) else VideoProject.model_validate(parsed_obj)
    else:
        raw_text = getattr(response, "text", None)
        proj = VideoProject.model_validate_json(_clean_json_string(raw_text))

    save_topic("education", niche, proj.metadata.source_topic)
    return proj

def generate_10_bulk_topics() -> list[TopicItem]:
    """Menghasilkan 10 ide topik acak lintas niche yang sedang tren dan anti-duplikasi."""
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    TARGET_MODEL = "gemini-2.5-flash"

    past_topics = get_recent_topics("all", limit=40)
    blacklist = "\n- ".join(past_topics) if past_topics else "Belum ada"

    prompt = f"""
    Riset 10 topik video TikTok edukasi/informasi yang sangat berpotensi FYP di Indonesia saat ini.
    Kombinasikan dari beragam niche populer: Finansial Pribadi, Psikologi & Mindset, Tips Karir/Kerja, AI & Tools Produktivitas, dan Bisnis/Side Hustle.
    
    DAFTAR TOPIK YANG SUDAH PERNAH DIBUAT (DILARANG MENGULANG):
    - {blacklist}

    Hasilkan tepat 10 judul yang memicu rasa penasaran, relevan dengan kehidupan anak muda Indonesia, dan praktis.
    """

    response = client.models.generate_content(
        model=TARGET_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BulkTopics,
            temperature=0.8,
            system_instruction="Anda adalah creative director media sosial nomor satu."
        )
    )

    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        data = parsed_obj if isinstance(parsed_obj, BulkTopics) else BulkTopics.model_validate(parsed_obj)
    else:
        data = BulkTopics.model_validate_json(_clean_json_string(getattr(response, "text", "{}")))

    return data.topics[:10]