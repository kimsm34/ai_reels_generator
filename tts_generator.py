import os
from google.cloud import texttospeech
import argparse
from dotenv import load_dotenv
from mutagen.mp3 import MP3
load_dotenv()

def generate_tts_for_script(script_path, output_dir="audio", speaking_rate=1.2, pitch=0.0, mood="happy"):
    os.makedirs(output_dir, exist_ok=True)

    client = texttospeech.TextToSpeechClient()

    if mood == "happy":
        voice_name = "ko-KR-Chirp3-HD-Achird"
    elif mood == "angry":
        voice_name = "ko-KR-Chirp3-HD-Schedar"
    else:
        voice_name = "ko-KR-Chirp3-HD-Achird"

    with open(script_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    if lines and lines[0].startswith("#"):
        lines = lines[1:]  # Skip the first line if it's a title

    for idx, line in enumerate(lines, start=1):
        line = line.replace("\\n", " ").replace("\n", " ")  # remove both literal and actual line breaks for TTS
        print(f"🎤 Generating TTS for line {idx}: {line[:30]}...")

        synthesis_input = texttospeech.SynthesisInput(text=line)

        voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            name=voice_name,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch
        )

        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        filename = f"line_{idx:02}.mp3"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "wb") as out:
            out.write(response.audio_content)

        audio = MP3(filepath)
        print(f"📏 Duration of line {idx}: {audio.info.length:.2f} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate TTS mp3 files for a script")
    parser.add_argument("--script", default="scripts/hotel_economics.txt", help="Path to the script file")
    parser.add_argument("--output-dir", default="audio", help="Directory to save mp3 files")
    parser.add_argument("--rate", type=float, default=1.2, help="Speaking rate, e.g. 1.1 for 10% faster")
    parser.add_argument("--pitch", type=float, default=0.0, help="Pitch offset for TTS voice (e.g. +2.0 or -2.0)")
    parser.add_argument("--mood", default="happy", help="Mood for voice selection, e.g. happy or angry")
    args = parser.parse_args()
    generate_tts_for_script(
        args.script,
        output_dir=args.output_dir,
        mood=args.mood,
        speaking_rate=args.rate,
        pitch=args.pitch
    )
