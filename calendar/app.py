from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime
import calendar
import requests
import google.generativeai as genai
import json
from dotenv import load_dotenv
import os
import pymysql

#.env 파일 내용 로드
load_dotenv()

def InitilizeDB():
    try:
        with conn.cursor() as cursor:
            cursor.execute("create database if not exists cal_db")
            cursor.execute("use cal_db")
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS users 
                           (
                                user_id INT AUTO_INCREMENT PRIMARY KEY,  -- 고유 ID (자동 증가)
                                username VARCHAR(50) NOT NULL,           -- 사용자 이름
                                email VARCHAR(100) NOT NULL UNIQUE,      -- 이메일 (중복 불가)
                                password_hash VARCHAR(255) NOT NULL,     -- 비밀번호 (암호화하여 저장 권장)
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 계정 생성일
                            );""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS schedules
                              (
                                  schedule_id INT AUTO_INCREMENT PRIMARY KEY,       -- 일정 고유 ID
                                  user_id     INT          NOT NULL,                -- 어떤 유저의 일정인지 (외래 키)
                                  title       VARCHAR(150) NOT NULL,                -- 일정 제목
                                  description TEXT,                                 -- 일정 상세 내용 (긴 글 가능)
                                  start_date  DATETIME     NOT NULL,                -- 시작 시간 (년-월-일 시:분:초)
                                  end_date    DATETIME     NOT NULL,                -- 종료 시간
                                  color       VARCHAR(7) DEFAULT '#3788d8',         -- 캘린더 표시 색상 (Hex 코드)
                                  created_at  TIMESTAMP  DEFAULT CURRENT_TIMESTAMP, -- 일정 생성일
                              );""")
            cursor.execute("CONSTRAINT fk_user_schedule")
            cursor.execute("FOREIGN KEY (user_id) REFERENCES users(user_id)")
            cursor.execute("ON DELETE CASCADE")

    except Exception as e:
        print(f"오류 : {e}")

# db 연결
conn = pymysql.connect(
    host="127.0.0.1",
    user="root",
    passwd=f"{os.environ.get("DB_PASSWORD")}",
    charset="utf8"
)

# db 기초값 생성
InitilizeDB()
app = Flask(__name__)

# ---------------------------------------------------------
# [설정] API 키
# ---------------------------------------------------------
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)

try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    print("⚠️ 2.5 모델 로드 실패, 1.5-flash로 전환합니다.")
    model = genai.GenerativeModel('gemini-1.5-flash')

# 데이터 저장소 (일정)
events_db = {}

# 캐시 저장소들
ootd_cache = {"weather_key": None, "text": None}
place_cache = {"data": None}

# [추가됨] 활동 추천 캐시
activity_cache = {"data": None}


# --- [함수 1] 실제 날씨 가져오기 ---
def get_real_weather(city="Anseong"):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=kr"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            temp = round(data['main']['temp'])
            desc = data['weather'][0]['description']
            weather_id = data['weather'][0]['id']

            icon = "fa-sun"
            if 200 <= weather_id <= 232:
                icon = "fa-bolt"
            elif 300 <= weather_id <= 531:
                icon = "fa-umbrella"
            elif 600 <= weather_id <= 622:
                icon = "fa-snowflake"
            elif 701 <= weather_id <= 781:
                icon = "fa-smog"
            elif weather_id == 800:
                icon = "fa-sun"
            elif weather_id >= 801:
                icon = "fa-cloud"

            return {"temp": f"{temp}°C", "status": desc, "icon": icon, "raw_temp": temp}
        else:
            return {"temp": "--°C", "status": "정보없음", "icon": "fa-question"}
    except Exception as e:
        return {"temp": "--°C", "status": "연결실패", "icon": "fa-exclamation-triangle"}


# --- [함수 2] Gemini에게 OOTD 요청 ---
def get_gemini_ootd_text(weather_data):
    try:
        prompt = f"""
        현재 날씨는 {weather_data['status']}이고 기온은 {weather_data['temp']}입니다.
        이 날씨에 맞는 패션 스타일(OOTD)을 추천해주세요.
        구체적인 아이템(상의, 하의, 아우터, 신발 등)을 언급하며 20자 내외의 한 문장으로 작성해주세요.
        말투는 친절하게, 이모지를 꼭 포함해주세요.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "날씨에 딱 맞는 따뜻한 코디를 추천해요! 🧥"


# --- [함수 3] Gemini에게 장소 추천 요청 ---
def get_gemini_place_recommendation(city="안성"):
    try:
        prompt = f"""
        경기도 {city}에 있는 실제 맛집이나 감성 카페 중 하나를 랜덤으로 추천해줘.
        반드시 아래 JSON 형식으로만 답변해줘 (마크다운 backtick 없이 순수 JSON만):
        {{
            "name": "가게이름",
            "tags": ["태그1", "태그2", "태그3"],
            "menu": "대표메뉴 1~2개"
        }}
        """
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        return {
            "name": "안성 맞춤 맛집",
            "tags": ["분위기좋은", "맛집탐방", "추천"],
            "menu": "맛있는 한 끼"
        }


