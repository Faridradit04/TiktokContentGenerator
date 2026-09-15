import os
import glob
import random
import textwrap
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
    """Mengubah foto produk statis menjadi background blur estetis 9:16."""
    out_path = f"{os.path.splitext(image_path)[0]}_vertical.png"
    if os.path.exists(out_path):
        return out_path

    img = PIL.Image.open(image_path).convert("RGBA")
    
    # 1. Background: di-crop dan di-blur pekat
    bg = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT))
    bg = bg.filter(PIL.ImageFilter.GaussianBlur(radius=30))

    # 2. Gambar produk di tengah tanpa terdistorsi
    img.thumbnail((VIDEO_WIDTH - 120, VIDEO_HEIGHT - 350))
    x_pos = (VIDEO_WIDTH - img.width) // 2
    y_pos = (VIDEO_HEIGHT - img.height) // 2

    bg.paste(img, (x_pos, y_pos), mask=img)
    bg.save(out_path)
    return out_path

def apply_slow_zoom(clip, duration: float):
    zoom_clip = clip.resize(lambda t: 1.0 + 0.08 * (t / max(duration, 0.1)))
    return zoom_clip.crop(
        x_center=zoom_clip.w / 2,
        y_center=zoom_clip.h / 2,
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT
    )

def _get_system_font(font_size: int):
    system_fonts = [
        "arialbd.ttf",
        "arial.ttf",
        "segoeuib.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]
    for f in system_fonts:
        try:
            return PIL.ImageFont.truetype(f, font_size)
        except Exception:
            continue
    return PIL.ImageFont.load_default()

def create_text_overlay_clip(text: str, duration: float) -> ImageClip:
    img = PIL.Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(img)

    font = _get_system_font(font_size=52)
    wrapped_text = "\n".join(textwrap.wrap(text.upper(), width=24))
    y_pos = int(VIDEO_HEIGHT * 0.38)

    draw.multiline_text(
        (VIDEO_WIDTH // 2, y_pos),
        wrapped_text,
        font=font,
        fill="#FFE600",
        stroke_width=7,
        stroke_fill="black",
        anchor="ma",
        align="center",
        spacing=12
    )

    return ImageClip(np.array(img), ismask=False, transparent=True).set_duration(duration)

def create_subtitle_clip(narration_text: str, duration: float) -> ImageClip:
    """Subtitle narasi diperlebar (width=46) agar menyebar proporsional dan tidak menumpuk sempit."""
    img = PIL.Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = PIL.ImageDraw.Draw(img)

    font_sub = _get_system_font(font_size=34)
    wrapped_sub = "\n".join(textwrap.wrap(narration_text, width=46))
    y_pos = int(VIDEO_HEIGHT * 0.72)

    draw.multiline_text(
        (VIDEO_WIDTH // 2, y_pos),
        wrapped_sub,
        font=font_sub,
        fill="#FFFFFF",
        stroke_width=5,
        stroke_fill="#000000",
        anchor="ma",
        align="center",
        spacing=10
    )

    return ImageClip(np.array(img), ismask=False, transparent=True).set_duration(duration)

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

        overlay = PIL.Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 115))
        combined = PIL.Image.alpha_composite(base_img, overlay)
        draw = PIL.ImageDraw.Draw(combined)

        font = _get_system_font(font_size=74)
        wrapped_headline = "\n".join(textwrap.wrap(headline_text.upper(), width=18))

        draw.multiline_text(
            (VIDEO_WIDTH // 2, int(VIDEO_HEIGHT * 0.42)),
            wrapped_headline,
            font=font,
            fill="#FFE600",
            stroke_width=9,
            stroke_fill="black",
            anchor="mm",
            align="center",
            spacing=20
        )

        combined.convert("RGB").save(output_path, "JPEG", quality=95)
        return output_path
    finally:
        # Menutup file handle video jika dibuka
        if vertical_video:
            try:
                vertical_video.close()
            except Exception:
                pass
        if raw_video:
            try:
                raw_video.close()
            except Exception:
                pass

def build_scene(media_path: str, audio_path: str, overlay_text: str, voiceover_text: str) -> CompositeVideoClip:
    audio = AudioFileClip(audio_path)
    duration = audio.duration

    if media_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        vertical_img_path = process_product_image_to_vertical(media_path)
        base_clip = ImageClip(vertical_img_path).set_duration(duration)
    else:
        raw_video = VideoFileClip(media_path).without_audio()
        vertical_video = format_clip_to_vertical(raw_video)
        if vertical_video.duration < duration:
            base_clip = vertical_video.loop(duration=duration)
        else:
            base_clip = vertical_video.subclip(0, duration)

    dynamic_clip = apply_slow_zoom(base_clip, duration)
    txt_clip = create_text_overlay_clip(overlay_text, duration)
    sub_clip = create_subtitle_clip(voiceover_text, duration)

    return CompositeVideoClip([dynamic_clip, txt_clip, sub_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT)).set_audio(audio)

def render_full_tiktok(processed_scenes: list, output_filename: str):
    scene_clips = []
    final_video = None
    bgm_raw = None
    print("🎞️ Merakit seluruh adegan video vertikal...")

    try:
        for scene in processed_scenes:
            media_path = scene.get("video_path")
            audio_path = scene.get("audio_path")
            if not media_path or not os.path.exists(media_path) or not audio_path or not os.path.exists(audio_path):
                continue

            clip = build_scene(
                media_path=media_path,
                audio_path=audio_path,
                overlay_text=scene.get("text_overlay", ""),
                voiceover_text=scene.get("voiceover_text", "")
            )
            scene_clips.append(clip)

        if not scene_clips:
            raise RuntimeError("Tidak ada klip video yang valid untuk dirakit.")

        final_video = concatenate_videoclips(scene_clips, method="compose")
        total_duration = final_video.duration
        print(f"⏱️ Total durasi: {round(total_duration, 1)} detik")

        bgm_files = glob.glob(str(BGM_DIR / "*.mp3"))
        if bgm_files:
            chosen_bgm = random.choice(bgm_files)
            try:
                bgm_raw = AudioFileClip(chosen_bgm)
                bgm_looped = audio_loop(bgm_raw, duration=total_duration)
                bgm_quiet = volumex(bgm_looped, 0.12)
                mixed_audio = CompositeAudioClip([final_video.audio, bgm_quiet])
                final_video = final_video.set_audio(mixed_audio)
            except Exception as e:
                print(f"⚠️ BGM diabaikan: {e}")

        final_video.write_videofile(
            output_filename,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            threads=4,
            preset="ultrafast"
        )
        print("✅ Render selesai!")
    finally:
        # Tutup semua klip agar Windows melepaskan file lock
        for clip in scene_clips:
            try:
                clip.close()
            except Exception:
                pass
        if final_video:
            try:
                final_video.close()
            except Exception:
                pass
        if bgm_raw:
            try:
                bgm_raw.close()
            except Exception:
                pass