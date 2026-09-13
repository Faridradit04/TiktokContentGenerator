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
from modules.script_gen import generate_trending_script, generate_10_bulk_topics
from modules.script_affiliate import generate_affiliate_script
from modules.audio_engine import process_json_to_audio
from modules.visual_fetcher import fetch_broll_clips
from modules.video_assembler import render_full_tiktok, generate_video_cover
from modules.drive_uploader import (
    upload_file_to_drive,
    create_or_get_drive_folder,
    save_metadata_file,
    cleanup_local_files
)

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_TELEGRAM_USER_ID", "0"))

EDU_NICHE, EDU_TITLE, AFF_MEDIA, AFF_DESC = range(4)

def is_owner(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    keyboard = [
        [InlineKeyboardButton("📚 Konten Edukasi / Tren", callback_data="menu_edu")],
        [InlineKeyboardButton("🛍️ Konten Produk Affiliate", callback_data="menu_aff")],
        [InlineKeyboardButton("🚀 Auto Generate 10 Video (Random Niche)", callback_data="menu_bulk10")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *STUDIO KONTEN TIKTOK AI*\n\n"
        "Silakan pilih mode pembuatan konten:\n"
        "Setiap video otomatis dibuatkan subfolder khusus di Google Drive dan file lokal langsung dibersihkan.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu_edu":
        await query.message.reply_text(
            "📚 *Jalur Konten Edukasi*\n"
            "Ketik **Niche** konten (contoh: *Finansial*, *Psikologi*, *AI Tools*):",
            parse_mode="Markdown"
        )
        return EDU_NICHE

    elif query.data == "menu_aff":
        await query.message.reply_text(
            "🛍️ *Jalur Konten Affiliate*\n"
            "Kirimkan **1 Foto atau Video Produk** sekarang:",
            parse_mode="Markdown"
        )
        return AFF_MEDIA

    elif query.data == "menu_bulk10":
        # Jalankan eksekusi 10 video secara asynchronous
        asyncio.create_task(run_pipeline_bulk_10(query.message, context))
        return ConversationHandler.END

# --- Handler Percakapan Edukasi ---
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
    status_msg = await update.message.reply_text("🚀 Memulai antrean konten edukasi...")
    asyncio.create_task(execute_single_video(status_msg, niche=niche, specific_title=title_text))
    return ConversationHandler.END

# --- Handler Percakapan Affiliate ---
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
        await update.message.reply_text("⚠️ Kirim foto atau video produk.")
        return AFF_MEDIA

    telegram_file = await context.bot.get_file(file_id)
    saved_path = str(UPLOADS_DIR / f"affiliate_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_ext}")
    await telegram_file.download_to_drive(saved_path)
    context.user_data["aff_media_path"] = saved_path

    await update.message.reply_text(
        "✅ Media produk diterima!\n\n"
        "Sekarang ketik **Nama Produk, Manfaat Utama, dan Promo Khusus**:\n"
        "*(Contoh: Termos tumbler tahan dingin 24 jam, diskon flash sale 40 ribu)*",
        parse_mode="Markdown"
    )
    return AFF_DESC

async def receive_affiliate_desc_and_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    media_path = context.user_data.get("aff_media_path")
    status_msg = await update.message.reply_text("🛍️ Memulai pembuatan konten affiliate...")
    asyncio.create_task(execute_affiliate_video(status_msg, media_path=media_path, desc=desc))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Proses dibatalkan.")
    return ConversationHandler.END

# --- Engine Pemrosesan Tunggal Edukasi ---
async def execute_single_video(status_msg, niche: str, specific_title: str = None) -> bool:
    created_temp_files = []
    try:
        await status_msg.edit_text(f"🔍 [1/5] Meriset & menyusun naskah ({niche})...")
        script_data = generate_trending_script(niche=niche, specific_title=specific_title)
        topic_title = script_data.metadata.source_topic
        slug = slugify_filename(topic_title)

        await status_msg.edit_text(f"🎙️ [2/5] Merekam voice-over: *{topic_title}*...", parse_mode="Markdown")
        scenes_audio = await process_json_to_audio(script_data.model_dump(), str(AUDIO_DIR))
        for sc in scenes_audio:
            if sc.get("audio_path"):
                created_temp_files.append(sc["audio_path"])

        await status_msg.edit_text("🎬 [3/5] Mengunduh B-roll Pexels HD...", parse_mode="Markdown")
        scenes_ready = fetch_broll_clips(scenes_audio, str(RAW_CLIPS_DIR))
        for sc in scenes_ready:
            if sc.get("video_path") and sc["video_path"] not in created_temp_files:
                created_temp_files.append(sc["video_path"])

        await status_msg.edit_text("🎞️ [4/5] Merender video 9:16 durasi 60+ detik...", parse_mode="Markdown")
        out_video = OUTPUT_DIR / f"{slug}.mp4"
        out_cover = OUTPUT_DIR / f"{slug}_cover.jpg"
        out_meta = OUTPUT_DIR / f"{slug}_metadata.txt"
        created_temp_files.extend([str(out_video), str(out_cover), str(out_meta)])

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, render_full_tiktok, scenes_ready, str(out_video))
        if scenes_ready[0].get("video_path"):
            await loop.run_in_executor(
                None,
                generate_video_cover,
                scenes_ready[0]["video_path"],
                script_data.metadata.cover_headline,
                str(out_cover)
            )

        # Simpan metadata
        meta_path = save_metadata_file(script_data.metadata, str(out_meta))

        # Upload ke subfolder khusus di Google Drive
        await status_msg.edit_text("☁️ [5/5] Membuat subfolder & mengunggah ke Google Drive...")
        folder_drive_name = f"[{niche.upper()}] {topic_title}"
        target_folder_id = create_or_get_drive_folder(folder_drive_name, GDRIVE_FOLDER_ID)

        upload_file_to_drive(str(out_video), target_folder_id)
        if out_cover.exists():
            upload_file_to_drive(str(out_cover), target_folder_id)
        upload_file_to_drive(str(meta_path), target_folder_id)

        with open(meta_path, "r", encoding="utf-8") as f:
            caption_text = f.read()

        await status_msg.edit_text(
            f"✅ *SELESAI!*\n\n"
            f"📁 *Folder Drive:* `{folder_drive_name}`\n"
            f"🧹 *Status Disk:* File lokal langsung dibersihkan.\n\n"
            f"📝 *Metadata:*\n```text\n{caption_text}\n```",
            parse_mode="Markdown"
        )
        return True
    except Exception as e:
        await status_msg.edit_text(f"❌ Terjadi error pada: `{niche}`\nDetail: `{e}`", parse_mode="Markdown")
        return False
    finally:
        # Pembersihan berkas lokal agar harddisk laptop/VPS tidak penuh
        cleanup_local_files(created_temp_files)

# --- Engine Pemrosesan Affiliate ---
async def execute_affiliate_video(status_msg, media_path: str, desc: str):
    created_temp_files = [media_path]
    try:
        await status_msg.edit_text("🔍 [1/5] Gemini Vision menganalisis produk...")
        script_data = generate_affiliate_script(media_path, desc)
        topic_title = script_data.metadata.source_topic
        slug = slugify_filename(topic_title)

        await status_msg.edit_text(f"🎙️ [2/5] Membuat narasi: *{topic_title}*...", parse_mode="Markdown")
        scenes_audio = await process_json_to_audio(script_data.model_dump(), str(AUDIO_DIR))
        for sc in scenes_audio:
            if sc.get("audio_path"):
                created_temp_files.append(sc["audio_path"])

        for sc in scenes_audio:
            if sc.get("visual_source") == "product_asset":
                sc["video_path"] = media_path

        await status_msg.edit_text("🎬 [3/5] Mengunduh b-roll pelengkap Pexels...", parse_mode="Markdown")
        scenes_ready = fetch_broll_clips(scenes_audio, str(RAW_CLIPS_DIR))
        for sc in scenes_ready:
            if sc.get("video_path") and sc["video_path"] not in created_temp_files:
                created_temp_files.append(sc["video_path"])

        await status_msg.edit_text("🎞️ [4/5] Merender video affiliate 60+ detik...", parse_mode="Markdown")
        out_video = OUTPUT_DIR / f"{slug}.mp4"
        out_cover = OUTPUT_DIR / f"{slug}_cover.jpg"
        out_meta = OUTPUT_DIR / f"{slug}_metadata.txt"
        created_temp_files.extend([str(out_video), str(out_cover), str(out_meta)])

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, render_full_tiktok, scenes_ready, str(out_video))
        await loop.run_in_executor(
            None,
            generate_video_cover,
            media_path,
            script_data.metadata.cover_headline,
            str(out_cover)
        )

        meta_path = save_metadata_file(script_data.metadata, str(out_meta))

        await status_msg.edit_text("☁️ [5/5] Membuat folder & mengunggah ke Google Drive...")
        folder_drive_name = f"[AFFILIATE] {topic_title}"
        target_folder_id = create_or_get_drive_folder(folder_drive_name, GDRIVE_FOLDER_ID)

        upload_file_to_drive(str(out_video), target_folder_id)
        if out_cover.exists():
            upload_file_to_drive(str(out_cover), target_folder_id)
        upload_file_to_drive(str(meta_path), target_folder_id)

        with open(meta_path, "r", encoding="utf-8") as f:
            caption_text = f.read()

        await status_msg.edit_text(
            f"✅ *PRODUK AFFILIATE SELESAI!*\n\n"
            f"📁 *Folder Drive:* `{folder_drive_name}`\n\n"
            f"📝 *Caption & Hashtag:*\n```text\n{caption_text}\n```",
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error affiliate: `{e}`", parse_mode="Markdown")
    finally:
        cleanup_local_files(created_temp_files)

# --- Engine Pemrosesan Bulk 10 Video Sekaligus ---
async def run_pipeline_bulk_10(msg, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await msg.reply_text("🤖 [Riset AI] Sedang meriset 10 topik tren acak bebas duplikasi...")
    try:
        topics_list = generate_10_bulk_topics()
        daftar_text = "\n".join([f"{i+1}. [{t.niche}] {t.title}" for i, t in enumerate(topics_list)])
        await status_msg.edit_text(
            f"📋 *Daftar 10 Topik yang Terpilih:*\n\n{daftar_text}\n\n"
            "⏳ Memulai proses pembuatan secara otomatis satu per satu...",
            parse_mode="Markdown"
        )

        success_count = 0
        for idx, item in enumerate(topics_list):
            progress_msg = await msg.reply_text(f"⏳ Memproses ({idx+1}/10): *[{item.niche}]* {item.title}...", parse_mode="Markdown")
            success = await execute_single_video(progress_msg, niche=item.niche, specific_title=item.title)
            if success:
                success_count += 1
            # Beri jeda 4 detik antar video untuk menjaga stabilitas API
            await asyncio.sleep(4)

        await msg.reply_text(
            f"🎉 *PROSES MASSAL 10 VIDEO SELESAI!*\n\n"
            f"✅ Berhasil diproduksi: *{success_count}/10 video*.\n"
            f"📁 Masing-masing video sudah rapi di subfoldernya sendiri di Google Drive.\n"
            f"🧹 Seluruh file sisa di VPS telah dibersihkan secara otomatis.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Gagal pada proses 10 video massal: `{e}`", parse_mode="Markdown")

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
    print("🤖 Bot Telegram Multi-Cabang + Auto 10 Video Aktif!")
    app.run_polling()

if __name__ == "__main__":
    run_bot()