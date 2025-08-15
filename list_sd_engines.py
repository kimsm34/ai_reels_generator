import os
import requests
from dotenv import load_dotenv
from stability_sdk import client

# .env에서 키 로드
load_dotenv()
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
if not STABILITY_API_KEY:
    raise RuntimeError("STABILITY_API_KEY 환경변수 설정 필요")

# Stability 클라이언트 초기화 (engine은 임시로 비워둬도 됩니다)
stability_api = client.StabilityInference(
    key=STABILITY_API_KEY,
    engine="stable-diffusion-512-v2-1",  # 실제로 존재하지 않아도 OK
    verbose=False,
)

# 사용 가능한 엔진 리스트 조회 via HTTP API
headers = {"Authorization": f"Bearer {STABILITY_API_KEY}"}
response = requests.get("https://api.stability.ai/v1/engines/list", headers=headers)
response.raise_for_status()
engines = response.json()  # response is a list of engine objects
print("===== Available Stability AI Engines =====")
for engine in engines:
    print("-", engine.get("id", engine.get("name")))