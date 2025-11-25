from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
import calendar
import requests
import google.generativeai as genai
import json
from dotenv import load_dotenv
import os
import pymysql
# [추가] Flask-Login 및 보안 관련 라이브러리 임포트
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# .env 파일 내용 로드
load_dotenv()

# 전역 DB 설정 (환경변수 없으면 기본값 사용)
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_CHARSET = "utf8mb4"

app = Flask(__name__)
# [추가] 세션 관리를 위한 시크릿 키 설정 (실제 배포시에는 복잡한 문자열로 변경 필요)
app.secret_key = os.environ.get("SECRET_KEY", "my_secret_key_1234")

# [추가] Flask-Login 초기화
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 로그인 안 된 사용자가 접근하면 이동할 뷰


# ---------------------------------------------------------
# [DB 관리] 연결 및 초기화
# ---------------------------------------------------------
def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        passwd=DB_PASSWORD,
        charset=DB_CHARSET,
        cursorclass=pymysql.cursors.DictCursor
    )


def InitilizeDB():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. DB 생성 및 사용
            cursor.execute("CREATE DATABASE IF NOT EXISTS cal_db")
            cursor.execute("USE cal_db")

            # 2. Users 테이블 생성
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS users
                           (
                               user_id
                               INT
                               AUTO_INCREMENT
                               PRIMARY
                               KEY,
                               username
                               VARCHAR
                           (
                               50
                           ) NOT NULL,
                               email VARCHAR
                           (
                               100
                           ) NOT NULL UNIQUE,
                               password_hash VARCHAR
                           (
                               255
                           ) NOT NULL,
                               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                               )
                           """)

            # 3. Schedules 테이블 생성 (문법 오류 수정됨)
            # 4. (테스트용) 기본 유저 확인 (비밀번호: 1234 로 설정하여 생성)
            cursor.execute("SELECT count(*) as cnt FROM users WHERE user_id = 1")
            result = cursor.fetchone()
            if result['cnt'] == 0:
                # '1234'를 해시화하여 저장
                pw_hash = generate_password_hash('1234')
                cursor.execute("""
                               INSERT INTO users (username, email, password_hash)
                               VALUES ('admin', 'admin@example.com', %s)
                               """, (pw_hash,))
                conn.commit()
                print("✅ 기본 유저(admin, id=1, pw=1234)가 생성되었습니다.")

        conn.commit()
        print("✅ 데이터베이스 초기화 완료")
    except Exception as e:
        print(f"⚠️ DB 초기화 오류 : {e}")
    finally:
        conn.close()


# 앱 시작 시 DB 초기화 실행
InitilizeDB()


# ---------------------------------------------------------
# [User 클래스 및 User Loader]
# ---------------------------------------------------------
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = None
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("SELECT user_id, username, email FROM users WHERE user_id = %s", (user_id,))
            result = cursor.fetchone()
            if result:
                user = User(id=result['user_id'], username=result['username'], email=result['email'])
    except Exception as e:
        print(f"User Load Error: {e}")
    finally:
        conn.close()
    return user


# ---------------------------------------------------------
# [인증 관련 라우트] 로그인/회원가입/로그아웃
# ---------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("USE cal_db")
                # 이메일 중복 확인
                cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash("이미 존재하는 이메일입니다.")
                    return redirect(url_for('register'))

                # 비밀번호 해시화 및 저장
                pw_hash = generate_password_hash(password)
                cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                               (username, email, pw_hash))
            conn.commit()
            flash("회원가입 성공! 로그인해주세요.")
            return redirect(url_for('login'))
        except Exception as e:
            print(e)
            flash("회원가입 중 오류가 발생했습니다.")
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("USE cal_db")
                cursor.execute("SELECT user_id, username, email, password_hash FROM users WHERE email = %s", (email,))
                result = cursor.fetchone()

                if result and check_password_hash(result['password_hash'], password):
                    user = User(id=result['user_id'], username=result['username'], email=result['email'])
                    login_user(user)
                    return redirect(url_for('dashboard'))
                else:
                    flash("이메일 또는 비밀번호가 올바르지 않습니다.")
        finally:
            conn.close()
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------------------------------------------------
# [DB 헬퍼 함수] 일정 조회 및 추가
# ---------------------------------------------------------

def fetch_events_from_db(user_id):
    """
    DB에서 일정을 가져와서 기존 템플릿이 사용하는
    {'YYYY-MM-DD': [{'title':..., 'time':..., 'type':...}]} 형태로 변환하여 반환
    """
    conn = get_db_connection()
    events_dict = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            # user_id에 해당하는 일정 조회
            sql = "SELECT title, start_date FROM schedules WHERE user_id = %s ORDER BY start_date ASC"
            cursor.execute(sql, (user_id,))
            rows = cursor.fetchall()

            for row in rows:
                dt = row['start_date']  # datetime 객체
                date_str = dt.strftime("%Y-%m-%d")  # 키값 (YYYY-MM-DD)
                time_str = dt.strftime("%H:%M")  # 표시 시간 (HH:MM)

                if date_str not in events_dict:
                    events_dict[date_str] = []

                events_dict[date_str].append({
                    'title': row['title'],
                    'time': time_str,
                    'type': 'bg-orange'  # 색상 로직은 필요시 DB color 컬럼 활용 가능
                })
    except Exception as e:
        print(f"일정 조회 실패: {e}")
    finally:
        conn.close()

    return events_dict


def insert_event_to_db(user_id, title, date_str, hour, minute):
    """
    일정을 DB에 저장
    """
    conn = get_db_connection()
    try:
        # 시간 문자열 처리
        if not hour or not minute:
            hour = "00"
            minute = "00"

        # DATETIME 문자열 생성
        start_dt_str = f"{date_str} {hour}:{minute}:00"
        # 종료 시간은 임의로 1시간 뒤로 설정 (필요시 입력받도록 수정 가능)
        start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
        end_dt = start_dt + timedelta(hours=1)

        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            sql = """
                  INSERT INTO schedules (user_id, title, start_date, end_date)
                  VALUES (%s, %s, %s, %s) \
                  """
            cursor.execute(sql, (user_id, title, start_dt, end_dt))
        conn.commit()
    except Exception as e:
        print(f"일정 저장 실패: {e}")
    finally:
        conn.close()


# ---------------------------------------------------------
# [설정] API 키 및 Gemini
# ---------------------------------------------------------
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    print("⚠️ 2.5 모델 로드 실패, 1.5-flash로 전환합니다.")
    model = genai.GenerativeModel('gemini-1.5-flash')

# 캐시 저장소들
ootd_cache = {"weather_key": None, "text": None}
place_cache = {"data": None}
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


# --- [함수 4] Gemini에게 활동 추천 요청 (일정 고려) ---
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
@login_required  # 로그인 필수
def api_get_activity():
    global activity_cache
    req_data = request.get_json() or {}
    force_refresh = req_data.get('refresh', False)

    # 날씨 정보 받기
    weather_data = {
        "status": req_data.get('status', ''),
        "temp": req_data.get('temp', '')
    }

    # DB에서 오늘 일정 가져오기
    # fetch_events_from_db()는 전체 일정을 가져오므로 오늘 날짜 키만 추출
    today_str = datetime.now().strftime("%Y-%m-%d")
    all_events = fetch_events_from_db(user_id=current_user.id)  # [변경] 로그인한 유저 ID 사용
    today_schedule = all_events.get(today_str, [])

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
@login_required  # [추가] 로그인 필요
def dashboard():
    now = datetime.now()
    weather_info = get_real_weather("Anseong")

    # 초기 로딩값들
    ootd_text = "gemini 답변을 기다리는중..."
    place_info = {"name": "로딩중...", "tags": [], "menu": ""}
    activity_info = []

    dashboard_schedule = []
    today_date_obj = now.date()

    # DB에서 일정 가져오기 (로그인한 유저)
    events_from_db = fetch_events_from_db(user_id=current_user.id)

    for date_str, events in events_from_db.items():
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

    today_info = {
        "username": current_user.username,  # [추가] 사용자 이름 전달
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
@login_required  # [추가] 로그인 필요
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

    # DB에서 일정 가져오기 (로그인한 유저)
    events_from_db = fetch_events_from_db(user_id=current_user.id)

    return render_template(
        'calendar.html',
        events=events_from_db,  # DB 데이터 전달
        year=year, month=month,
        month_name=calendar.month_name[month],
        days_in_month=days_in_month,
        start_blank_count=start_blank_count,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        today_year=now.year, today_month=now.month, today_day=now.day
    )


@app.route('/add_event', methods=['POST'])
@login_required  # [추가] 로그인 필요
def add_event():
    date = request.form.get('date')  # YYYY-MM-DD
    title = request.form.get('title')
    hour = request.form.get('hour')  # HH
    minute = request.form.get('minute')  # MM

    if date and title:
        # DB에 저장 (로그인한 유저 ID 사용)
        insert_event_to_db(current_user.id, title, date, hour, minute)

    return redirect(url_for('calendar_page', year=int(date.split('-')[0]), month=int(date.split('-')[1])))


if __name__ == '__main__':
    app.run(debug=True)