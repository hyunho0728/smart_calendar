// static/script.js

let currentSelectedDay = null;

function selectDate(day) {
    currentSelectedDay = day;

    // 1. 시각적 효과
    document.querySelectorAll('.cal-cell').forEach(el => el.classList.remove('selected'));
    const selectedCell = document.getElementById('cell-' + day);
    if (selectedCell) selectedCell.classList.add('selected');

    // 2. 날짜 제목 (JS에서 월 이름 배열 사용)
    const monthNames = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    const dateTitle = document.getElementById('sidebar-date-title');
    if (dateTitle) {
        dateTitle.innerText = `Selected: ${monthNames[currentMonth]} ${day}, ${currentYear}`;
    }

    // 3. 일정 리스트 갱신
    const listContainer = document.getElementById('sidebar-event-list');
    listContainer.innerHTML = "";

    // [중요] 키 생성 로직 변경 (현재 보고 있는 년/월 사용)
    // 예: 2025, 11, 5 -> "2025-11-05"
    const mStr = currentMonth < 10 ? '0' + currentMonth : currentMonth;
    const dStr = day < 10 ? '0' + day : day;
    const dateKey = `${currentYear}-${mStr}-${dStr}`;

    if (typeof serverEvents !== 'undefined' && serverEvents[dateKey] && serverEvents[dateKey].length > 0) {
        serverEvents[dateKey].forEach(event => {
            const p = document.createElement('p');
            let timeHtml = event.time ? `<span style="color: #0056b3; font-weight:bold; margin-right: 5px;">${event.time}</span>` : '';
            p.innerHTML = `${timeHtml}${event.title}`;
            p.style.borderBottom = "1px dashed #ddd";
            p.style.padding = "8px 0";
            listContainer.appendChild(p);
        });
    } else {
        listContainer.innerHTML = `<p style="color: #aaa;">등록된 일정이 없습니다.</p>`;
    }
}

function openModal() {
    const modal = document.getElementById('eventModal');
    const dateInput = document.getElementById('modal-date-input');

    // [중요] 모달 창 날짜 기본값 설정
    const mStr = currentMonth < 10 ? '0' + currentMonth : currentMonth;

    if (currentSelectedDay) {
        const dStr = currentSelectedDay < 10 ? '0' + currentSelectedDay : currentSelectedDay;
        dateInput.value = `${currentYear}-${mStr}-${dStr}`;
    } else {
        // 선택 안했으면 해당 월 1일로
        dateInput.value = `${currentYear}-${mStr}-01`;
    }

    modal.style.display = 'block';
}

function closeModal() {
    document.getElementById('eventModal').style.display = 'none';
}

window.onclick = function(event) {
    const modal = document.getElementById('eventModal');
    if (event.target == modal) {
        modal.style.display = "none";
    }
}