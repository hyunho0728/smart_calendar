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
from itertools import groupby  # [중요] 스위핑 알고리즘용

# .env 파일 내용 로드
load_dotenv()

# 전역 DB 설정
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_CHARSET = "utf8mb4"

# AI 및 날씨 API 키
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "my_secret_key_1234")

# Flask-Login 초기화
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 캐시
ootd_cache = {"weather_key": None, "text": None}
place_cache = {"data": None}
activity_cache = {"data": None}


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
            # ... (테이블 생성 로직 생략, 기존과 동일) ...
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
        conn.commit()
    except Exception as e:
        print(f"⚠️ DB 초기화 오류 : {e}")
    finally:
        conn.close()


InitilizeDB()


# ---------------------------------------------------------
# User 클래스 및 로그인
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
# [공유 캘린더 기능]
# ---------------------------------------------------------

@app.route('/create_group_calendar')
@login_required
def create_group_calendar():
    invite_code = str(uuid.uuid4())[:8]
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("INSERT INTO cal_groups (group_name, invite_code, created_by) VALUES (%s, %s, %s)",
                           (f"{current_user.username}의 공유 캘린더", invite_code, current_user.id))
            group_id = cursor.lastrowid
            cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)", (group_id, current_user.id))
        conn.commit()
        return redirect(url_for('shared_calendar', invite_code=invite_code))
    except Exception as e:
        print(e)
        flash("그룹 생성 실패")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    invite_input = request.form.get('invite_code', '').strip()
    if '/shared/' in invite_input:
        invite_code = invite_input.split('/shared/')[-1]
    else:
        invite_code = invite_input

    if not invite_code:
        flash("초대 코드를 입력해주세요.")
        return redirect(url_for('dashboard'))

    return redirect(url_for('shared_calendar', invite_code=invite_code))


@app.route('/api/group_status/<int:group_id>')
def group_status(group_id):
    conn = get_db_connection()
    last_id = 0
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("SELECT MAX(slot_id) as last_id FROM available_slots WHERE group_id = %s", (group_id,))
            result = cursor.fetchone()
            if result and result['last_id']:
                last_id = result['last_id']
    finally:
        conn.close()
    return jsonify({"last_id": last_id})


# [헬퍼 함수] 시간 구간 병합
def merge_intervals(intervals):
    if not intervals: return []
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:
            new_end = max(last[1], current[1])
            merged[-1] = (last[0], new_end)
        else:
            merged.append(current)
    return merged


