import os
import openai
from dotenv import load_dotenv
import time
import concurrent.futures
import argparse
from PIL import Image
from io import BytesIO
import io
import requests
import base64

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
if not STABILITY_API_KEY:
    raise RuntimeError("STABILITY_API_KEY not set in environment")
API_HOST = "https://api.stability.ai"
ENGINE_ID = "stable-diffusion-v1-6"

# GPT model
MODEL = "gpt-4o-mini"
# Image model (use "dall-e-2" for lower cost, or "dall-e-3" for quality)
IMAGE_MODEL = "dall-e-2"

# Image style and size
SIMPSONS_STYLE = "in the style of The Simpsons"
IMAGE_SIZE = "1024x1024"
BG_COLOR = (255, 224, 189, 255)  # yellow background RGBA
bg_w, bg_h = map(int, IMAGE_SIZE.split('x'))

USER_TEMPLATE = (
    "심플한 심슨스타일, 노란색 배경, 불필요한 요소 제외\n\n"
    "{line} 사진 만들어줘"
)

def generate_images_for_script(script_path, output_dir="images"):
    os.makedirs(output_dir, exist_ok=True)

    with open(script_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    def process_line(idx, line):
        try:
            # 1) Generate English base prompt from the script line
            for attempt in range(3):
                try:
                    eng_resp = openai.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": "You are an assistant that translates a Korean instruction into an English DALL·E prompt."},
                            {"role": "user", "content": f'Translate the following into an English prompt for DALL·E: "{line}"'}
                        ],
                        temperature=0.3,
                        max_tokens=60
                    )
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    time.sleep(1)
            base_prompt = eng_resp.choices[0].message.content.strip().strip('"')
            # 2) Append Korean style guide
            prompt = f"{base_prompt} simple flat Simpson cartoon style, yellow background, unnecessary elements excluded"
            print(f"🖼️ GPT prompt for image {idx}: {prompt}")

            # Call Stability REST API
            url = f"{API_HOST}/v1/generation/{ENGINE_ID}/text-to-image"
            payload = {
                "text_prompts": [{"text": prompt}],
                "cfg_scale": 7,
                "samples": 1,
                "width": bg_w,
                "height": bg_h,
                "steps": 30,
            }
            headers = {
                "Authorization": f"Bearer {STABILITY_API_KEY}",
                "Content-Type": "application/json"
            }
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            # The first artifact contains base64 image data
            base64_img = data["artifacts"][0]["base64"]
            image_data = base64.b64decode(base64_img)

            # Composite on yellow background
            with Image.open(BytesIO(image_data)).convert("RGBA") as fg:
                # Create background
                bg = Image.new("RGBA", (bg_w, bg_h), BG_COLOR)
                # Center the foreground
                x = (bg_w - fg.width) // 2
                y = (bg_h - fg.height) // 2
                bg.paste(fg, (x, y), fg)
                # Save final image
                final_buffer = BytesIO()
                bg.save(final_buffer, format="PNG")
                final_bytes = final_buffer.getvalue()

            filename = f"line_{idx:02}.png"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(final_bytes)

        except Exception as e:
            print(f"❌ Failed to generate image for line {idx}: {e}")

    # Use ThreadPoolExecutor to parallelize
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_line, idx, line) for idx, line in enumerate(lines, start=1)]
        for future in concurrent.futures.as_completed(futures):
            pass  # we already print inside process_line

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate images for a script via ChatGPT+DALL·E")
    parser.add_argument("--script", required=True, help="Path to the script text file")
    parser.add_argument("--output-dir", default="images", help="Base output directory")
    args = parser.parse_args()
    generate_images_for_script(args.script, args.output_dir)