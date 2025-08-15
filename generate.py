# =============================================================================
# generate.py - Full ThinkTok generation pipeline
#
# Usage:
#   python generate.py --script <script.txt> [--output-dir <dir>] [--generate-images] [--fast] [--mood <mood>] [--skip-tts] [--speed-factor <factor>] [--rate <rate>] [--pitch <pitch>]
#
# Arguments:
#   --script         Path to the script text file (one sentence per line)
#   --output-dir     Base output directory (ignored; outputs go to root audio/, images/, subtitles/, video/)
#   --generate-images  Generate images (off by default)
#   --fast           Enable fast video mode (speed up to fit 59s)
#   --mood           Background music mood ("happy" or "angry")
#   --pitch          Set pitch for TTS voice (e.g., -2.0 or +2.0)
#   --skip-tts       Use existing audio files without TTS
#   --speed-factor   Apply global speed adjustment (e.g., 0.97 to shorten duration)
#   --rate           Speaking rate for TTS (e.g., 1.0 = normal speed)
#
# Examples:
#   python generate.py --script scripts/test.txt
#   python generate.py --script scripts/test.txt --generate-images --fast --mood happy
#   python generate.py --script scripts/test.txt --rate 1.1 --pitch 1.0 --skip-tts
# =============================================================================

import os
import argparse
from tts_generator import generate_tts_for_script
from subtitle_generator import generate_subtitles
from image_generator import generate_images_for_script
try:
    from video_builder import build_video
except ModuleNotFoundError:
    build_video = None

def main():
    parser = argparse.ArgumentParser(description="Full ThinkTok generation pipeline.")
    parser.add_argument("--script", required=True, help="Path to the script text file")
    parser.add_argument("--output-dir", default="output", help="Base output directory")
    parser.add_argument("--generate-images", action="store_true", help="Generate images (off by default)")
    parser.add_argument("--fast", action="store_true", help="Enable fast video mode (speed up to fit 59s)")
    parser.add_argument("--mood", choices=["happy", "angry"], default="angry", help="Background music mood")
    parser.add_argument("--rate", type=float, default=1.2, help="Speaking rate for TTS (1.0 = normal speed)")
    parser.add_argument("--pitch", type=float, default=0.0, help="Set pitch for TTS voice (e.g., -2.0 or +2.0)")
    parser.add_argument("--skip-tts", action="store_true", help="Use existing audio files without TTS generation")
    parser.add_argument("--speed-factor", type=float, default=1.0, help="Apply global speed factor to final video (e.g., 0.97)")
    args = parser.parse_args()

    script_path = args.script
    name = os.path.splitext(os.path.basename(script_path))[0]

    # Always use root-level folders
    audio_dir = os.path.join("audio", name)
    subtitles_dir = "subtitles"
    subtitles_path = os.path.join(subtitles_dir, f"{name}.srt")
    images_dir = os.path.join("images", name)
    video_dir = "video"
    video_path = os.path.join(video_dir, f"{name}.mp4")

    # Create root-level directories
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(subtitles_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(video_dir, exist_ok=True)

    # 1) TTS generation (can be skipped with --skip-tts)
    if args.skip_tts:
        print("▶ Skipping TTS generation (using pre-recorded audio)...")
    else:
        print("▶ Generating TTS...")
        generate_tts_for_script(
            script_path,
            output_dir=audio_dir,
            mood=args.mood,
            speaking_rate=args.rate,
            pitch=args.pitch
        )

    # 2) Subtitle generation
    print("▶ Generating subtitles...")
    generate_subtitles(script_path, audio_dir=audio_dir, output_path=subtitles_path)

    # 3) Image generation (optional, off by default)
    if args.generate_images:
        print("▶ Generating images...")
        generate_images_for_script(script_path, output_dir=images_dir)
    else:
        print("▶ Skipping image generation.")


    # 4) Video building
    if build_video is None:
        print("⚠️ video_builder module not available. Install moviepy to enable video generation.")
    else:
        print("▶ Building video...")
        build_video(
            script_path=script_path,
            audio_dir=audio_dir,
            image_dir=images_dir,
            subtitle_path=subtitles_path,
            output_path=video_path,
            fast=args.fast,
            mood=args.mood,
            skip_tts=args.skip_tts
        )
        print(f"✅ Pipeline completed. Video saved to {video_path}")

if __name__ == "__main__":
    main()