# --- [추가됨] [함수 4] Gemini에게 활동 추천 요청 (일정 고려) ---
def get_gemini_activity_recommendation(weather_data, today_schedule):
    try:
        # 일정 정보를 텍스트로 변환
        schedule_text = "오늘의 일정:\n"
        if not today_schedule:
            schedule_text += "일정이 없습니다. 하루 종일 자유시간입니다."
        else:
            for event in today_schedule:
                time = event.get('time', '시간미정')
                title = event.get('title', '일정')
                schedule_text += f"- {time} {title}\n"

        prompt = f"""
        현재 날씨: {weather_data['status']}, 기온: {weather_data['temp']}
        {schedule_text}

        위의 날씨와 오늘의 일정을 고려해서, 일정이 없는 '자투리 시간(Free Time)'에 할 수 있는 알차고 힐링되는 활동 2가지를 추천해줘.

        조건:
        1. 이미 있는 일정과 시간이 겹치지 않아야 함.
        2. 날씨를 고려해야 함 (비오면 실내, 맑으면 야외 등).
        3. 반드시 아래 JSON 리스트 형식으로만 답변해줘 (마크다운 없이):
        [
            {{ "title": "활동명1", "desc": "간단한 설명(10자 내외)" }},
            {{ "title": "활동명2", "desc": "간단한 설명(10자 내외)" }}
        ]
        """
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"활동 추천 실패: {e}")
        return [
            {"title": "독서하기", "desc": "조용한 카페에서 힐링"},
            {"title": "스트레칭", "desc": "가벼운 운동으로 활력 충전"}
        ]


# =========================================================
# [API] 비동기 요청 핸들러들
# =========================================================

@app.route('/api/get_ootd', methods=['POST'])
def api_get_ootd():
    global ootd_cache
    data = request.get_json()
    current_key = f"{data.get('status')}_{data.get('temp')}"

    if ootd_cache["weather_key"] == current_key and ootd_cache["text"]:
        return jsonify({"text": ootd_cache["text"]})

    ootd_text = get_gemini_ootd_text(data)
    ootd_cache["weather_key"] = current_key
    ootd_cache["text"] = ootd_text
    return jsonify({"text": ootd_text})


@app.route('/api/get_place', methods=['POST'])
def api_get_place():
    global place_cache
    req_data = request.get_json() or {}
    force_refresh = req_data.get('refresh', False)

    if place_cache['data'] and not force_refresh:
        return jsonify(place_cache['data'])

    place_data = get_gemini_place_recommendation("안성")
    place_cache['data'] = place_data
    return jsonify(place_data)


# [추가됨] 활동 추천 API
@app.route('/api/get_activity', methods=['POST'])
def api_get_activity():
    global activity_cache
    req_data = request.get_json() or {}
    force_refresh = req_data.get('refresh', False)

    # 날씨 정보 받기
    weather_data = {
        "status": req_data.get('status', ''),
        "temp": req_data.get('temp', '')
    }

    # 오늘 일정 가져오기 (서버 DB 조회)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_schedule = events_db.get(today_str, [])

    # 캐시 확인
    if activity_cache['data'] and not force_refresh:
        return jsonify(activity_cache['data'])

    # Gemini 호출
    activity_data = get_gemini_activity_recommendation(weather_data, today_schedule)
    activity_cache['data'] = activity_data
    return jsonify(activity_data)


# =========================================================
# [메인 화면] 대시보드
# =========================================================
@app.route('/')
def dashboard():
    now = datetime.now()
    weather_info = get_real_weather("Anseong")

    # 초기 로딩값들
    ootd_text = "gemini 답변을 기다리는중..."
    place_info = {"name": "로딩중...", "tags": [], "menu": ""}
    activity_info = []  # [추가됨] 활동 정보 초기값 (빈 리스트)

    dashboard_schedule = []
    today_date_obj = now.date()

    for date_str, events in events_db.items():
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            diff = (event_date - today_date_obj).days
            if diff >= 0:
                d_day_str = "D-Day" if diff == 0 else f"D-{diff}"
                for event in events:
                    dashboard_schedule.append({
                        "d_day": d_day_str,
                        "time": event.get('time', ''),
                        "title": event['title'],
                        "full_date": date_str,
                        "sort_time": event.get('time') or "23:59"
                    })
        except ValueError:
            continue

    dashboard_schedule.sort(key=lambda x: (x['full_date'], x['sort_time']))

    today_info = {
        "date": now.strftime("%m/%d/%Y"),
        "time_now": now.strftime("%I:%M %p"),
        "weather": weather_info,
        "ootd_text": ootd_text,
        "schedule": dashboard_schedule,
        "location": place_info,
        "activity": activity_info
    }
    return render_template('dashboard.html', info=today_info)


# =========================================================
# [캘린더 화면]
# =========================================================
@app.route('/calendar')
def calendar_page():
    now = datetime.now()
    try:
        year = int(request.args.get('year', now.year))
        month = int(request.args.get('month', now.month))
    except ValueError:
        year = now.year
        month = now.month

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    start_weekday, days_in_month = calendar.monthrange(year, month)
    start_blank_count = (start_weekday + 1) % 7

    return render_template(
        'calendar.html',
        events=events_db,
        year=year, month=month,
        month_name=calendar.month_name[month],
        days_in_month=days_in_month,
        start_blank_count=start_blank_count,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        today_year=now.year, today_month=now.month, today_day=now.day
    )


@app.route('/add_event', methods=['POST'])
def add_event():
    date = request.form.get('date')
    title = request.form.get('title')
    hour = request.form.get('hour')
    minute = request.form.get('minute')

    time_str = ""
    if hour and minute:
        time_str = f"{hour}:{minute}"

    if date and title:
        if date not in events_db:
            events_db[date] = []
        events_db[date].append({
            'title': title,
            'time': time_str,
            'type': 'bg-orange'
        })
        events_db[date].sort(key=lambda x: x.get('time') or "99:99")

    return redirect(url_for('calendar_page', year=int(date.split('-')[0]), month=int(date.split('-')[1])))


if __name__ == '__main__':
    app.run(debug=True)