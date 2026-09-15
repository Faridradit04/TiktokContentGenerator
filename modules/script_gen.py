import re
import time
import random
from typing import Optional, Callable, Any
import feedparser
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from config import GEMINI_API_KEYS
from modules.db_manager import get_recent_topics, save_topic

PRIMARY_MODEL = "gemini-3-flash"
FALLBACK_MODEL = "gemini-3.6-flash"

# Kerangka sudut pandang kreatif non-klise
CONTENT_ANGLES = [
    {
        "type": "STUDI_KASUS_BISNIS_SKANDAL",
        "instruction": "Bedah 1 strategi brilian, kegagalan fatal, atau skandal rahasia dari sebuah perusahaan/tokoh terkenal dunia atau Indonesia. Jangan berikan tips umum, fokus pada kronologi peristiwa dan keputusan fatalnya."
    },
    {
        "type": "PARADOKS_PSIKOLOGI_PERILAKU",
        "instruction": "Bongkar 1 bias kognitif atau eksperimen psikologi nyata yang menjelaskan mengapa manusia sering mengambil keputusan bodoh tanpa sadar. Mulai dengan fenomena aneh sehari-hari."
    },
    {
        "type": "FAKTA_GELAP_SEJARAH",
        "instruction": "Angkat 1 peristiwa sejarah langka, manipulasi pasar, atau eksperimen sosial masa lalu yang jarang diketahui publik namun berdampak besar ke kehidupan modern."
    },
    {
        "type": "SIMULASI_EXTREME_SCENARIO",
        "instruction": "Lakukan simulasi 'Bagaimana jika...?' skenario ekstrem (misal: apa jadinya jika perbankan tumbang serentak, atau jika sebuah regulasi mendadak diubah). Jelaskan rantai efek domino yang terjadi secara realistis."
    },
    {
        "type": "MITOS_VS_FAKTA_KONTROVERSIAL",
        "instruction": "Tabrakkan dan hancurkan 1 mitos umum yang dipercaya 90 persen orang dengan data dan fakta mengejutkan yang berlawanan. Gunakan argumen berani dan to-the-point."
    }
]

class Scene(BaseModel):
    scene_id: int
    role: str = Field(description="hook, kronologi_1, kronologi_2, klimaks, plot_twist, pesan_inti, cta")
    voiceover_text: str = Field(
        description="Narasi bahasa Indonesia bergaya dokumenter/storytelling cepat. Jangan ada sapaan 'halo guys' atau 'tahukah kamu'. Eja angka secara kata penuh ('dua puluh lima persen'). Padat, memicu penasaran."
    )
    visual_prompt: str = Field(description="Deskripsi visual aksi nyata vertikal 9:16")
    stock_keywords: list[str] = Field(
        description="3-5 keyword aksi Pexels bahasa Inggris yang relevan dengan jalan cerita adegan ini."
    )
    text_overlay: str = Field(description="Headline teks kapital provokatif maksimal 3-4 kata.")

class VideoMetadata(BaseModel):
    tiktok_caption: str = Field(description="Caption TikTok misterius/memicu debat dengan hashtag relevan")
    hashtags: list[str] = Field(description="5 hashtag tren")
    source_topic: str = Field(description="Judul cerita/peristiwa inti")
    cover_headline: str = Field(description="Headline thumbnail kontroversial maksimal 5 kata kapital")

class VideoProject(BaseModel):
    project_title: str
    metadata: VideoMetadata
    scenes: list[Scene]

class TopicItem(BaseModel):
    niche: str = Field(description="Kategori bahasan")
    title: str = Field(description="Judul cerita/konsep konten yang menggugah rasa penasaran")

class BulkTopics(BaseModel):
    topics: list[TopicItem]

