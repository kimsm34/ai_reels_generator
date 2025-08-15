import os
from moviepy.editor import AudioFileClip
import argparse
from dotenv import load_dotenv
load_dotenv()

"""
Usage examples:
    python subtitle_generator.py --script scripts/hotel_economics.txt --audio-dir audio --output-path subtitles/hotel_economics.srt
"""

def generate_subtitles(script_path, audio_dir="audio", output_path="subtitles/output.srt"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(script_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    if lines and lines[0].startswith("#"):
        lines = lines[1:]  # Skip title line

    srt_entries = []
    current_time = 0.0

    def format_time(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    for idx, line in enumerate(lines, start=1):
        line = line.replace("\n", "\n")  # Ensure line breaks are respected directly

        audio_file = os.path.join(audio_dir, f"line_{idx:02}.mp3")
        audio = AudioFileClip(audio_file)
        duration_sec = audio.duration

        start_time = current_time
        end_time = current_time + duration_sec
        current_time = end_time

        srt_entry = f"{idx}\n{format_time(start_time)} --> {format_time(end_time)}\n{line}\n"
        srt_entries.append(srt_entry)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))

    print(f"✅ Subtitles written to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate SRT subtitles from script and audio files")
    parser.add_argument("--script", default="scripts/hotel_economics.txt", help="Path to the script file")
    parser.add_argument("--audio-dir", default="audio", help="Directory containing mp3 files")
    parser.add_argument("--output-path", default="subtitles/hotel_economics.srt", help="Path to save the SRT file")
    args = parser.parse_args()
    generate_subtitles(args.script, audio_dir=args.audio_dir, output_path=args.output_path)