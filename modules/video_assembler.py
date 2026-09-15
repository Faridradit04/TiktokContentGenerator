import os
import glob
import random
import textwrap
import gc
import numpy as np
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import PIL.ImageFilter

if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips
)
from moviepy.audio.fx.all import audio_loop, volumex
from config import VIDEO_WIDTH, VIDEO_HEIGHT, FPS, BGM_DIR
from modules.jamendo_fetcher import fetch_jamendo_bgm

def format_clip_to_vertical(clip: VideoFileClip) -> VideoFileClip:
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT
    clip_ratio = clip.w / clip.h

    if clip_ratio > target_ratio:
        scaled = clip.resize(height=VIDEO_HEIGHT)
        x_center = scaled.w / 2
        return scaled.crop(
            x1=x_center - (VIDEO_WIDTH / 2),
            y1=0,
            x2=x_center + (VIDEO_WIDTH / 2),
            y2=VIDEO_HEIGHT
        )
    else:
        scaled = clip.resize(width=VIDEO_WIDTH)
        y_center = scaled.h / 2
        return scaled.crop(
            x1=0,
            y1=y_center - (VIDEO_HEIGHT / 2),
            x2=VIDEO_WIDTH,
            y2=y_center + (VIDEO_HEIGHT / 2)
        )

def process_product_image_to_vertical(image_path: str) -> str:
    out_path = f"{os.path.splitext(image_path)[0]}_vertical.png"
    if os.path.exists(out_path):
        return out_path

    img = PIL.Image.open(image_path).convert("RGBA")
    bg = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT))
    bg = bg.filter(PIL.ImageFilter.GaussianBlur(radius=20))

    img.thumbnail((VIDEO_WIDTH - 80, VIDEO_HEIGHT - 260))
    x_pos = (VIDEO_WIDTH - img.width) // 2
    y_pos = (VIDEO_HEIGHT - img.height) // 2

    bg.paste(img, (x_pos, y_pos), mask=img)
    bg.save(out_path)
    return out_path

def _get_system_font(font_size: int):
    system_fonts = [
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arialbd.ttf",
        "segoeuib.ttf"
    ]
    for f in system_fonts:
        try:
            return PIL.ImageFont.truetype(f, font_size)
        except Exception:
            continue
    return PIL.ImageFont.load_default()

