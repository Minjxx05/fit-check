# app.py
import os
import json
from datetime import datetime, timedelta

import requests
import streamlit as st
import pandas as pd

# =============================
# Page Config
# =============================
st.set_page_config(page_title="AI 습관 트래커", page_icon="📊", layout="wide")
st.title("📊 AI 습관 트래커")
st.caption("습관 · 기분 · 날씨 · AI 코치 리포트")

# =============================
# Sidebar - API Keys
# =============================
with st.sidebar:
    st.header("🔐 API 설정")
    openai_key_input = st.text_input("OpenAI API Key", type="password")
    weather_key_input = st.text_input("OpenWeatherMap API Key", type="password")
    use_env = st.checkbox("Secrets / 환경변수 사용", value=True)

def get_key(name, sidebar_value):
    if sidebar_value:
        return sidebar_value
    if use_env:
        if name in st.secrets:
            return st.secrets[name]
        return os.getenv(name)
    return None

OPENAI_API_KEY = get_key("OPENAI_API_KEY", openai_key_input)
OPENWEATHER_API_KEY = get_key("OPENWEATHER_API_KEY", weather_key_input)

# =============================
# External APIs
# =============================
def get_weather(city, api_key):
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "q": city,
                "appid": api_key,
                "units": "metric",
                "lang": "kr",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            "city": city,
            "temp": d["main"]["temp"],
            "desc": d["weather"][0]["description"],
        }
    except Exception:
        return None

def get_dog_image():
    try:
        r = requests.get("https://dog.ceo/api/breeds/image/random", timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        url = data.get("message")
        breed = "알 수 없음"
        if "/breeds/" in url:
            breed = url.split("/breeds/")[1].split("/")[0].replace("-", " ")
        return {"url": url, "breed": breed}
    except Exception:
        return None

def generate_report(habits, mood, weather, dog, style, api_key):
    if not api_key:
        return None

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    system_prompts = {
        "스파르타 코치": "너는 엄격하고 직설적인 스파르타 코치다.",
        "따뜻한 멘토": "너는 따뜻하고 공감하는 멘토다.",
        "게임 마스터": "너는 RPG 게임 마스터다.",
    }

    payload = {
        "기분": mood,
        "완료습관": [k for k, v in habits.items() if v],
        "미완료습관": [k for k, v in habits.items() if not v],
        "날씨": weather,
        "강아지품종": dog["breed"] if dog else None,
    }

    user_prompt = (
        "다음 데이터를 기반으로 컨디션 리포트를 작성해줘.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n출력 형식:\n"
          "1) 컨디션 등급(S~D)\n"
          "2) 습관 분석\n"
          "3) 날씨 코멘트\n"
          "4) 내일 미션 3개\n"
          "5) 오늘의 한마디"
    )

    try:
        res = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompts[style]},
                {"role": "user", "content": user_prompt},
            ],
        )
        return res.choices[0].message.content
    except Exception:
        return None

# =============================
# Session State
# =============================
if "history" not in st.session_state:
    st.session_state.history = []

# =============================
# Habit UI
# =============================
habits_def = {
    "⏰ 기상 미션": False,
    "💧 물 마시기": False,
    "📚 공부/독서": False,
    "🏃 운동하기": False,
    "🛌 수면": False,
}

st.subheader("✅ 오늘의 습관")
c1, c2 = st.columns(2)

habits = {}
for i, (k, _) in enumerate(habits_def.items()):
    with (c1 if i % 2 == 0 else c2):
        habits[k] = st.checkbox(k)

mood = st.slider("😊 오늘 기분", 1, 10, 6)

city = st.selectbox(
    "🌍 도시",
    ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju", "Ulsan", "Suwon", "Jeju", "Sejong"],
)

style = st.radio(
    "🎭 코치 스타일",
    ["스파르타 코치", "따뜻한 멘토", "게임 마스터"],
)

# =============================
# Metrics
# =============================
checked = sum(habits.values())
rate = int(checked / len(habits) * 100)

m1, m2, m3 = st.columns(3)
m1.metric("달성률", f"{rate}%")
m2.metric("완료 습관", f"{checked}/5")
m3.metric("기분", f"{mood}/10")

# =============================
# Chart
# =============================
today = datetime.now().date()
data = []

for i in range(6, 0, -1):
    data.append(
        {"date": today - timedelta(days=i), "rate": [50, 60, 40, 70, 80, 55][6 - i]}
    )

data.append({"date": today, "rate": rate})

df = pd.DataFrame(data).set_index("date")
st.bar_chart(df)

# =============================
# Generate Report
# =============================
st.divider()
if st.button("🧠 컨디션 리포트 생성", type="primary"):
    weather = get_weather(city, OPENWEATHER_API_KEY)
    dog = get_dog_image()

    report = generate_report(
        habits=habits,
        mood=mood,
        weather=weather,
        dog=dog,
        style=style,
        api_key=OPENAI_API_KEY,
    )

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("🌦️ 날씨")
        if weather:
            st.info(f"{weather['city']} · {weather['desc']} · {weather['temp']}℃")
        else:
            st.warning("날씨 정보 없음")

    with c2:
        st.subheader("🐶 강아지")
        if dog:
            st.image(dog["url"], use_container_width=True)
            st.caption(dog["breed"])
        else:
            st.warning("강아지 이미지 없음")

    st.subheader("📋 AI 리포트")
    if report:
        st.markdown(report)
    else:
        st.error("리포트 생성 실패 (API Key 확인)")

# =============================
# API Guide
# =============================
with st.expander("ℹ️ API 안내"):
    st.markdown(
        "- OpenAI / OpenWeatherMap 키 필요\n"
        "- Streamlit Cloud에서는 Secrets 사용 권장\n"
        "- 외부 API는 timeout=10, 실패 시 자동 무시"
    )
