"""
Usage:
    python video_builder.py 
        --script-path scripts/hotel_economics.txt 
        --audio-dir audio/hotel_economics 
        --image-dir images/hotel_economics 
        --subtitle-path subtitles/hotel_economics.srt 
        --output-path video/hotel_economics.mp4
        [--mood happy|angry]
        [--fast]
        [--skip-tts]
"""

# Pillow 10 compatibility: add ANTIALIAS alias if missing
from PIL import Image as PILImage
if not hasattr(PILImage, "ANTIALIAS"):
    PILImage.ANTIALIAS = PILImage.Resampling.LANCZOS

import moviepy.config as mpc
mpc.IMAGEMAGICK_BINARY = "convert"   # macOS에선 "magick" 대신 "convert"일 수 있음

# --- Add import for hashing ---
import hashlib
import os
# import librosa  # disabled beat detection
import argparse
import random
from datetime import timedelta
from moviepy.editor import AudioFileClip, CompositeAudioClip, ImageClip, concatenate_videoclips, CompositeVideoClip, TextClip
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
import noisereduce as nr
import numpy as np
import tempfile
import srt
from moviepy.video.VideoClip import ColorClip
import math
from moviepy.video.fx.all import resize, fadein, fadeout, speedx
from moviepy.video.fx.all import loop
import textwrap

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FOOTER_Y_FRAC = 0.89
FOOTER_X_FRAC = 0.65  # fraction across from left for footer center position
LOGO_X_FRAC = 0.2
LOGO_Y_FRAC = 0.89

# Header text box hyperparameters
HEADER_TEXT       = "THINKTOK\n뇌 깨우기"
HEADER_FONT_SIZE  = 100                     # font size for header text
HEADER_X_FRAC     = 0.50       # horizontal center fraction for header text
HEADER_Y_FRAC     = 0.07       # vertical fraction down from top for header text
HEADER_BOX_SIZE   = (1200, 220) # increased height to prevent text clipping
HEADER_BG_COLOR   = 'rgb(200,160,120)'  # darker beige for header background
HEADER_TEXT_COLOR = '#333333'               # dark gray text
HEADER_MARGIN     = 50                      # horizontal margin from edges
SUBTITLE_FONT_SIZE = 60       # consistent font size for all subtitles

def get_top_left(center_x, center_y, width, height):
    """
    Given a center coordinate and element size, returns
    the top-left coordinate for positioning.
    """
    x = int(center_x - width / 2)
    y = int(center_y - height / 2)
    return (x, y)

