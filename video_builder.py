def detect_leading_silence(sound, silence_threshold=-40.0, chunk_size=10):
    trim_ms = 0
    while trim_ms < len(sound):
        if sound[trim_ms:trim_ms + chunk_size].dBFS > silence_threshold:
            break
        trim_ms += chunk_size
    return trim_ms
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
HEADER_MARGIN     = 50                      # horizontal margin from edges
SUBTITLE_FONT_SIZE = 60       # consistent font size for all subtitles

# Offsets for title and subtitle relative to image area
IMAGE_SIZE = VIDEO_WIDTH  # since image resized to height=VIDEO_WIDTH
IMAGE_TOP = (VIDEO_HEIGHT - IMAGE_SIZE) // 2
TITLE_OFFSET = 20        # pixels above image for title
SUBTITLE_OFFSET = 20     # pixels below image for subtitle

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
    from moviepy.editor import concatenate_audioclips

    # Prepare list to hold all SFX clips
    sfx_clips = []

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
            # --- Insert intro SFX before adding very first clip ---
            intro_sfx_path = "sound_effect/intro.mp3"
            if os.path.exists(intro_sfx_path):
                intro_sfx = AudioFileClip(intro_sfx_path).set_start(0).volumex(0.32)
                sfx_clips.append(intro_sfx)

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

                bg_clip = ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_duration(duration)
                # Load the square image and resize so its width matches VIDEO_WIDTH (1080)
                fg = ImageClip(prev_img_file).set_duration(duration).resize(width=VIDEO_WIDTH)
                w, h = fg.size

                # Crop 10% from top and 10% from bottom
                crop_top = int(h * 0.10)
                crop_bottom = h - crop_top
                fg = fg.crop(x1=0, y1=crop_top, x2=w, y2=crop_bottom)
                h = crop_bottom - crop_top
                # Center the cropped image both horizontally and vertically
                fg_clip = fg.set_position(("center", "center"))

                shadow = ColorClip(size=fg_clip.size, color=(0, 0, 0)).set_opacity(0.5).set_duration(duration)
                shadow = shadow.set_position((15, 15))
                moving_fg = CompositeVideoClip([shadow, fg_clip], size=fg_clip.size)
                # No fade-in/out applied to avoid audio artifacts

                clip = CompositeVideoClip(
                    [bg_clip, moving_fg.set_position(("center", "center"))],
                    size=(1080, 1920)
                ).set_audio(audio).set_fps(24)
                clips.append(clip)

                # Add transition SFX between clips, after every scene group except the very last
                if len(clips) >= 1:
                    trans_candidates = [
                        "sound_effect/trans_1.mp3",
                        "sound_effect/trans_2.mp3",
                        "sound_effect/trans_3.mp3",
                        "sound_effect/trans_4.mp3",
                        "sound_effect/trans_5.mp3"
                    ]
                    import random
                    trans_sfx = random.choice([p for p in trans_candidates if os.path.exists(p)])
                    if trans_sfx:
                        sfx_seg = AudioSegment.from_file(trans_sfx)
                        # Normalize to target dBFS
                        target_dBFS = -20.0
                        change_in_dBFS = target_dBFS - sfx_seg.dBFS
                        sfx_seg = sfx_seg.apply_gain(change_in_dBFS)
                        leading_silence = detect_leading_silence(sfx_seg) / 1000.0
                        temp_sfx_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
                        sfx_seg.export(temp_sfx_path, format="mp3")
                        sfx = AudioFileClip(temp_sfx_path).set_start(current_time - leading_silence).volumex(0.32)
                        sfx_clips.append(sfx)

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

        bg_clip = ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_duration(duration)
        # Load the square image and resize so its width matches VIDEO_WIDTH (1080)
        fg = ImageClip(prev_img_file).set_duration(duration).resize(width=VIDEO_WIDTH)
        w, h = fg.size

        # Crop 10% from top and 10% from bottom
        crop_top = int(h * 0.10)
        crop_bottom = h - crop_top
        fg = fg.crop(x1=0, y1=crop_top, x2=w, y2=crop_bottom)
        h = crop_bottom - crop_top
        # Center the cropped image both horizontally and vertically
        fg_clip = fg.set_position(("center", "center"))

        shadow = ColorClip(size=fg_clip.size, color=(0, 0, 0)).set_opacity(0.5).set_duration(duration)
        shadow = shadow.set_position((15, 15))
        moving_fg = CompositeVideoClip([shadow, fg_clip], size=fg_clip.size)
        # No fade-in/out applied to avoid audio artifacts

        clip = CompositeVideoClip(
            [bg_clip, moving_fg.set_position(("center", "center"))],
            size=(1080, 1920)
        ).set_audio(audio).set_fps(24)
        clips.append(clip)

        # (Transition SFX before outro REMOVED as requested)
        # Transition SFX logic removed as requested

    # Treat outro.mov as a regular scene clip
    # outro_path = "video/outro.mov"
    # if os.path.exists(outro_path):
    #     raw_outro = VideoFileClip(outro_path)
    #     raw_outro = raw_outro.resize(width=VIDEO_WIDTH)  # make square fill width
    #     duration_outro = raw_outro.duration
    #     # Background for outro
    #     outro_bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(0, 0, 0)).set_duration(duration_outro)
    #     # Composite outro on background, centered
    #     outro_clip = CompositeVideoClip(
    #         [outro_bg, raw_outro.set_position("center")],
    #         size=(VIDEO_WIDTH, VIDEO_HEIGHT)
    #     ).set_audio(raw_outro.audio).set_fps(24)
    #     clips.append(outro_clip)


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

    # Skip background music, use only main audio and SFX
    if sfx_clips:
        if final.audio:
            all_audio = [final.audio, *sfx_clips]
        else:
            all_audio = sfx_clips
        final = final.set_audio(CompositeAudioClip(all_audio))

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

                # Subtitle style: transparent bg, yellow text, thinner stroke, positioned directly below cropped image
                # Compute actual cropped image height (1:0.8 of IMAGE_SIZE)
                h_img = int(IMAGE_SIZE * 0.8)
                image_top = int((VIDEO_HEIGHT - h_img) / 2)
                subtitle_fontsize = int((SUBTITLE_FONT_SIZE / 2) * 1.69)
                subtitle_y = image_top + h_img + SUBTITLE_OFFSET
                txt_clip = (
                    TextClip(
                        wrapped,
                        font="fonts/title_2.otf",
                        fontsize=subtitle_fontsize,
                        bg_color='rgba(0,0,0,0.0)',  # transparent background
                        color='yellow',
                        stroke_width=1,
                        stroke_color='black',
                        method='label'
                    )
                    .set_start(start)
                    .set_duration(duration_sub)
                    .set_position(('center', subtitle_y))
                    .crossfadein(0.2)
                    .crossfadeout(0.2)
                )
                subtitles.append(txt_clip)

            final = CompositeVideoClip([final, *subtitles], size=(1080, 1920))

    # Overlay fixed text "야무진 동생" at Y = 4 * font size from the top
    top_fontsize = 50
    # Move “야무진 동생” down by four times its font size from the top
    top_text_y = top_fontsize * 4
    top_text_clip = TextClip(
        "야무진 동생",
        font="fonts/design.otf",
        fontsize=top_fontsize,
        color="white",
        method="caption",
        size=(VIDEO_WIDTH, None)
    ).set_duration(final.duration).set_position(("center", top_text_y))
    final = CompositeVideoClip([final, top_text_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT))

    # Overlay title above the image, calculating height from line count
    if HEADER_TEXT:
        title_fontsize = int((IMAGE_TOP * 0.2) * 0.7 * 1.3)
        # Calculate number of lines in HEADER_TEXT
        lines = HEADER_TEXT.count("\n") + 1
        title_height = title_fontsize * lines
        title_y = IMAGE_TOP - title_height + title_fontsize
        title_clip = TextClip(
            HEADER_TEXT,
            font="fonts/title_2.otf",
            fontsize=title_fontsize,
            color="white",
            method="caption",
            size=(VIDEO_WIDTH - 40, None)
        ).set_duration(current_time).set_position(("center", title_y))
        final = CompositeVideoClip([final, title_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT))

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
