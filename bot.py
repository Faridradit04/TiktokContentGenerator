import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from config import (
    AUDIO_DIR,
    RAW_CLIPS_DIR,
    OUTPUT_DIR,
    UPLOADS_DIR,
    GDRIVE_FOLDER_ID,
    slugify_filename
)
from modules.script_gen import generate_trending_script
from modules.script_affiliate import generate_affiliate_script
from modules.audio_engine import process_json_to_audio
from modules.visual_fetcher import fetch_broll_clips
from modules.video_assembler import render_full_tiktok, generate_video_cover
from modules.drive_uploader import upload_file_to_drive, save_metadata_file

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_TELEGRAM_USER_ID", "0"))

# State dialog
EDU_NICHE, EDU_TITLE, AFF_MEDIA, AFF_DESC = range(4)

def is_owner(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    keyboard = [
        [
            InlineKeyboardButton("📚 Konten Edukasi / Tren", callback_data="menu_edu"),
            InlineKeyboardButton("🛍️ Konten Produk Affiliate", callback_data="menu_aff")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *STUDIO KONTEN TIKTOK AI*\n\n"
        "Silakan pilih jenis konten yang ingin diproduksi:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_edu":
        await query.message.reply_text(
            "📚 *Jalur Konten Edukasi*\n"
            "Ketik **Niche** konten (contoh: *Finansial*, *Kesehatan*, *AI Tools*):",
            parse_mode="Markdown"
        )
        return EDU_NICHE

    elif query.data == "menu_aff":
        await query.message.reply_text(
            "🛍️ *Jalur Konten Affiliate*\n"
            "Kirimkan **1 Foto atau Video Produk** yang ingin dipromosikan sekarang:",
            parse_mode="Markdown"
        )
        return AFF_MEDIA

# --- Alur Edukasi ---
async def receive_edu_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["edu_niche"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Niche: *{context.user_data['edu_niche']}*\n\n"
        "Ketik **Judul/Topik Spesifik** yang diinginkan.\n"
        "*(Ketik `skip` jika ingin AI mencarikan topik tren unik yang belum pernah dibuat)*",
        parse_mode="Markdown"
    )
    return EDU_TITLE

async def receive_edu_title_and_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title_text = update.message.text.strip()
    if title_text.lower() == "skip":
        title_text = None

    niche = context.user_data.get("edu_niche")
    await run_pipeline_education(update, niche, title_text)
    return ConversationHandler.END

# --- Alur Affiliate ---
async def receive_affiliate_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = None
    file_ext = ".jpg"

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        file_ext = ".jpg"
    elif update.message.video:
        file_id = update.message.video.file_id
        file_ext = ".mp4"
    else:
        await update.message.reply_text("⚠️ Kirim berkas foto atau video produk.")
        return AFF_MEDIA

    telegram_file = await context.bot.get_file(file_id)
    saved_path = str(UPLOADS_DIR / f"affiliate_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_ext}")
    await telegram_file.download_to_drive(saved_path)
    context.user_data["aff_media_path"] = saved_path

    await update.message.reply_text(
        "✅ Media produk diterima!\n\n"
        "Sekarang ketik **Nama Produk, Manfaat Utama, dan Promo Khusus**:\n"
        "*(Contoh: Termos tumbler tahan dingin 24 jam anti tumpah, diskon flash sale 40 ribu)*",
        parse_mode="Markdown"
    )
    return AFF_DESC

async def receive_affiliate_desc_and_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    media_path = context.user_data.get("aff_media_path")
    await run_pipeline_affiliate(update, media_path, desc)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Proses dibatalkan.")
    return ConversationHandler.END

# --- Eksekutor Pipeline ---
async def run_pipeline_education(update: Update, niche: str, title: str = None):
    status_msg = await update.message.reply_text(f"🚀 [1/5] Meriset topik edukasi unik & menyusun naskah ({niche})...")
    try:
        script_data = generate_trending_script(niche=niche, specific_title=title)
        slug = slugify_filename(script_data.metadata.source_topic)

        await status_msg.edit_text(f"🎙️ [2/5] Membuat narasi: *{script_data.metadata.source_topic}*...", parse_mode="Markdown")
        scenes_audio = await process_json_to_audio(script_data.model_dump(), str(AUDIO_DIR))

        await status_msg.edit_text("🎬 [3/5] Mengunduh klip video B-Roll Pexels...", parse_mode="Markdown")
        scenes_ready = fetch_broll_clips(scenes_audio, str(RAW_CLIPS_DIR))

        await status_msg.edit_text("🎞️ [4/5] Merender video 9:16 (60+ detik) dengan subtitle...", parse_mode="Markdown")
        out_video = OUTPUT_DIR / f"{slug}.mp4"
        out_cover = OUTPUT_DIR / f"{slug}_cover.jpg"
        out_meta = OUTPUT_DIR / f"{slug}_metadata.txt"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, render_full_tiktok, scenes_ready, str(out_video))
        if scenes_ready[0].get("video_path"):
            await loop.run_in_executor(None, generate_video_cover, scenes_ready[0]["video_path"], script_data.metadata.cover_headline, str(out_cover))

        await upload_and_finish(status_msg, update, script_data.metadata, out_video, out_cover, out_meta)
    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan: `{e}`", parse_mode="Markdown")

async def run_pipeline_affiliate(update: Update, media_path: str, desc: str):
    status_msg = await update.message.reply_text("🔍 [1/5] Gemini Vision menganalisis produk & membuat naskah...")
    try:
        script_data = generate_affiliate_script(media_path, desc)
        slug = slugify_filename(script_data.metadata.source_topic)

        await status_msg.edit_text(f"🎙️ [2/5] Membuat narasi promosi: *{script_data.metadata.source_topic}*...", parse_mode="Markdown")
        scenes_audio = await process_json_to_audio(script_data.model_dump(), str(AUDIO_DIR))

        # Pasangkan foto produk ke adegan yang membutuhkan product_asset
        for sc in scenes_audio:
            if sc.get("visual_source") == "product_asset":
                sc["video_path"] = media_path

        await status_msg.edit_text("🎬 [3/5] Mengunduh klip B-roll pelengkap dari Pexels...", parse_mode="Markdown")
        scenes_ready = fetch_broll_clips(scenes_audio, str(RAW_CLIPS_DIR))

        await status_msg.edit_text("🎞️ [4/5] Merender video promosi affiliate...", parse_mode="Markdown")
        out_video = OUTPUT_DIR / f"{slug}.mp4"
        out_cover = OUTPUT_DIR / f"{slug}_cover.jpg"
        out_meta = OUTPUT_DIR / f"{slug}_metadata.txt"

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, render_full_tiktok, scenes_ready, str(out_video))
        await loop.run_in_executor(None, generate_video_cover, media_path, script_data.metadata.cover_headline, str(out_cover))

        await upload_and_finish(status_msg, update, script_data.metadata, out_video, out_cover, out_meta)
    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi kesalahan affiliate: `{e}`", parse_mode="Markdown")

async def upload_and_finish(status_msg, update: Update, metadata, out_video, out_cover, out_meta):
    await status_msg.edit_text("☁️ [5/5] Menyimpan metadata & mengunggah ke Google Drive...")
    meta_path = save_metadata_file(metadata, str(out_meta))

    drive_info = "Lokal saja"
    if GDRIVE_FOLDER_ID:
        cid = GDRIVE_FOLDER_ID.split("?")[0].strip()
        vid_id = upload_file_to_drive(str(out_video), cid)
        if out_cover.exists():
            upload_file_to_drive(str(out_cover), cid)
        upload_file_to_drive(str(meta_path), cid)
        drive_info = f"✅ Berhasil masuk Drive (ID: `{vid_id}`)"

    with open(meta_path, "r", encoding="utf-8") as f:
        caption_text = f.read()

    await status_msg.edit_text(
        f"🎉 *KONTEN SELESAI!*\n\n{drive_info}\n\n"
        f"📝 *Caption & Hashtag:*\n```text\n{caption_text}\n```",
        parse_mode="Markdown"
    )
    if out_cover.exists():
        with open(out_cover, "rb") as p:
            await update.message.reply_photo(photo=p, caption="🖼️ Preview Cover Thumbnail")

def run_bot():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN belum disetel di .env")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("buat", start),
            CallbackQueryHandler(button_handler, pattern="^menu_")
        ],
        states={
            EDU_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edu_niche)],
            EDU_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edu_title_and_run)],
            AFF_MEDIA: [MessageHandler(filters.PHOTO | filters.VIDEO, receive_affiliate_media)],
            AFF_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_affiliate_desc_and_run)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    print("🤖 Bot Telegram Multi-Cabang Aktif!")
    app.run_polling()

if __name__ == "__main__":
    run_bot()