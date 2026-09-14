import re
import time
from typing import Optional, Callable, Any
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import PIL.Image

from config import GEMINI_API_KEYS
from modules.db_manager import save_topic

TARGET_MODEL = "gemini-2.5-flash"

class AffiliateScene(BaseModel):
    scene_id: int
    role: str = Field(description="hook, problem, product_reveal, feature_1, feature_2, cta")
    voiceover_text: str = Field(
        description="Narasi promosi TikTok yang persuasif, natural, tidak kaku, dan eja angka/diskon secara penuh. Durasi per adegan cukup panjang."
    )
    visual_source: str = Field(
        description="'product_asset' jika menampilkan foto/video produk kiriman pengguna, atau 'pexels' jika menampilkan klip B-roll pendukung."
    )
    stock_keywords: list[str] = Field(
        description="3-5 keyword Pexels bahasa Inggris berupa aksi nyata yang relevan dengan fungsi produk (contoh: 'thirsty athlete drinking water', 'woman sweating hot sun')."
    )
    text_overlay: str = Field(description="Headline teks penawaran/fitur maksimal 3-4 kata kapital.")

class AffiliateMetadata(BaseModel):
    tiktok_caption: str = Field(description="Caption penjualan TikTok dengan hashtag dan ajakan cek keranjang kuning/bio")
    hashtags: list[str] = Field(description="5 hashtag tren affiliate")
    source_topic: str = Field(description="Nama produk dan nilai jual utamanya")
    cover_headline: str = Field(description="Headline cover promo diskon/solusi (maksimal 5 kata kapital)")

class AffiliateProject(BaseModel):
    project_title: str
    metadata: AffiliateMetadata
    scenes: list[AffiliateScene]

def _clean_json_string(raw_text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    return cleaned.strip()

def _execute_with_key_rotation(operation: Callable[[genai.Client], Any]) -> Any:
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

    raise RuntimeError(f"Semua kuota API Key Gemini telah habis: {last_error}")

def generate_affiliate_script(media_path: str, product_desc: str) -> AffiliateProject:
    prompt = f"""
    ANALISIS PRODUK AFFILIATE TIKTOK:
    Keterangan Produk dari Penjual: "{product_desc}"

    TUGAS:
    Analisis media produk ini (warna, bentuk, fungsi, keunggulan fisik).
    Susun naskah video TikTok promosi berdurasi MINIMAL 60 DETIK (target 60-70 detik, buat 6 adegan):
    1. Scene 1 (Hook Masalah): Sorot penderitaan/masalah yang dihadapi penonton tanpa produk ini. (visual_source: 'pexels')
    2. Scene 2 (Solusi/Product Reveal): Kenalkan produk sebagai solusi terbaik. (visual_source: 'product_asset')
    3. Scene 3 & 4 (Detail Fitur & Manfaat Nyata): Tunjukkan detail fisik produk dan bagaimana produk mempermudah hidup. (Bergantian 'product_asset' dan 'pexels')
    4. Scene 5 (Urgensi Diskon/Promo): Tekankan harga terjangkau atau stok terbatas. (visual_source: 'product_asset')
    5. Scene 6 (Call to Action Kuat): Instruksikan klik keranjang kuning di kiri bawah atau cek link di bio sekarang. (visual_source: 'product_asset')

    ATURAN TEKNIS:
    - Narasi panjang (25-30 kata per adegan) agar durasi total mencapai minimal 60 detik.
    - Eja angka/harga secara penuh ('sembilan puluh sembilan ribu rupiah').
    - Berikan 3-5 stock_keywords bahasa Inggris yang relevan untuk setiap adegan.
    """

    def _call_affiliate(client: genai.Client):
        contents = []
        if media_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            img = PIL.Image.open(media_path)
            contents.append(img)
        elif media_path.lower().endswith((".mp4", ".mov", ".avi")):
            video_file = client.files.upload(file=media_path)
            contents.append(video_file)
        contents.append(prompt)

        return client.models.generate_content(
            model=TARGET_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AffiliateProject,
                max_output_tokens=4000,
                temperature=0.7,
                system_instruction="Anda adalah copywriter affiliate TikTok top dunia. Buat naskah promosi yang menghasilkan konversi penjualan tinggi."
            )
        )

    print("🛍️ [Gemini Vision] Menganalisis produk dan membuat naskah affiliate...")
    response = _execute_with_key_rotation(_call_affiliate)

    parsed_obj = getattr(response, "parsed", None)
    if parsed_obj is not None:
        proj = parsed_obj if isinstance(parsed_obj, AffiliateProject) else AffiliateProject.model_validate(parsed_obj)
    else:
        raw_text = getattr(response, "text", None)
        proj = AffiliateProject.model_validate_json(_clean_json_string(raw_text))

    save_topic("affiliate", "affiliate_product", proj.metadata.source_topic)
    return proj