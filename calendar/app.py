from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from datetime import datetime, timedelta
import calendar
import requests
import google.generativeai as genai
import json
from dotenv import load_dotenv
import os
import pymysql
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

# .env 파일 내용 로드
load_dotenv()

# 전역 DB 설정
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_CHARSET = "utf8mb4"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "my_secret_key_1234")

# Flask-Login 초기화
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


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
            cursor.execute("CREATE DATABASE IF NOT EXISTS cal_db")
            cursor.execute("USE cal_db")

            # 1. Users 테이블
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

            # 2. Schedules 테이블
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS schedules
                           (
                               schedule_id
                               INT
                               AUTO_INCREMENT
                               PRIMARY
                               KEY,
                               user_id
                               INT
                               NOT
                               NULL,
                               title
                               VARCHAR
                           (
                               150
                           ) NOT NULL,
                               description TEXT,
                               start_date DATETIME NOT NULL,
                               end_date DATETIME NOT NULL,
                               color VARCHAR
                           (
                               7
                           ) DEFAULT '#3788d8',
                               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                               FOREIGN KEY
                           (
                               user_id
                           ) REFERENCES users
                           (
                               user_id
                           ) ON DELETE CASCADE
                               )
                           """)

            # 3. Groups 테이블 (cal_groups)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS cal_groups
                           (
                               group_id
                               INT
                               AUTO_INCREMENT
                               PRIMARY
                               KEY,
                               group_name
                               VARCHAR
                           (
                               100
                           ) NOT NULL,
                               invite_code VARCHAR
                           (
                               50
                           ) NOT NULL UNIQUE,
                               created_by INT NOT NULL,
                               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                               )
                           """)

            # 4. Group Members 테이블
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS group_members
                           (
                               group_id
                               INT
                               NOT
                               NULL,
                               user_id
                               INT
                               NOT
                               NULL,
                               joined_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               PRIMARY
                               KEY
                           (
                               group_id,
                               user_id
                           ),
                               FOREIGN KEY
                           (
                               group_id
                           ) REFERENCES cal_groups
                           (
                               group_id
                           ) ON DELETE CASCADE,
                               FOREIGN KEY
                           (
                               user_id
                           ) REFERENCES users
                           (
                               user_id
                           )
                             ON DELETE CASCADE
                               )
                           """)

            # 5. Available Slots 테이블
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS available_slots
                           (
                               slot_id
                               INT
                               AUTO_INCREMENT
                               PRIMARY
                               KEY,
                               group_id
                               INT
                               NOT
                               NULL,
                               user_id
                               INT
                               NOT
                               NULL,
                               start_time
                               DATETIME
                               NOT
                               NULL,
                               end_time
                               DATETIME
                               NOT
                               NULL,
                               FOREIGN
                               KEY
                           (
                               group_id
                           ) REFERENCES cal_groups
                           (
                               group_id
                           ) ON DELETE CASCADE,
                               FOREIGN KEY
                           (
                               user_id
                           ) REFERENCES users
                           (
                               user_id
                           )
                             ON DELETE CASCADE
                               )
                           """)

            # 기본 유저 생성
            cursor.execute("SELECT count(*) as cnt FROM users WHERE user_id = 1")
            result = cursor.fetchone()
            if result['cnt'] == 0:
                pw_hash = generate_password_hash('1234')
                cursor.execute("""
                               INSERT INTO users (username, email, password_hash)
                               VALUES ('admin', 'admin@example.com', %s)
                               """, (pw_hash,))
                conn.commit()

        conn.commit()
        print("✅ 데이터베이스 초기화 완료")
    except Exception as e:
        print(f"⚠️ DB 초기화 오류 : {e}")
    finally:
        conn.close()


InitilizeDB()


# ---------------------------------------------------------
# User 클래스 및 로그인 로직
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
                cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash("이미 존재하는 이메일입니다.")
                    return redirect(url_for('register'))
                pw_hash = generate_password_hash(password)
                cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                               (username, email, pw_hash))
            conn.commit()
            flash("회원가입 성공!")
            return redirect(url_for('login'))
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
                    flash("로그인 정보가 올바르지 않습니다.")
        finally:
            conn.close()
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------------------------------------------------
# [공유 캘린더 관련 로직]
# ---------------------------------------------------------

