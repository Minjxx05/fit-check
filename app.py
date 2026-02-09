# app.py
import os
import json
from datetime import datetime, timedelta

import requests
import streamlit as st
import pandas as pd

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(page_title="AI 습관 트래커", page_icon="📊", layout="wide")

st.title("📊 AI 습관 트래커")
st.caption("오늘의 습관을 체크하고, 날씨/강아지와 함께 AI 코치 리포트를 받아보세요.")

# -----------------------------
# Sidebar: API Keys
# -----------------------------
with st.sidebar:
    st.header("🔐 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
    weather_key = st.text_input("OpenWeatherMap API Key", type="password", placeholder="xxxx...")

    st.divider()
    st.subheader("⚙️ 옵션")
    use_env = st.checkbox("환경변수/Secrets 키도 사용하기", value=True, help="Streamlit Cloud에서는 Secrets를 권장해요.")

def get_key(name: str, sidebar_value: str, allow_env: bool = True) -> str | None:
    """우선순위: sidebar 입력 > st.secrets > env"""
    if sidebar_value:
        return sidebar_value.strip()
    if allow_env:
        if name in st.secrets:
            return str(st.secrets.get(name)).strip()
        v = os.getenv(name)
        if v:
            return v.strip()
    return None

OPENAI_API_KEY = get_key("OPENAI_API_KEY", openai_key, use_env)
OPENWEATHER_API_KEY = get_key("OPENWEATHER_API_KEY", weather_key, use_env)

# -----------------------------
# Utilities: API calls
# -----------------------------
def get_weather(city: str, api_key: str | None):
    """
    OpenWeatherMap에서 현재 날씨 가져오기 (한국어, 섭씨)
    실패 시 None 반환, timeout=10
    """
    if not api_key:
        return None
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric",
            "lang": "kr",
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        return {
            "city": city,
            "temp": data.get("main", {}).get("temp"),
            "feels_like": data.get("main", {}).get("feels_like"),
            "humidity": data.get("main", {}).get("humidity"),
            "desc": (data.get("weather") or [{}])[0].get("description"),
        }
    except Exception:
        return None


def get_dog_image():
    """
    Dog CEO에서 랜덤 강아지 사진 URL과 품종 가져오기
    실패 시 None 반환, timeout=10
    """
    try:
        r = requests.get("https://dog.ceo/api/breeds/image/random", timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("status") != "success":
            return None
        url = data.get("message")
        breed = None

        # URL 예: https://images.dog.ceo/breeds/hound-afghan/n02088094_1003.jpg
        try:
            parts = url.split("/breeds/")[1].split("/")
            breed_slug = parts[0]  # hound-afghan
            breed = breed_slug.replace("-", " ")
        except Exception:
            breed = None

        return {"url": url, "breed": breed}
    except Exception:
        return None


def generate_report(
    *,
    habits: dict,
    mood: int,
    weather: dict | None,
    dog: dict | None,
    coach_style: str,
    api_key: str | None,
):
    """
    습관+기분+날씨+강아지 품종을 모아서 OpenAI에 전달해 리포트 생성
    - 모델: gpt-5-mini
    - 코치 스타일별 시스템 프롬프트
    - 실패 시 None 반환
    """
    if not api_key:
        return None

    style_prompts = {
        "스파르타 코치": "너는 엄격하고 직설적인 스파르타 코치다. 변명은 허용하지 않는다. 짧고 강하게, 실행 중심으로 피드백하라.",
        "따뜻한 멘토": "너는 따뜻하고 공감하는 멘토다. 사용자의 작은 성취를 인정하고, 부담 없이 지속 가능한 제안을 하라.",
        "게임 마스터": "너는 RPG 게임 마스터다. 사용자를 플레이어로 보고, 퀘스트/보상/레벨업 말투로 동기부여하라. 재밌고 구체적으로!",
    }

    system = style_prompts.get(coach_style, style_prompts["따뜻한 멘토"])

    checked = [k for k, v in habits.items() if v]
    unchecked = [k for k, v in habits.items() if not v]

    payload = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "mood": mood,
        "checked_habits": checked,
        "unchecked_habits": unchecked,
        "weather": weather or None,
        "dog_breed": (dog or {}).get("breed"),
    }

    user_prompt = f"""
아래 데이터를 바탕으로 'AI 습관 트래커' 컨디션 리포트를 작성해줘.

[입력 데이터(JSON)]
{json.dumps(payload, ensure_ascii=False, indent=2)}

[출력 형식 - 반드시 이 순서/라벨 유지]
1) 컨디션 등급: (S/A/B/C/D 중 하나)
2) 습관 분석: (오늘 잘한 점 2개 + 아쉬운 점 2개 + 바로 실천 팁 2개)
3) 날씨 코멘트: (날씨가 없으면 '날씨 정보를 불러오지 못했어요' 포함)
4) 내일 미션: (3개, 체크박스처럼 '- [ ]' 포맷)
5) 오늘의 한마디: (한 문장, 임팩트 있게)

추가 규칙:
- 습관 이름은 한국어로 자연스럽게.
- 기분(1~10)을 반드시 언급하고, 과하게 길지 않게.
"""

    try:
        # OpenAI Python SDK (>=1.0.0) 사용
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt.strip()},
            ],
        )
        return resp.choices[0].message.content
    except Exception:
        return None