# [메인] 공유 캘린더 화면 & 스위핑 알고리즘 적용
@app.route('/shared/<invite_code>')
@login_required
def shared_calendar(invite_code):
    conn = get_db_connection()
    group_info = None
    members = []
    group_slots = []
    common_slots = []
    last_id = 0

    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("SELECT * FROM cal_groups WHERE invite_code = %s", (invite_code,))
            group_info = cursor.fetchone()

            if not group_info:
                flash("존재하지 않는 캘린더입니다.")
                return redirect(url_for('dashboard'))

            group_id = group_info['group_id']

            # 자동 가입
            cursor.execute("SELECT * FROM group_members WHERE group_id=%s AND user_id=%s", (group_id, current_user.id))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                               (group_id, current_user.id))
                conn.commit()

            cursor.execute("SELECT MAX(slot_id) as last_id FROM available_slots WHERE group_id = %s", (group_id,))
            res = cursor.fetchone()
            if res and res['last_id']: last_id = res['last_id']

            cursor.execute("""
                           SELECT u.user_id, u.username, u.email
                           FROM group_members gm
                                    JOIN users u ON gm.user_id = u.user_id
                           WHERE gm.group_id = %s
                           """, (group_id,))
            members = cursor.fetchall()

            cursor.execute("""
                           SELECT s.slot_id, s.user_id, u.username, s.start_time, s.end_time
                           FROM available_slots s
                                    JOIN users u ON s.user_id = u.user_id
                           WHERE s.group_id = %s
                           ORDER BY s.start_time ASC
                           """, (group_id,))
            group_slots = cursor.fetchall()

            # ---------------------------------------------------------
            # [최종 수정] 날짜별 독립적 겹침 계산 (Date-wise Intersection)
            # ---------------------------------------------------------
            if group_slots:
                # 1. 슬롯을 날짜별로 분리 (Split slots by date)
                slots_by_date = {}  # Key: 'YYYY-MM-DD', Value: list of (start, end, user_id)

                for slot in group_slots:
                    uid = slot['user_id']
                    s = slot['start_time']
                    e = slot['end_time']

                    # 시작 시간부터 종료 시간까지 날짜별로 쪼개기
                    curr = s
                    while curr < e:
                        # 다음날 자정 계산
                        next_midnight = (curr + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                        eff_end = min(e, next_midnight)

                        day_key = curr.strftime('%Y-%m-%d')
                        if day_key not in slots_by_date:
                            slots_by_date[day_key] = []

                        slots_by_date[day_key].append((curr, eff_end, uid))

                        curr = eff_end

                # 2. 각 날짜별로 교집합 계산
                for day_key, day_slots in slots_by_date.items():
                    # 해당 날짜에 일정을 등록한 유저들 확인
                    users_on_this_day = set(slot[2] for slot in day_slots)
                    active_count_for_day = len(users_on_this_day)

                    if active_count_for_day > 0:
                        # 유저별 일정 정리 및 내부 병합
                        user_intervals = {uid: [] for uid in users_on_this_day}
                        for s, e, uid in day_slots:
                            user_intervals[uid].append((s, e))

                        # 타임라인 생성 (Start: +1, End: -1)
                        timeline = []
                        for uid in users_on_this_day:
                            merged = merge_intervals(user_intervals[uid])
                            for ms, me in merged:
                                timeline.append((ms, 1, uid))
                                timeline.append((me, -1, uid))

                        timeline.sort(key=lambda x: x[0])

                        # 스위핑 알고리즘
                        current_users = set()

                        # 같은 시각의 이벤트 그룹화
                        grouped_timeline = []
                        for key, group in groupby(timeline, lambda x: x[0]):
                            grouped_timeline.append((key, list(group)))

                        for i in range(len(grouped_timeline) - 1):
                            curr_time, events = grouped_timeline[i]
                            next_time, _ = grouped_timeline[i + 1]

                            # 현재 시각의 이벤트 처리
                            for _, type, uid in events:
                                if type == 1:
                                    current_users.add(uid)
                                elif type == -1:
                                    if uid in current_users: current_users.remove(uid)

                            # 해당 날짜의 활성 유저 모두가 포함된 구간인지 확인
                            if len(current_users) == active_count_for_day and curr_time < next_time:
                                common_slots.append({'start': curr_time, 'end': next_time})

    except Exception as e:
        print(f"Calendar Error: {e}")
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


@app.route('/add_free_time', methods=['POST'])
@login_required
def add_free_time():
    group_id = request.form.get('group_id')
    invite_code = request.form.get('invite_code')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    start_hour = request.form.get('start_hour')
    start_min = request.form.get('start_min')
    end_hour = request.form.get('end_hour')
    end_min = request.form.get('end_min')

    conn = get_db_connection()
    try:
        start_dt = datetime.strptime(f"{start_date} {start_hour}:{start_min}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{end_date} {end_hour}:{end_min}", "%Y-%m-%d %H:%M")
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
    finally:
        conn.close()
    return redirect(url_for('shared_calendar', invite_code=invite_code))


@app.route('/delete_slot/<int:slot_id>', methods=['POST'])
@login_required
def delete_slot(slot_id):
    invite_code = request.form.get('invite_code')
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("DELETE FROM available_slots WHERE slot_id=%s AND user_id=%s", (slot_id, current_user.id))
            conn.commit()
    finally:
        conn.close()
    return redirect(url_for('shared_calendar', invite_code=invite_code))


@app.route('/update_slot', methods=['POST'])
@login_required
def update_slot():
    invite_code = request.form.get('invite_code')
    slot_id = request.form.get('slot_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    start_hour = request.form.get('start_hour')
    start_min = request.form.get('start_min')
    end_hour = request.form.get('end_hour')
    end_min = request.form.get('end_min')

    conn = get_db_connection()
    try:
        start_dt = datetime.strptime(f"{start_date} {start_hour}:{start_min}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{end_date} {end_hour}:{end_min}", "%Y-%m-%d %H:%M")
        if end_dt <= start_dt:
            flash("종료 시간이 시작 시간보다 늦어야 합니다.")
            return redirect(url_for('shared_calendar', invite_code=invite_code))
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("""
                           UPDATE available_slots
                           SET start_time=%s,
                               end_time=%s
                           WHERE slot_id = %s
                             AND user_id = %s
                           """, (start_dt, end_dt, slot_id, current_user.id))
            conn.commit()
    except Exception as e:
        print(f"Update error: {e}")
    finally:
        conn.close()
    return redirect(url_for('shared_calendar', invite_code=invite_code))


# --- AI 및 대시보드 함수 (기존 유지) ---
def fetch_events_from_db(user_id):
    conn = get_db_connection()
    events_dict = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")
            cursor.execute("SELECT title, start_date FROM schedules WHERE user_id = %s ORDER BY start_date ASC",
                           (user_id,))
            for row in cursor.fetchall():
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
        start_dt = datetime.strptime(f"{date_str} {hour}:{minute}:00", "%Y-%m-%d %H:%M:%S")
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
        res = requests.get(url)
        if res.status_code == 200:
            data = res.json()
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
            return {"temp": f"{round(data['main']['temp'])}°C", "status": data['weather'][0]['description'],
                    "icon": icon}
        return {"temp": "--°C", "status": "정보없음", "icon": "fa-question"}
    except:
        return {"temp": "--°C", "status": "연결실패", "icon": "fa-exclamation-triangle"}


def get_gemini_ootd_text(weather_data):
    try:
        prompt = f"날씨: {weather_data['status']}, 기온: {weather_data['temp']}. OOTD 추천(20자 내외, 이모지 포함)."
        return model.generate_content(prompt).text
    except:
        return "날씨에 딱 맞는 따뜻한 코디를 추천해요! 🧥"


def get_gemini_place_recommendation(city="안성"):
    try:
        prompt = f"경기도 {city} 맛집/카페 추천. JSON: {{ \"name\": \"..\", \"tags\": [\"..\"], \"menu\": \"..\" }}"
        text = model.generate_content(prompt).text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except:
        return {"name": "추천 맛집", "tags": ["맛집"], "menu": "메뉴"}


def get_gemini_activity_recommendation(weather_data, today_schedule):
    try:
        prompt = f"날씨: {weather_data['status']}, 일정 고려하여 자투리 시간 활동 2개 추천. JSON: [ {{ \"title\": \"..\", \"desc\": \"..\" }} ]"
        text = model.generate_content(prompt).text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except:
        return [{"title": "휴식", "desc": "편안한 시간 보내기"}]


@app.route('/api/get_ootd', methods=['POST'])
def api_get_ootd():
    global ootd_cache
    data = request.get_json()
    key = f"{data.get('status')}_{data.get('temp')}"
    if ootd_cache["weather_key"] == key and ootd_cache["text"]: return jsonify({"text": ootd_cache["text"]})
    ootd_cache["text"] = get_gemini_ootd_text(data);
    ootd_cache["weather_key"] = key
    return jsonify({"text": ootd_cache["text"]})


@app.route('/api/get_place', methods=['POST'])
def api_get_place():
    global place_cache
    if place_cache['data'] and not request.get_json().get('refresh'): return jsonify(place_cache['data'])
    place_cache['data'] = get_gemini_place_recommendation("안성")
    return jsonify(place_cache['data'])


@app.route('/api/get_activity', methods=['POST'])
@login_required
def api_get_activity():
    global activity_cache
    if activity_cache['data'] and not request.get_json().get('refresh'): return jsonify(activity_cache['data'])
    activity_cache['data'] = get_gemini_activity_recommendation({"status": "", "temp": ""}, [])
    return jsonify(activity_cache['data'])


@app.route('/')
@login_required
def dashboard():
    now = datetime.now()
    weather_info = get_real_weather("Anseong")
    today_date_obj = now.date()

    # [복구] DB에서 내 일정 가져오기
    events_from_db = fetch_events_from_db(user_id=current_user.id)

    dashboard_schedule = []
    for date_str, events in events_from_db.items():
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            diff = (event_date - today_date_obj).days

            # 오늘 포함, 미래의 일정만 표시
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

    # 날짜 및 시간순 정렬
    dashboard_schedule.sort(key=lambda x: (x['full_date'], x['sort_time']))

    today_info = {
        "username": current_user.username,
        "date": now.strftime("%m/%d/%Y"),
        "time_now": now.strftime("%I:%M %p"),
        "weather": weather_info,
        "ootd_text": "로딩중...",
        "schedule": dashboard_schedule,
        # [복구] 누락되었던 location(맛집)과 activity(활동) 초기값 추가
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

    # [수정] 달력 시작 요일 계산을 위해 start_weekday 변수 받기
    start_weekday, days_in_month = calendar.monthrange(year, month)

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    return render_template('calendar.html',
                           events=fetch_events_from_db(current_user.id),
                           year=year,
                           month=month,
                           days_in_month=days_in_month,
                           # [수정] start_blank_count 계산하여 전달 (일요일 시작 기준)
                           start_blank_count=(start_weekday + 1) % 7,
                           prev_year=prev_year,
                           prev_month=prev_month,
                           next_year=next_year,
                           next_month=next_month,
                           month_name=calendar.month_name[month],
                           today_year=now.year,
                           today_month=now.month,
                           today_day=now.day)


@app.route('/add_event', methods=['POST'])
@login_required
def add_event():
    if request.form.get('date') and request.form.get('title'):
        insert_event_to_db(current_user.id, request.form.get('title'), request.form.get('date'),
                           request.form.get('hour'), request.form.get('minute'))
    return redirect(url_for('calendar_page', year=int(request.form.get('date').split('-')[0]),
                            month=int(request.form.get('date').split('-')[1])))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)