# 1. 공유 캘린더 생성
@app.route('/create_group_calendar')
@login_required
def create_group_calendar():
    invite_code = str(uuid.uuid4())[:8]  # 8자리 랜덤 코드
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("""
                           INSERT INTO cal_groups (group_name, invite_code, created_by)
                           VALUES (%s, %s, %s)
                           """, (f"{current_user.username}의 공유 캘린더", invite_code, current_user.id))
            group_id = cursor.lastrowid

            # 생성자를 멤버로 추가
            cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)", (group_id, current_user.id))
        conn.commit()
        return redirect(url_for('shared_calendar', invite_code=invite_code))
    except Exception as e:
        print(e)
        flash("그룹 생성 실패")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


# 1.5 공유 캘린더 참가 (초대 코드 입력)
@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    invite_input = request.form.get('invite_code', '').strip()

    # URL에서 코드만 추출
    if '/shared/' in invite_input:
        invite_code = invite_input.split('/shared/')[-1]
    else:
        invite_code = invite_input

    if not invite_code:
        flash("초대 코드를 입력해주세요.")
        return redirect(url_for('dashboard'))

    return redirect(url_for('shared_calendar', invite_code=invite_code))


# 2. 공유 캘린더 화면 & 계산 로직
@app.route('/shared/<invite_code>')
@login_required
def shared_calendar(invite_code):
    conn = get_db_connection()
    group_info = None
    members = []
    group_slots = []
    common_slots = []
    last_id = 0  # 상태 추적 변수

    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")

            # 1. 그룹 정보 조회
            cursor.execute("SELECT * FROM cal_groups WHERE invite_code = %s", (invite_code,))
            group_info = cursor.fetchone()

            if not group_info:
                flash("존재하지 않는 캘린더입니다.")
                return redirect(url_for('dashboard'))

            group_id = group_info['group_id']

            # 2. 자동 가입 처리
            cursor.execute("SELECT * FROM group_members WHERE group_id=%s AND user_id=%s", (group_id, current_user.id))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                               (group_id, current_user.id))
                conn.commit()
                flash("공유 캘린더에 참여했습니다!")

            # 3. 멤버 리스트 조회
            cursor.execute("""
                           SELECT u.user_id, u.username, u.email
                           FROM group_members gm
                                    JOIN users u ON gm.user_id = u.user_id
                           WHERE gm.group_id = %s
                           """, (group_id,))
            members = cursor.fetchall()

            # 3.5 현재 그룹의 최신 슬롯 ID 조회
            cursor.execute("SELECT MAX(slot_id) as last_id FROM available_slots WHERE group_id = %s", (group_id,))
            res = cursor.fetchone()
            if res and res['last_id']:
                last_id = res['last_id']

            # 4. 모든 멤버의 슬롯 가져오기
            cursor.execute("""
                           SELECT s.slot_id, s.user_id, u.username, s.start_time, s.end_time
                           FROM available_slots s
                                    JOIN users u ON s.user_id = u.user_id
                           WHERE s.group_id = %s
                           ORDER BY s.start_time ASC
                           """, (group_id,))
            group_slots = cursor.fetchall()

            # --- [핵심] 모두가 비는 시간 계산 (교집합) ---
            member_count = len(members)
            if member_count > 1 and group_slots:
                time_counter = {}
                for slot in group_slots:
                    curr = slot['start_time']
                    while curr < slot['end_time']:
                        if curr not in time_counter:
                            time_counter[curr] = set()
                        time_counter[curr].add(slot['user_id'])
                        curr += timedelta(minutes=30)

                common_times = sorted([t for t, users in time_counter.items() if len(users) == member_count])

                if common_times:
                    start = common_times[0]
                    end = start + timedelta(minutes=30)
                    for i in range(1, len(common_times)):
                        if common_times[i] == end:
                            end += timedelta(minutes=30)
                        else:
                            common_slots.append({'start': start, 'end': end})
                            start = common_times[i]
                            end = start + timedelta(minutes=30)
                    common_slots.append({'start': start, 'end': end})

    except Exception as e:
        print(f"Shared Calendar Error: {e}")
    finally:
        conn.close()

    now = datetime.now()
    year = now.year
    month = now.month
    days_in_month = calendar.monthrange(year, month)[1]

    return render_template('shared_calendar.html',
                           group=group_info,
                           members=members,
                           invite_code=invite_code,
                           group_slots=group_slots,
                           common_slots=common_slots,
                           last_id=last_id,
                           year=year, month=month, days_in_month=days_in_month,
                           calendar=calendar)