# -----------------------------
# Session State: history
# -----------------------------
if "history" not in st.session_state:
    st.session_state.history = []

# -----------------------------
# Habit Check-in UI
# -----------------------------
habit_defs = [
    ("기상 미션", "⏰"),
    ("물 마시기", "💧"),
    ("공부/독서", "📚"),
    ("운동하기", "🏃"),
    ("수면", "🛌"),
]

cities = ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon", "Gwangju", "Suwon", "Ulsan", "Jeju", "Sejong"]
coach_styles = ["스파르타 코치", "따뜻한 멘토", "게임 마스터"]

st.subheader("✅ 오늘의 습관 체크인")

left, right = st.columns([1.2, 1])

with left:
    st.markdown("#### 🗒️ 습관 체크")
    c1, c2 = st.columns(2)

    habits = {}
    for i, (name, emo) in enumerate(habit_defs):
        col = c1 if i % 2 == 0 else c2
        with col:
            habits[name] = st.checkbox(f"{emo} {name}", value=False)

    st.markdown("#### 😊 기분")
    mood = st.slider("오늘 기분은 어때요? (1=최악, 10=최고)", min_value=1, max_value=10, value=6)

with right:
    st.markdown("#### 🌍 도시 & 🎭 코치 스타일")
    city = st.selectbox("도시 선택", cities, index=0)
    coach_style = st.radio("코치 스타일", coach_styles, index=1)

# -----------------------------
# Metrics & Chart (7-day)
# -----------------------------
checked_count = sum(1 for v in habits.values() if v)
total_habits = len(habits)
achievement = int(round((checked_count / total_habits) * 100))

m1, m2, m3 = st.columns(3)
m1.metric("달성률", f"{achievement}%")
m2.metric("달성 습관", f"{checked_count}/{total_habits}")
m3.metric("기분", f"{mood}/10")

st.divider()
st.subheader("📈 최근 7일 기록")

# demo 6 days + today
today = datetime.now().date()
demo_days = [today - timedelta(days=i) for i in range(6, 0, -1)]  # 6 days ago .. yesterday
demo_values = [50, 60, 40, 80, 70, 55]  # demo achievement %

# If we already have history, use it to build last 7 days
def normalize_history(history_list):
    # keep only last 30
    if len(history_list) > 30:
        history_list = history_list[-30:]
    # dict date->record (latest wins)
    m = {}
    for rec in history_list:
        m[rec["date"]] = rec
    return m

hist_map = normalize_history(st.session_state.history)

rows = []
for d, v in zip(demo_days, demo_values):
    ds = d.strftime("%Y-%m-%d")
    if ds in hist_map:
        rows.append({"date": ds, "achievement": hist_map[ds]["achievement"], "mood": hist_map[ds]["mood"]})
    else:
        rows.append({"date": ds, "achievement": v, "mood": None})