def compute_image_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def build_video(script_path, audio_dir, image_dir, subtitle_path, output_path, fast=False, mood="angry", skip_tts=False):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(script_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    # Extract title as header if first line starts with "#"
    global HEADER_TEXT
    if lines and lines[0].startswith("#"):
        HEADER_TEXT = lines[0][1:].strip().replace("\\n", "\n")
        lines = lines[1:]  # remove title from lines to avoid using as subtitle

    clips = []

    # Track start and end times for each video clip segment
    clip_times = []
    current_time = 0.0

    # --- Image hash-based merging logic ---
    current_hash = None
    audio_segments = []
    current_audio_paths = []
    prev_img_file = None

    # Load background music and detect beat times
    # bg_music_path = "music/hiphop_angry.mp3"
    # beat_times = []
    # if os.path.exists(bg_music_path) and librosa:
    #     print("🔊 Loading background music for analysis...")
    #     y, sr = librosa.load(bg_music_path, sr=None)
    #     print("⏳ Performing beat detection (this may take a moment)...")
    #     _, beat_frames = librosa.beat.beat_track(y=y, sr=sr, tightness=100)
    #     beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    #     print(f"✅ Beat detection completed: {len(beat_times)} beats found.")
    # else:
    #     beat_times = []
    beat_times = []  # beat effect disabled

    PADDING_AFTER_AUDIO = 0.0  # Add a slight pause after each TTS line
    for idx, line in enumerate(lines, start=1):
        # Support multiple image extensions
        img_file = None
        # Try current and previous lines down to line 1
        for fallback_idx in reversed(range(1, idx + 1)):
            for ext in (".png", ".jpg", ".jpeg"):
                candidate = os.path.join(image_dir, f"line_{fallback_idx:02}{ext}")
                if os.path.exists(candidate):
                    img_file = candidate
                    break
            if img_file:
                break
        audio_file = os.path.join(audio_dir, f"line_{idx:02}.mp3")

        missing_items = []
        if not os.path.exists(img_file):
            missing_items.append("image")
        if not os.path.exists(audio_file):
            missing_items.append("audio")
        if missing_items:
            print(f"⚠️ Skipping line {idx}: missing {', '.join(missing_items)}.")
            continue

        # --- Compute image hash and merge logic ---
        img_hash = compute_image_hash(img_file)
        if current_hash is None:
            current_hash = img_hash

        # If image changed, flush previous group
        if img_hash != current_hash:
            if current_audio_paths:
                merged = sum([AudioSegment.from_file(p) for p in current_audio_paths])
                temp_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
                merged.export(temp_audio_path, format="wav")
                audio = AudioFileClip(temp_audio_path)

                duration = audio.duration + PADDING_AFTER_AUDIO
                clip_times.append((current_time, current_time + duration))
                current_time += duration

                bg_clip = ColorClip(size=(1080, 1920), color=(240, 200, 160)).set_duration(duration)
                fg_clip = (ImageClip(prev_img_file)
                           .set_duration(duration)
                           .resize(height=1080)
                           .set_position(("center", "center")))
                shadow = ColorClip(size=fg_clip.size, color=(0, 0, 0)).set_opacity(0.5).set_duration(duration)
                shadow = shadow.set_position((15, 15))
                moving_fg = CompositeVideoClip([shadow, fg_clip], size=fg_clip.size)
                # No fade-in/out applied to avoid audio artifacts

                clip = CompositeVideoClip(
                    [bg_clip, moving_fg.set_position(("center", "center"))],
                    size=(1080, 1920)
                ).set_audio(audio).set_fps(24)
                clips.append(clip)

            current_audio_paths = []
            current_hash = img_hash

        current_audio_paths.append(audio_file)
        prev_img_file = img_file

    # --- After loop, flush remaining group if any ---
    if current_audio_paths:
        merged = sum([AudioSegment.from_file(p) for p in current_audio_paths])
        temp_audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        merged.export(temp_audio_path, format="wav")
        audio = AudioFileClip(temp_audio_path)

        duration = audio.duration + PADDING_AFTER_AUDIO
        clip_times.append((current_time, current_time + duration))
        current_time += duration

        bg_clip = ColorClip(size=(1080, 1920), color=(240, 200, 160)).set_duration(duration)
        fg_clip = (ImageClip(prev_img_file)
                   .set_duration(duration)
                   .resize(height=1080)
                   .set_position(("center", "center")))
        shadow = ColorClip(size=fg_clip.size, color=(0, 0, 0)).set_opacity(0.5).set_duration(duration)
        shadow = shadow.set_position((15, 15))
        moving_fg = CompositeVideoClip([shadow, fg_clip], size=fg_clip.size)
        # No fade-in/out applied to avoid audio artifacts

        clip = CompositeVideoClip(
            [bg_clip, moving_fg.set_position(("center", "center"))],
            size=(1080, 1920)
        ).set_audio(audio).set_fps(24)
        clips.append(clip)

    # Treat outro.mov as a regular scene clip
    outro_path = "video/outro.mov"
    if os.path.exists(outro_path):
        raw_outro = VideoFileClip(outro_path)
        raw_outro = raw_outro.resize(width=VIDEO_WIDTH)  # make square fill width
        duration_outro = raw_outro.duration
        # Background for outro
        outro_bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(240, 200, 160)).set_duration(duration_outro)
        # Composite outro on background, centered
        outro_clip = CompositeVideoClip(
            [outro_bg, raw_outro.set_position("center")],
            size=(VIDEO_WIDTH, VIDEO_HEIGHT)
        ).set_audio(raw_outro.audio).set_fps(24)
        clips.append(outro_clip)


    # Concatenate clips without padding
    final = concatenate_videoclips(clips, method="compose")

    # After concatenation, overwrite the subtitle file with new SRT based on actual video clip structure
    # Only do this if there are lines (to avoid empty SRT)

    subs = []
    line_idx = 0
    for start, end in clip_times:
        group_duration = end - start

        # Collect all audio files in this group
        group_audio_paths = []
        total_audio_duration = 0.0
        current_idx = line_idx
        while current_idx < len(lines):
            audio_path = os.path.join(audio_dir, f"line_{current_idx+1:02}.mp3")
            if not os.path.exists(audio_path):
                break
            group_audio_paths.append(audio_path)
            total_audio_duration += AudioSegment.from_file(audio_path).duration_seconds
            current_idx += 1
            # Break early if accumulated audio duration exceeds group_duration with small buffer
            if total_audio_duration >= group_duration - 0.05:
                break

        accumulated_time = start
        for i, audio_path in enumerate(group_audio_paths):
            dur = AudioSegment.from_file(audio_path).duration_seconds
            portion = (dur / total_audio_duration) * group_duration if total_audio_duration > 0 else group_duration / len(group_audio_paths)
            seg_start = accumulated_time
            seg_end = seg_start + portion
            content = lines[line_idx + i]
            subs.append(srt.Subtitle(
                index=len(subs) + 1,
                start=timedelta(seconds=seg_start),
                end=timedelta(seconds=seg_end),
                content=content
            ))
            accumulated_time = seg_end

        line_idx += len(group_audio_paths)

    with open(subtitle_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subs))

    # Enforce vertical 9:16 aspect ratio and center images
    final = final.on_color(size=(1080, 1920), color=(0, 0, 0), pos=('center', 'center'))

    def choose_random_music(mood):
        music_dir = "music"
        if mood not in ("happy", "angry"):
            return None
        candidates = [os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.startswith(mood) and f.endswith(".mp3")]
        if not candidates:
            return None
        return random.choice(candidates)

    bg_music_path = choose_random_music(mood)
    if bg_music_path and os.path.exists(bg_music_path):
        bg_clip = AudioFileClip(bg_music_path).volumex(0.1).set_duration(final.duration)
        final = final.set_audio(CompositeAudioClip([bg_clip, final.audio]))

    # Add subtitles
    if os.path.exists(subtitle_path):
        with open(subtitle_path, "r", encoding="utf-8") as f:
            srt_text = f.read()
            subs = list(srt.parse(srt_text))

            subtitles = []
            for sub in subs:
                start = sub.start.total_seconds()
                end = sub.end.total_seconds()
                duration_sub = end - start
                content = sub.content

                # Use explicit line breaks from script
                wrapped = content.replace("\\n", "\n")

                # Slide-in subtitle from above over first 0.3s
                # (previously used subtitle_pos for animation, now fixed position)
                txt_clip = (
                    TextClip(
                        wrapped,
                        font="fonts/Danjo-bold-Regular.otf",
                        fontsize=SUBTITLE_FONT_SIZE,
                        bg_color='rgba(0,0,0,0.5)',
                        color='white',
                        stroke_width=2,
                        stroke_color='black',
                        method='label'  # changed from 'caption'
                    )
                    .set_start(start)
                    .set_duration(duration_sub)
                    .set_position(('center', 1300))
                    .crossfadein(0.2)
                    .crossfadeout(0.2)
                )
                subtitles.append(txt_clip)

            final = CompositeVideoClip([final, *subtitles], size=(1080, 1920))

    # Add persistent header text box overlay
    # Modern MZ-style header: semi-transparent white bar with dark text
    header_width = VIDEO_WIDTH - HEADER_MARGIN*2
    header_height = HEADER_BOX_SIZE[1]
    header_clip = (TextClip(
                       HEADER_TEXT,
                       font="fonts/Danjo-bold-Regular.otf",
                       fontsize=HEADER_FONT_SIZE,
                       color=HEADER_TEXT_COLOR,
                       bg_color='white',
                       method="caption",
                       size=(header_width, header_height)
                   )
                   .set_duration(final.duration))
    # place header margin pixels from left, and HEADER_Y_FRAC down
    hw, hh = header_clip.size
    hy = int(VIDEO_HEIGHT * HEADER_Y_FRAC)
    hx = HEADER_MARGIN
    header_clip = header_clip.set_position((hx, hy))
    final = CompositeVideoClip([final, header_clip], size=final.size)

    # Add underline image below header
    # underline_path = "images/bottom_line.png"
    # if os.path.exists(underline_path):
    #     underline_clip = (
    #         ImageClip(underline_path)
    #         .set_duration(final.duration)
    #         .resize(width=hw * 0.9)  # 90% width of header text
    #     )
    #     uw, uh = underline_clip.size
    #     ux = hx + int((hw - uw) / 2)
    #     uy = hy + hh - int(uh * 0.5)  # move underline upward by 50% of its height
    #     underline_clip = underline_clip.set_position((ux, uy))
    #     final = CompositeVideoClip([final, underline_clip], size=final.size)

    # Add persistent footer text with beige background rectangle
    footer_bg_height = int(VIDEO_HEIGHT * 0.18)  # ~18% height of video
    # Footer text: two lines with different font sizes
    line1 = "동생이 야무지게"
    line2 = "말아줄게"
    # Halve both font sizes and scale down by factor of 1.2; adjust per requirements
    fontsize_large = int(((footer_bg_height * 0.4) / 2) * 1.1 * 1.7)
    fontsize_small = int((fontsize_large / 2) * 0.9)
    # Create TextClips
    clip1 = (
        TextClip(
            line1,
            font="fonts/Danjo-bold-Regular.otf",
            fontsize=fontsize_small,
            color=HEADER_TEXT_COLOR,  # match header text color
            bg_color='transparent',
            method="caption",
            size=(int(VIDEO_WIDTH*0.6), fontsize_small + 10)
        )
        .set_duration(final.duration)
    )
    clip2 = (
        TextClip(
            line2,
            font="fonts/Danjo-bold-Regular.otf",
            fontsize=fontsize_large,
            color=HEADER_TEXT_COLOR,  # match header text color
            bg_color='transparent',
            method="caption",
            size=(int(VIDEO_WIDTH*0.6), fontsize_large + 10)
        )
        .set_duration(final.duration)
    )
    # Footer text position
    # These will be updated after logo_clip is created, see below.
    x1 = int(VIDEO_WIDTH * 5 / 9)
    x2 = x1
    y1 = int(VIDEO_HEIGHT - VIDEO_HEIGHT * 3 / 16) + 40  # lower by 40px
    y2 = y1 + clip1.size[1]
    # Beige footer background
    # (The y1 value is used below, so must be defined before this)
    # Will be repositioned if logo exists
    # Add logo overlay, slightly right of center and aligned with first text line
    logo_path = "images/snu_ui.png"
    logo_clip = None
    if os.path.exists(logo_path):
        # Resize logo to occupy ~7.5% of footer height (half of previous), scaled down by factor of 1.2
        logo_height = int(footer_bg_height * 0.3 * 1.1 * 1.1 * 1.7)
        logo_clip = ImageClip(logo_path).resize(height=logo_height).set_duration(final.duration)
        # --- Strong navy blue tint effect ---
        from moviepy.video.fx.all import colorx
        logo_clip = logo_clip.fx(colorx, 0.4)

        
        lw, lh = logo_clip.size


        # Calculate total width: logo width + one-third logo width (gap) + text width
        total_width = lw + int(lw / 3) + int(VIDEO_WIDTH * 0.6)
        # Calculate new left x position so total group is centered
        x1 = int((VIDEO_WIDTH - total_width) / 2)
        x2 = x1
        y1 = int(VIDEO_HEIGHT - VIDEO_HEIGHT * 3 / 16) + 40  # lower by 40px
        y2 = y1 + clip1.size[1]
    # Beige footer background
    footer_bg = ColorClip(size=(VIDEO_WIDTH, footer_bg_height), color=(240, 200, 160)).set_duration(final.duration)
    footer_bg = footer_bg.set_position(("center", y1 - int(footer_bg_height * 0.2)))
    # Position footer text and logo
    clip1 = clip1.set_position((x1, y1))
    clip2 = clip2.set_position((x2, y2))
    # Ensure footer_bg is always the bottommost layer in the footer area
    if logo_clip is not None:
        # Logo position: to the right of text, with 1.2 times logo width gap
        lw, lh = logo_clip.size
        lx = x1 + int(VIDEO_WIDTH * 0.6) 
        ly = y1  # keep in sync with lowered text
        logo_clip = logo_clip.set_position((lx, ly))
        # TODO: Apply a color tint to the logo externally if needed
        final = CompositeVideoClip([final, footer_bg, clip1, clip2, logo_clip], size=final.size)
    else:
        final = CompositeVideoClip([final, footer_bg, clip1, clip2], size=final.size)

    if fast:
        # faster build: lower fps and use ultrafast preset
        final.write_videofile(
            output_path,
            fps=12,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=8
        )
    else:
        final.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build video from script, images, audio, and subtitles")
    parser.add_argument("--script-path", default="scripts/hotel_economics.txt", help="Path to the script file")
    parser.add_argument("--audio-dir", default="audio/hotel_economics", help="Directory containing mp3 files")
    parser.add_argument("--image-dir", default="images", help="Directory containing image files")
    parser.add_argument("--subtitle-path", default="subtitles/hotel_economics.srt", help="Path to the SRT subtitle file")
    parser.add_argument("--output-path", default="video/hotel_economics.mp4", help="Output video file path")
    parser.add_argument("--fast", action="store_true", help="Use faster build settings (lower FPS, ultrafast preset)")
    parser.add_argument("--mood", choices=["happy", "angry"], default="angry", help="Select background music mood")
    parser.add_argument("--skip-tts", action="store_true", help="Use existing audio files without TTS generation")
    args = parser.parse_args()

    build_video(
        script_path=args.script_path,
        audio_dir=args.audio_dir,
        image_dir=args.image_dir,
        subtitle_path=args.subtitle_path,
        output_path=args.output_path,
        fast=args.fast,
        mood=args.mood,
        skip_tts=args.skip_tts
    )