def get_email_by_id(conn, uid):
    with conn.cursor() as cursor:
        cursor.execute("SELECT email FROM users WHERE user_id=%s", (uid,))
        res = cursor.fetchone()
        return res['email'] if res else None


# 3. 비는 시간 추가
@app.route('/add_free_time', methods=['POST'])
@login_required
def add_free_time():
    group_id = request.form.get('group_id')
    invite_code = request.form.get('invite_code')

    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')

    start_hour = request.form.get('start_hour')
    start_min = request.form.get('start_min')
    end_hour = request.form.get('end_hour')
    end_min = request.form.get('end_min')

    conn = get_db_connection()
    try:
        start_time_str = f"{start_hour}:{start_min}"
        end_time_str = f"{end_hour}:{end_min}"

        start_dt = datetime.strptime(f"{start_date_str} {start_time_str}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{end_date_str} {end_time_str}", "%Y-%m-%d %H:%M")

        if end_dt <= start_dt:
            flash("종료 시간은 시작 시간보다 늦어야 합니다.")
            return redirect(url_for('shared_calendar', invite_code=invite_code))

        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("""
                           INSERT INTO available_slots (group_id, user_id, start_time, end_time)
                           VALUES (%s, %s, %s, %s)
                           """, (group_id, current_user.id, start_dt, end_dt))
        conn.commit()
    except Exception as e:
        print(e)
        flash("시간 저장 실패")
    finally:
        conn.close()

    return redirect(url_for('shared_calendar', invite_code=invite_code))

# 3.5. 그룹 데이터 변경 확인용 API
@app.route('/api/group_status/<int:group_id>')
def group_status(group_id):
    conn = get_db_connection()
    last_id = 0
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")

            # 가장 마지막에 추가된 슬롯의 ID를 조회 (변경사항 감지용)
            cursor.execute("SELECT MAX(slot_id) as last_id FROM available_slots WHERE group_id = %s", (group_id,))
            result = cursor.fetchone()
            if result and result['last_id']:
                last_id = result['last_id']
    finally:
        conn.close()
    return jsonify({"last_id": last_id})

# ---------------------------------------------------------
# [기존 라우트 및 Gemini AI 설정 (복구됨)]
# ---------------------------------------------------------

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

# 캐시
ootd_cache = {"weather_key": None, "text": None}
place_cache = {"data": None}
activity_cache = {"data": None}


# DB 헬퍼 함수
def fetch_events_from_db(user_id):
    conn = get_db_connection()
    events_dict = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            sql = "SELECT title, start_date FROM schedules WHERE user_id = %s ORDER BY start_date ASC"
            cursor.execute(sql, (user_id,))
            rows = cursor.fetchall()
            for row in rows:
                dt = row['start_date']
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M")
                if date_str not in events_dict: events_dict[date_str] = []
                events_dict[date_str].append({'title': row['title'], 'time': time_str, 'type': 'bg-orange'})
    finally:
        conn.close()
    return events_dict


def insert_event_to_db(user_id, title, date_str, hour, minute):
    conn = get_db_connection()
    try:
        if not hour or not minute: hour, minute = "00", "00"
        start_dt_str = f"{date_str} {hour}:{minute}:00"
        start_dt = datetime.strptime(start_dt_str, "%Y-%m-%d %H:%M:%S")
        end_dt = start_dt + timedelta(hours=1)
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("INSERT INTO schedules (user_id, title, start_date, end_date) VALUES (%s, %s, %s, %s)",
                           (user_id, title, start_dt, end_dt))
        conn.commit()
    finally:
        conn.close()


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
            elif weather_id >= 801:
                icon = "fa-cloud"
            return {"temp": f"{temp}°C", "status": desc, "icon": icon, "raw_temp": temp}
        else:
            return {"temp": "--°C", "status": "정보없음", "icon": "fa-question"}
    except:
        return {"temp": "--°C", "status": "연결실패", "icon": "fa-exclamation-triangle"}