def _clean_json_string(raw_text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()

def _get_google_trends_headlines() -> list[str]:
    """Mengambil 5 berita tren terhangat hari ini via Google Trends RSS Indonesia."""
    try:
        feed = feedparser.parse("https://trends.google.com/trending/rss?geo=ID")
        headlines = [entry.title for entry in feed.entries[:5]]
        return headlines
    except Exception as e:
        print(f"⚠️ RSS Google Trends dilewati: {e}")
        return []

def _execute_with_key_rotation(operation: Callable[[genai.Client, str], Any]) -> Any:
    if not GEMINI_API_KEYS:
        raise RuntimeError("Variabel GEMINI_API_KEYS belum disetel di file .env.")

    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL, "gemini-2.5-flash"]
    last_error = None

    for model_name in models_to_try:
        for idx, key in enumerate(GEMINI_API_KEYS):
            client = genai.Client(api_key=key)
            for attempt in range(1, 4):
                try:
                    return operation(client, model_name)
                except Exception as e:
                    err_msg = str(e)
                    last_error = e

                    if "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower():
                        sleep_time = attempt * 3
                        print(f"⏳ Server Gemini sibuk (503) pada model {model_name}. Menunggu {sleep_time} detik...")
                        time.sleep(sleep_time)
                        continue

                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                        print(f"⚠️ Akun Gemini #{idx + 1} limit (429). Pindah akun...")
                        time.sleep(1)
                        break

                    if "404" in err_msg or "NOT_FOUND" in err_msg:
                        print(f"⚠️ Model {model_name} tidak ditemukan (404). Beralih ke model berikutnya...")
                        break

                    print(f"⚠️ Kesalahan API ({model_name}): {err_msg}")
                    break

    raise RuntimeError(f"Semua kuota atau percobaan model Gemini gagal: {last_error}")

def _research_topic_with_fallback(prompt: str) -> str:
    """Riset komprehensif via Search Grounding dengan fallback internal."""
    def _run_grounding(client: genai.Client, model_name: str):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                system_instruction="Anda adalah jurnalis investigasi dan kurator cerita viral yang mengutamakan data konkret."
            )
        )

    try:
        print("🌐 Meriset materi faktual via Google Search Grounding...")
        res = _execute_with_key_rotation(_run_grounding)
        text_val = getattr(res, "text", "")
        if text_val and text_val.strip():
            print("✅ Data riset berhasil ditemukan.")
            return text_val
    except Exception as e:
        print(f"⚠️ Search Grounding dilewati ({e}). Mengalihkan ke riset internal...")

    def _run_internal(client: genai.Client, model_name: str):
        fallback_prompt = (
            f"Berdasarkan wawasan investigatif mendalam Anda:\n{prompt}\n\n"
            f"Berikan fakta konkret peristiwa, nama entitas, tahun kejadian, dan alur sebab-akibat."
        )
        return client.models.generate_content(
            model=model_name,
            contents=fallback_prompt,
            config=types.GenerateContentConfig(
                system_instruction="Anda adalah periset storytelling dan sutradara video pendek."
            )
        )

    try:
        res_internal = _execute_with_key_rotation(_run_internal)
        text_fallback = getattr(res_internal, "text", "")
        if text_fallback and text_fallback.strip():
            return text_fallback
    except Exception as e:
        print(f"⚠️ Riset internal gagal: {e}")

    return "Fokuskan pada kronologi peristiwa nyata, data angka mengejutkan, dan dampak langsungnya bagi kehidupan masyarakat."

