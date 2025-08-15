import os
import sys
import whisper
from pydub import AudioSegment

def split_audio_by_script(audio_path):
    # Load whisper model
    model = whisper.load_model("base")

    # Transcribe the audio file
    print(f"🔍 Transcribing: {audio_path}")
    result = model.transcribe(audio_path, word_timestamps=False)
    segments = result.get("segments", [])

    # Load the audio as a pydub segment
    audio = AudioSegment.from_file(audio_path)
    base_dir = os.path.dirname(audio_path)

    # Split and export each segment
    for i, seg in enumerate(segments, start=1):
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)
        chunk = audio[start_ms:end_ms]

        out_path = os.path.join(base_dir, f"line_{i:02}.mp3")
        chunk.export(out_path, format="mp3")
        print(f"✅ Saved: {out_path}")

    print("✅ All segments exported.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python split_audio_by_script.py path/to/audio.mp3")
        sys.exit(1)

    audio_file = sys.argv[1]
    if not os.path.isfile(audio_file):
        print(f"❌ File not found: {audio_file}")
        sys.exit(1)

    split_audio_by_script(audio_file)