today_s = today.strftime("%Y-%m-%d")
rows.append({"date": today_s, "achievement": achievement, "mood": mood})

df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date")

st.bar_chart(df.set_index("date")[["achievement"]])

# Save today's data in session_state (not automatically; do on button to avoid spam)
st.caption("기록은 세션 동안 저장됩니다(새로고침/재실행 시 초기화될 수 있어요).")

# -----------------------------
# Result: Weather + Dog + AI report
# -----------------------------
st.divider()
st.subheader("🧠 AI 코치 리포트")

btn_col1, btn_col2 = st.columns([1, 2])
with btn_col1:
    gen = st.button("컨디션 리포트 생성", type="primary", use_container_width=True)

if gen:
    # store today's record
    st.session_state.history.append(
        {
            "date": today_s,
            "habits": habits,
            "achievement": achievement,
            "mood": mood,
            "city": city,
            "coach_style": coach_style,
        }
    )

    # Fetch external data
    weather = get_weather(city, OPENWEATHER_API_KEY)
    dog = get_dog_image()

    # Generate AI report
    report = generate_report(
        habits=habits,
        mood=mood,
        weather=weather,
        dog=dog,
        coach_style=coach_style,
        api_key=OPENAI_API_KEY,
    )

    # Two-column cards
    wcol, dcol = st.columns(2)

    with wcol:
        st.markdown("#### 🌦️ 날씨 카드")
        if weather:
            st.info(
                f"**{weather['city']}**\n\n"
                f"- 상태: {weather.get('desc','-')}\n"
                f"- 기온: {weather.get('temp','-')}℃ (체감 {weather.get('feels_like','-')}℃)\n"
                f"- 습도: {weather.get('humidity','-')}%"
            )
        else:
            st.warning("날씨 정보를 불러오지 못했어요. (API Key/도시/네트워크를 확인해 주세요)")

    with dcol:
        st.markdown("#### 🐶 강아지 카드")
        if dog and dog.get("url"):
            breed = dog.get("breed") or "알 수 없음"
            st.write(f"**품종:** {breed}")
            st.image(dog["url"], use_container_width=True)
        else:
            st.warning("강아지 이미지를 불러오지 못했어요.")

    st.markdown("#### 📝 AI 리포트")
    if report:
        st.markdown(report)
    else:
        if not OPENAI_API_KEY:
            st.error("OpenAI API Key가 없습니다. 사이드바에 입력하거나 Secrets/환경변수를 설정하세요.")
        else:
            st.error("리포트를 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")

    # Share text
    checked_names = ", ".join([k for k, v in habits.items() if v]) or "없음"
    unchecked_names = ", ".join([k for k, v in habits.items() if not v]) or "없음"
    w_line = (
        f"{city} / {weather.get('desc','-')} {weather.get('temp','-')}℃"
        if weather else f"{city} / 날씨 불러오기 실패"
    )
    dog_line = (dog.get("breed") or "알 수 없음") if dog else "불러오기 실패"

    share = f"""[AI 습관 트래커 공유]
- 날짜: {today_s}
- 달성률: {achievement}% ({checked_count}/{total_habits})
- 기분: {mood}/10
- 완료: {checked_names}
- 미완료: {unchecked_names}
- 날씨: {w_line}
- 강아지 품종: {dog_line}

[AI 코치 리포트]
{report or '(리포트 생성 실패)'}
"""
    st.markdown("#### 🔗 공유용 텍스트")
    st.code(share, language="text")

# -----------------------------
# API Guide
# -----------------------------
with st.expander("ℹ️ API 안내 / 설정 방법"):
    st.markdown(
        """
**1) OpenAI API Key**
- Streamlit Cloud에서는 `Secrets`에 저장하는 걸 추천해요.
- Secrets 예시:
```toml
OPENAI_API_KEY="sk-..."
OPENWEATHER_API_KEY="xxxx..."