# [복구됨] OOTD 추천 로직
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
        print(f"OOTD Error: {e}")
        return "날씨에 딱 맞는 따뜻한 코디를 추천해요! 🧥"


# [복구됨] 장소 추천 로직
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
        print(f"Place Error: {e}")
        return {
            "name": "안성 맞춤 맛집",
            "tags": ["분위기좋은", "맛집탐방", "추천"],
            "menu": "맛있는 한 끼"
        }


# [복구됨] 활동 추천 로직
def get_gemini_activity_recommendation(weather_data, today_schedule):
    try:
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
        반드시 아래 JSON 리스트 형식으로만 답변해줘 (마크다운 없이):
        [
            {{ "title": "활동명1", "desc": "간단한 설명(10자 내외)" }},
            {{ "title": "활동명2", "desc": "간단한 설명(10자 내외)" }}
        ]
        """
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"Activity Error: {e}")
        return [
            {"title": "독서하기", "desc": "조용한 카페에서 힐링"},
            {"title": "스트레칭", "desc": "가벼운 운동으로 활력 충전"}
        ]


# [복구됨] API 라우트
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


@app.route('/api/get_activity', methods=['POST'])
@login_required
def api_get_activity():
    global activity_cache
    req_data = request.get_json() or {}
    force_refresh = req_data.get('refresh', False)

    weather_data = {
        "status": req_data.get('status', ''),
        "temp": req_data.get('temp', '')
    }

    today_str = datetime.now().strftime("%Y-%m-%d")
    all_events = fetch_events_from_db(user_id=current_user.id)
    today_schedule = all_events.get(today_str, [])

    if activity_cache['data'] and not force_refresh:
        return jsonify(activity_cache['data'])

    activity_data = get_gemini_activity_recommendation(weather_data, today_schedule)
    activity_cache['data'] = activity_data
    return jsonify(activity_data)


@app.route('/')
@login_required
def dashboard():
    now = datetime.now()
    weather_info = get_real_weather("Anseong")
    today_date_obj = now.date()
    events_from_db = fetch_events_from_db(user_id=current_user.id)

    dashboard_schedule = []
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
    dashboard_schedule.sort(key=lambda x: (x['full_date'], x['sort_time']))

    today_info = {
        "username": current_user.username,
        "date": now.strftime("%m/%d/%Y"),
        "time_now": now.strftime("%I:%M %p"),
        "weather": weather_info,
        "ootd_text": "로딩중...",
        "schedule": dashboard_schedule,
        "location": {"name": "로딩중...", "tags": [], "menu": ""},
        "activity": []
    }
    return render_template('dashboard.html', info=today_info)


@app.route('/calendar')
@login_required
def calendar_page():
    now = datetime.now()
    year = int(request.args.get('year', now.year))
    month = int(request.args.get('month', now.month))
    start_weekday, days_in_month = calendar.monthrange(year, month)
    events_from_db = fetch_events_from_db(user_id=current_user.id)

    # 달력 계산 로직
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    return render_template('calendar.html', events=events_from_db, year=year, month=month,
                           month_name=calendar.month_name[month], days_in_month=days_in_month,
                           start_blank_count=(start_weekday + 1) % 7, prev_year=prev_year, prev_month=prev_month,
                           next_year=next_year, next_month=next_month,
                           today_year=now.year, today_month=now.month, today_day=now.day)


@app.route('/add_event', methods=['POST'])
@login_required
def add_event():
    date = request.form.get('date')
    title = request.form.get('title')
    hour = request.form.get('hour')
    minute = request.form.get('minute')
    if date and title: insert_event_to_db(current_user.id, title, date, hour, minute)
    return redirect(url_for('calendar_page', year=int(date.split('-')[0]), month=int(date.split('-')[1])))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)