def generate_trending_script(niche: str, specific_title: Optional[str] = None) -> VideoProject:
    past_topics = get_recent_topics(niche)
    blacklist_instruction = ""
    if past_topics:
        past_list_str = "\n- ".join(past_topics)
        blacklist_instruction = (
            f"\nDILARANG MEMBAHAS TOPIK YANG SUDAH PERNAH DIBUAT BERIKUT INI:\n- {past_list_str}\n"
        )

    # Injeksi tren aktual via Google Trends jika pengguna memilih mode otomatis
    trending_context = ""
    if not specific_title:
        live_trends = _get_google_trends_headlines()
        if live_trends:
            trending_context = f"\nISU HANGAT HARI INI DI INDONESIA (Bisa dijadikan inspirasi jika relevan): {', '.join(live_trends)}"

    # Pilih 1 sudut pandang kreatif secara acak
    chosen_angle = random.choice(CONTENT_ANGLES)
    print(f"🎭 [Konsep Terpilih]: {chosen_angle['type']}")

    if specific_title and specific_title.strip():
        research_prompt = f"""
        Riset mendalam mengenai: '{specific_title.strip()}' dalam kategori {niche}.
        Instruksi Sudut Pandang: {chosen_angle['instruction']}
        Cari nama aktor/pelaku, angka kerugian/keuntungan, dan peristiwa kunci. Maksimal 250 kata.
        {blacklist_instruction}
        """
    else:
        research_prompt = f"""
        Temukan 1 studi kasus, fakta gelap, atau fenomena nyata yang mengejutkan tentang {niche}.
        Instruksi Sudut Pandang: {chosen_angle['instruction']}
        {trending_context}
        DILARANG membuat tips menabung, gaji UMR, atau nasihat motivasi klise. 
        Maksimal 250 kata.
        {blacklist_instruction}
        """

    print("🔍 [1/2] Menelusuri fakta peristiwa nyata...")
    researched_info = _research_topic_with_fallback(research_prompt)

    time.sleep(1)

    print("📝 [2/2] Merakit naskah storytelling dramatis...")
    formatting_prompt = f"""
    Referensi Fakta:
    {researched_info[:1600]}

    Format Naskah: {chosen_angle['type']}
    Niche: {niche}
    Fokus Pembahasan: {specific_title if specific_title else 'Cerita/Fakta Baru'}
    {blacklist_instruction}

    ATURAN PENULISAN:
    1. Durasi video MINIMAL 60 DETIK (buat 6-7 adegan, masing-masing 25-30 kata).
    2. Scene 1 (HOOK): Wajib membuka dengan misteri atau fakta mencengangkan tanpa basa-basi (DILARANG pakai 'halo guys' atau 'tahukah kamu').
    3. Scene 2-4 (KRONOLOGI & ESKALASI): Ungkap detail peristiwa dan mengapa hal itu terjadi.
    4. Scene 5-6 (PLOT TWIST/DAMPAK): Tunjukkan fakta yang jarang diketahui orang.
    5. Scene Terakhir (CTA): Berikan pertanyaan reflektif yang memicu perdebatan di kolom komentar.
    6. ANGKA: Semua angka/tahun wajib dieja kata penuh ('tahun dua ribu dua puluh empat').
    7. KEYWORDS PEXELS: 3-5 keyword bahasa Inggris aksi nyata yang sinkron dengan adegan.
    """

    def _generate_json(client: genai.Client, model_name: str):
        return client.models.generate_content(
            model=model_name,
            contents=formatting_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoProject,
                max_output_tokens=4000,
                temperature=0.75,
                system_instruction="Anda adalah sutradara video pendek storytelling dan dokumenter investigasi top dunia."
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
    past_topics = get_recent_topics("all", limit=50)
    blacklist = "\n- ".join(past_topics) if past_topics else "Belum ada"
    live_trends = _get_google_trends_headlines()
    trends_str = ", ".join(live_trends) if live_trends else "Isu tren umum"

    prompt = f"""
    Buat 10 konsep judul video TikTok storytelling & investigasi yang sangat memicu rasa ingin tahu (curiosity loop).
    
    TREN SAAT INI DI INDONESIA:
    {trends_str}

    KOMBINASIKAN DARI BERAGAM SUDUT PANDANG KREATIF:
    - Studi kasus keruntuhan merek besar / skandal korporasi
    - Paradoks psikologi dan bias pikiran manusia
    - Rahasia sejarah gelap industri tertentu
    - Skenario simulasi ekstrem ekonomi/sosial
    - Mitos umum masyarakat yang dibongkar secara brutal

    DILARANG membuat judul tips klise (seperti 'cara menabung gaji UMR', '5 buku wajib dibaca', dll).
    
    DAFTAR TOPIK YANG SUDAH PERNAH DIBUAT (DILARANG DIULANG):
    - {blacklist}
    """

    def _call_bulk(client: genai.Client, model_name: str):
        return client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BulkTopics,
                temperature=0.85,
                system_instruction="Anda adalah creative strategist media sosial viral nomor satu."
            )
        )

    response = _execute_with_key_rotation(_call_bulk)

    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        data = parsed_obj if isinstance(parsed_obj, BulkTopics) else BulkTopics.model_validate(parsed_obj)
    else:
        data = BulkTopics.model_validate_json(_clean_json_string(getattr(response, "text", "{}")))

    return data.topics[:10]