def create_text_overlay_clip(text: str, duration: float) -> ImageClip:
    if not text:
        return None
    img = PIL.Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(img)

    font = _get_system_font(font_size=36)
    wrapped_text = "\n".join(textwrap.wrap(text.upper(), width=20))
    y_pos = int(VIDEO_HEIGHT * 0.35)

    draw.multiline_text(
        (VIDEO_WIDTH // 2, y_pos),
        wrapped_text,
        font=font,
        fill="#FFE600",
        stroke_width=5,
        stroke_fill="black",
        anchor="ma",
        align="center",
        spacing=8
    )
    return ImageClip(np.array(img), ismask=False, transparent=True).set_duration(duration)

def create_chunked_subtitle_clips(narration_text: str, total_duration: float) -> list:
    words = narration_text.strip().split()
    if not words:
        return []

    chunk_size = 4
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    chunk_duration = total_duration / len(chunks)

    font_sub = _get_system_font(font_size=30)
    y_safe_pos = int(VIDEO_HEIGHT * 0.60)

    sub_clips = []
    current_time = 0.0

    for chunk_text in chunks:
        img = PIL.Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        draw = PIL.ImageDraw.Draw(img)

        draw.text(
            (VIDEO_WIDTH // 2, y_safe_pos),
            chunk_text.upper(),
            font=font_sub,
            fill="#FFFFFF",
            stroke_width=4,
            stroke_fill="#000000",
            anchor="mm",
            align="center"
        )

        clip = (
            ImageClip(np.array(img), ismask=False, transparent=True)
            .set_start(current_time)
            .set_duration(chunk_duration)
        )
        sub_clips.append(clip)
        current_time += chunk_duration

    return sub_clips

def build_scene_ultralight(media_path: str, audio_path: str, overlay_text: str, voiceover_text: str) -> CompositeVideoClip:
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    if media_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        v_img = process_product_image_to_vertical(media_path)
        base_video = ImageClip(v_img).set_duration(duration)
    else:
        raw_video = VideoFileClip(media_path).without_audio()
        v_clip = format_clip_to_vertical(raw_video)
        if v_clip.duration < duration:
            base_video = v_clip.loop(duration=duration)
        else:
            base_video = v_clip.subclip(0, duration)

    elements = [base_video]
    
    txt_clip = create_text_overlay_clip(overlay_text, duration)
    if txt_clip:
        elements.append(txt_clip)

    sub_clips = create_chunked_subtitle_clips(voiceover_text, duration)
    elements.extend(sub_clips)

    return CompositeVideoClip(elements, size=(VIDEO_WIDTH, VIDEO_HEIGHT)).set_audio(audio)

def generate_video_cover(first_media_path: str, headline_text: str, output_path: str) -> str:
    print("🖼️ Membuat gambar cover thumbnail...")
    raw_video = None
    vertical_video = None
    try:
        if first_media_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            base_img = PIL.Image.open(first_media_path).resize((VIDEO_WIDTH, VIDEO_HEIGHT)).convert("RGBA")
        else:
            raw_video = VideoFileClip(first_media_path)
            vertical_video = format_clip_to_vertical(raw_video)
            frame = vertical_video.get_frame(min(0.5, vertical_video.duration / 2))
            base_img = PIL.Image.fromarray(frame).convert("RGBA")

        overlay = PIL.Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 125))
        combined = PIL.Image.alpha_composite(base_img, overlay)
        draw = PIL.ImageDraw.Draw(combined)

        font = _get_system_font(font_size=52)
        wrapped_headline = "\n".join(textwrap.wrap(headline_text.upper(), width=18))

        draw.multiline_text(
            (VIDEO_WIDTH // 2, int(VIDEO_HEIGHT * 0.42)),
            wrapped_headline,
            font=font,
            fill="#FFE600",
            stroke_width=6,
            stroke_fill="black",
            anchor="mm",
            align="center",
            spacing=14
        )
        combined.convert("RGB").save(output_path, "JPEG", quality=88)
        return output_path
    finally:
        if vertical_video:
            try: vertical_video.close()
            except Exception: pass
        if raw_video:
            try: raw_video.close()
            except Exception: pass

def render_full_tiktok(processed_scenes: list, output_filename: str, niche: str = "education"):
    scene_clips = []
    final_video = None
    bgm_clip = None
    print("🎞️ Merakit video (Engine Low-RAM 720p)...")

    try:
        for scene in processed_scenes:
            media_path = scene.get("video_path")
            audio_path = scene.get("audio_path")
            if not media_path or not os.path.exists(media_path) or not audio_path or not os.path.exists(audio_path):
                continue

            clip = build_scene_ultralight(
                media_path=media_path,
                audio_path=audio_path,
                overlay_text=scene.get("text_overlay", ""),
                voiceover_text=scene.get("voiceover_text", "")
            )
            scene_clips.append(clip)
            gc.collect()

        if not scene_clips:
            raise RuntimeError("Tidak ada klip valid untuk dirakit.")

        final_video = concatenate_videoclips(scene_clips, method="compose")
        total_duration = final_video.duration
        print(f"⏱️ Total durasi: {round(total_duration, 1)} detik")

        jamendo_track = fetch_jamendo_bgm(niche=niche)
        if jamendo_track and os.path.exists(jamendo_track):
            try:
                bgm_raw = AudioFileClip(jamendo_track)
                bgm_looped = audio_loop(bgm_raw, duration=total_duration)
                bgm_quiet = volumex(bgm_looped, 0.09)
                mixed_audio = CompositeAudioClip([final_video.audio, bgm_quiet])
                final_video = final_video.set_audio(mixed_audio)
                bgm_clip = bgm_raw
            except Exception as e:
                print(f"⚠️ Gagal mixing BGM: {e}")

        # Render dengan batasan buffer FFmpeg ketat
        final_video.write_videofile(
            output_filename,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            threads=1,
            preset="ultrafast",
            ffmpeg_params=["-crf", "26", "-maxrate", "2500k", "-bufsize", "5000k"]
        )
        print("✅ Render selesai tanpa OOM!")
    finally:
        for clip in scene_clips:
            try: clip.close()
            except Exception: pass
        if final_video:
            try: final_video.close()
            except Exception: pass
        if bgm_clip:
            try: bgm_clip.close()
            except Exception: pass
        gc.collect()