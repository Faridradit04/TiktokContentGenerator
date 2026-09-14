import re
import time
from typing import Optional, Callable, Any
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config import GEMINI_API_KEYS
from modules.db_manager import get_recent_topics, save_topic

TARGET_MODEL = "gemini-2.5-flash"

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

def _execute_with_key_rotation(operation: Callable[[genai.Client], Any]) -> Any:
    """Mengeksekusi operasi API Gemini dengan rotasi kunci otomatis jika menemui limit (429)."""
    if not GEMINI_API_KEYS:
        raise RuntimeError("Variabel GEMINI_API_KEYS belum disetel di file .env.")

    last_error = None
    for idx, key in enumerate(GEMINI_API_KEYS):
        try:
            client = genai.Client(api_key=key)
            return operation(client)
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                print(f"⚠️ Kunci Akun #{idx + 1} terkena kuota limit. Beralih ke akun berikutnya...")
                last_error = e
                time.sleep(1)
                continue
            raise e

    raise RuntimeError(f"Semua kuota API Key Gemini telah habis atau tidak dapat diakses: {last_error}")

def _research_topic_with_fallback(prompt: str) -> str:
    """Riset tren via Search Grounding dengan rotasi akun, fallback ke riset internal jika gagal."""
    # 1. Coba Search Grounding
    def _run_grounding(client: genai.Client):
        return client.models.generate_content(
            model=TARGET_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                system_instruction="Anda adalah periset tren terpercaya di Indonesia."
            )
        )

    try:
        print("🌐 Melakukan riset via Google Search Grounding...")
        res = _execute_with_key_rotation(_run_grounding)
        text_val = getattr(res, "text", "")
        if text_val and text_val.strip():
            print("✅ Data tren Search Grounding berhasil didapatkan.")
            return text_val
    except Exception as e:
        print(f"⚠️ Search Grounding dilewati ({e}). Mengalihkan ke riset internal Gemini...")

    # 2. Fallback: Riset Internal
    def _run_internal(client: genai.Client):
        fallback_prompt = (
            f"Berdasarkan wawasan mendalam Anda:\n{prompt}\n\n"
            f"Berikan fakta konkret, data realistis, dan langkah terstruktur untuk audiens Indonesia."
        )
        return client.models.generate_content(
            model=TARGET_MODEL,
            contents=fallback_prompt,
            config=types.GenerateContentConfig(
                system_instruction="Anda adalah periset tren dan edukator konten Indonesia yang berwawasan luas."
            )
        )

    try:
        print("🧠 Menjalankan riset berbasis basis pengetahuan internal Gemini...")
        res_internal = _execute_with_key_rotation(_run_internal)
        text_fallback = getattr(res_internal, "text", "")
        if text_fallback and text_fallback.strip():
            print("✅ Riset internal Gemini selesai.")
            return text_fallback
    except Exception as e:
        print(f"⚠️ Riset internal gagal: {e}")

    return "Berikan panduan edukasi aplikatif, data realistis, dan langkah terstruktur yang relevan untuk audiens Indonesia."

def generate_trending_script(niche: str, specific_title: Optional[str] = None) -> VideoProject:
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
    researched_info = _research_topic_with_fallback(research_prompt)

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

    def _generate_json(client: genai.Client):
        return client.models.generate_content(
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

    response = _execute_with_key_rotation(_generate_json)

    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        proj = parsed_obj if isinstance(parsed_obj, VideoProject) else VideoProject.model_validate(parsed_obj)
    else:
        raw_text = getattr(response, "text", None)
        proj = VideoProject.model_validate_json(_clean_json_string(raw_text))

    save_topic("education", niche, proj.metadata.source_topic)
    return proj

def generate_10_bulk_topics() -> list[TopicItem]:
    past_topics = get_recent_topics("all", limit=40)
    blacklist = "\n- ".join(past_topics) if past_topics else "Belum ada"

    prompt = f"""
    Riset 10 topik video TikTok edukasi/informasi yang sangat berpotensi FYP di Indonesia saat ini.
    Kombinasikan dari beragam niche populer: Finansial Pribadi, Psikologi & Mindset, Tips Karir/Kerja, AI & Tools Produktivitas, dan Bisnis/Side Hustle.
    
    DAFTAR TOPIK YANG SUDAH PERNAH DIBUAT (DILARANG MENGULANG):
    - {blacklist}

    Hasilkan tepat 10 judul yang memicu rasa penasaran, relevan dengan kehidupan anak muda Indonesia, dan praktis.
    """

    def _call_bulk(client: genai.Client):
        return client.models.generate_content(
            model=TARGET_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BulkTopics,
                temperature=0.8,
                system_instruction="Anda adalah creative director media sosial nomor satu."
            )
        )

    response = _execute_with_key_rotation(_call_bulk)

    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        data = parsed_obj if isinstance(parsed_obj, BulkTopics) else BulkTopics.model_validate(parsed_obj)
    else:
        data = BulkTopics.model_validate_json(_clean_json_string(getattr(response, "text", "{}")))

    return data.topics[:10]