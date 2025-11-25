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
        print("✅ 데이터베이스 초기화 완료 (테이블명 수정됨: cal_groups)")
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


# [추가됨] 1.5 공유 캘린더 참가 (초대 코드 입력)
@app.route('/join_group', methods=['POST'])
@login_required
def join_group():
    invite_input = request.form.get('invite_code', '').strip()

    # URL에서 코드만 추출 (만약 전체 링크를 넣었을 경우)
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
    my_slots = []
    common_slots = []

    try:
        with conn.cursor() as cursor:
            cursor.execute("USE cal_db")

            cursor.execute("SELECT * FROM cal_groups WHERE invite_code = %s", (invite_code,))
            group_info = cursor.fetchone()

            if not group_info:
                flash("존재하지 않는 캘린더입니다.")
                return redirect(url_for('dashboard'))

            group_id = group_info['group_id']

            # 내가 멤버가 아니면 자동으로 가입
            cursor.execute("SELECT * FROM group_members WHERE group_id=%s AND user_id=%s", (group_id, current_user.id))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                               (group_id, current_user.id))
                conn.commit()
                flash("공유 캘린더에 참여했습니다!")

            # 멤버 리스트 조회
            cursor.execute("""
                           SELECT u.username, u.email
                           FROM group_members gm
                                    JOIN users u ON gm.user_id = u.user_id
                           WHERE gm.group_id = %s
                           """, (group_id,))
            members = cursor.fetchall()

            # 나의 비는 시간 조회
            cursor.execute("""
                           SELECT start_time, end_time
                           FROM available_slots
                           WHERE group_id = %s
                             AND user_id = %s
                           """, (group_id, current_user.id))
            my_slots = cursor.fetchall()

            # --- [핵심] 모두가 비는 시간 계산 로직 ---
            cursor.execute("""
                           SELECT user_id, start_time, end_time
                           FROM available_slots
                           WHERE group_id = %s
                           ORDER BY start_time
                           """, (group_id,))
            all_slots = cursor.fetchall()

            member_count = len(members)
            if member_count > 0 and all_slots:
                member_availability = {m['username']: set() for m in members}

                for slot in all_slots:
                    u_name = next(
                        (m['username'] for m in members if m['email'] == get_email_by_id(conn, slot['user_id'])), None)
                    if not u_name: continue

                    curr = slot['start_time']
                    while curr < slot['end_time']:
                        member_availability[u_name].add(curr)
                        curr += timedelta(minutes=30)

                if member_availability:
                    common_times_set = set.intersection(*member_availability.values())
                    sorted_times = sorted(list(common_times_set))
                    if sorted_times:
                        temp_start = sorted_times[0]
                        temp_curr = temp_start
                        for i in range(1, len(sorted_times)):
                            if sorted_times[i] == temp_curr + timedelta(minutes=30):
                                temp_curr = sorted_times[i]
                            else:
                                common_slots.append({'start': temp_start, 'end': temp_curr + timedelta(minutes=30)})
                                temp_start = sorted_times[i]
                                temp_curr = temp_start
                        common_slots.append({'start': temp_start, 'end': temp_curr + timedelta(minutes=30)})

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
                           my_slots=my_slots,
                           common_slots=common_slots,
                           year=year, month=month, days_in_month=days_in_month,
                           calendar=calendar)


def get_email_by_id(conn, uid):
    with conn.cursor() as cursor:
        cursor.execute("SELECT email FROM users WHERE user_id=%s", (uid,))
        res = cursor.fetchone()
        return res['email'] if res else None


# 3. 비는 시간 추가 (24시간제 UI 지원을 위해 입력 처리 로직 수정)
@app.route('/add_free_time', methods=['POST'])
@login_required
def add_free_time():
    group_id = request.form.get('group_id')
    invite_code = request.form.get('invite_code')
    date_str = request.form.get('date')

    # 24시간제 Select Box에서 값 받아오기
    start_hour = request.form.get('start_hour')
    start_min = request.form.get('start_min')
    end_hour = request.form.get('end_hour')
    end_min = request.form.get('end_min')

    conn = get_db_connection()
    try:
        # 시간 문자열 조립 (HH:MM)
        start_time_str = f"{start_hour}:{start_min}"
        end_time_str = f"{end_hour}:{end_min}"

        start_dt = datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date_str} {end_time_str}", "%Y-%m-%d %H:%M")

        # 종료 시간이 시작 시간보다 빠르면 무시
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


# ---------------------------------------------------------
# 기존 라우트 및 설정
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


def get_gemini_ootd_text(weather_data):
    try:
        prompt = f"날씨 {weather_data['status']}, 기온 {weather_data['temp']}. OOTD 추천 20자 내외."
        response = model.generate_content(prompt)
        return response.text
    except:
        return "날씨에 딱 맞는 따뜻한 코디를 추천해요! 🧥"


def get_gemini_place_recommendation(city="안성"):
    try:
        prompt = f"경기도 {city} 맛집/카페 추천 JSON 포맷: {{'name':.., 'tags':[], 'menu':..}}"
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except:
        return {"name": "추천 맛집", "tags": ["맛집"], "menu": "맛있는 메뉴"}


def get_gemini_activity_recommendation(weather_data, today_schedule):
    try:
        # 간단화된 프롬프트
        prompt = f"날씨 {weather_data['status']}에 맞는 자투리 시간 활동 2개 추천 JSON 리스트 포맷."
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except:
        return [{"title": "휴식", "desc": "잠시 쉬어가세요"}]


@app.route('/api/get_ootd', methods=['POST'])
def api_get_ootd():
    data = request.get_json()
    return jsonify({"text": get_gemini_ootd_text(data)})


@app.route('/api/get_place', methods=['POST'])
def api_get_place():
    return jsonify(get_gemini_place_recommendation("안성"))


@app.route('/api/get_activity', methods=['POST'])
@login_required
def api_get_activity():
    # ... (기존 로직 유지)
    return jsonify(get_gemini_activity_recommendation({}, []))


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