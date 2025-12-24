let token = null;
let me = null; // {id,name,color}

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "요청 실패");
  }
  return data;
}

function showModal({ title, foot, withNote=false }) {
  $("modalTitle").textContent = title || "암호 확인";
  $("modalFoot").textContent = foot || "";
  $("modalPass").value = "";
  $("modalNote").value = "";
  $("modalNote").style.display = withNote ? "block" : "none";
  $("modal").style.display = "grid";

  return new Promise((resolve, reject) => {
    const cleanup = () => {
      $("modalOk").onclick = null;
      $("modalCancel").onclick = null;
      $("modal").style.display = "none";
    };

    $("modalCancel").onclick = () => {
      cleanup();
      reject(new Error("취소"));
    };

    $("modalOk").onclick = () => {
      const pass = $("modalPass").value.trim();
      const note = $("modalNote").value.trim();
      cleanup();
      resolve({ passcode: pass, note });
    };
  });
}

function setMeBadge(text, color=null) {
  const badge = $("meBadge");
  badge.textContent = text;
  if (color) {
    badge.style.borderColor = `${color}55`;
    badge.style.boxShadow = `0 0 22px ${color}22`;
  } else {
    badge.style.borderColor = "rgba(255,255,255,0.14)";
    badge.style.boxShadow = "none";
  }
}

function buildLegend(users) {
  const box = $("legend");
  box.innerHTML = "";
  users.forEach(u => {
    const tag = document.createElement("div");
    tag.className = "tag";
    const dot = document.createElement("div");
    dot.className = "dot";
    dot.style.background = u.color;
    tag.appendChild(dot);
    const txt = document.createElement("div");
    txt.textContent = u.name;
    tag.appendChild(txt);
    box.appendChild(tag);
  });
}

let calendar;

async function init() {
  // 유저 목록 로드
  const users = await api("/api/users");
  const sel = $("userSelect");
  sel.innerHTML = "";
  users.forEach(u => {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = `${u.name} (${u.id})`;
    sel.appendChild(opt);
  });
  buildLegend(users);

  $("loginBtn").onclick = async () => {
    const user_id = sel.value;
    const passcode = $("passInput").value;
    try {
      const out = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ user_id, passcode })
      });
      token = out.token;
      me = { id: out.user_id, name: out.name, color: out.color };

      $("loginCard").style.display = "none";
      $("calendarCard").style.display = "block";
      $("logoutBtn").style.display = "inline-block";
      setMeBadge(`${me.name} ONLINE`, me.color);

      initCalendar();
    } catch (e) {
      alert(e.message);
    }
  };

  $("logoutBtn").onclick = () => {
    token = null;
    me = null;
    $("calendarCard").style.display = "none";
    $("loginCard").style.display = "block";
    $("logoutBtn").style.display = "none";
    setMeBadge("OFFLINE", null);
    if (calendar) {
      calendar.destroy();
      calendar = null;
    }
  };

  setMeBadge("OFFLINE");
}

function initCalendar() {
  const calEl = document.getElementById("calendar");

  calendar = new FullCalendar.Calendar(calEl, {
    initialView: "dayGridMonth",
    timeZone: "UTC",
    height: "auto",

    // 범위 제한: 2025-12 ~ 2026-12
    validRange: {
      start: "2025-12-01",
      end: "2027-01-01" // end는 exclusive라 2027-01-01로
    },
    initialDate: "2025-12-01",

    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "dayGridMonth,timeGridWeek,timeGridDay"
    },

    selectable: true,
    editable: false, // 드래그로 수정은 막고, 클릭 기반으로만 수정하게 (암호 모달 때문)

    events: async (info, success, failure) => {
      try {
        const data = await api(`/api/events?start=${encodeURIComponent(info.startStr)}&end=${encodeURIComponent(info.endStr)}`);
        success(data);
      } catch (e) {
        failure(e);
      }
    },

    select: async (selInfo) => {
      try {
        const title = prompt("일정 제목 입력");
        if (!title) return;

        const { passcode, note } = await showModal({
          title: "일정 추가: 수정 암호 확인",
          foot: "추가도 ‘수정권한’이라 암호 필요. 네 규칙이니까.",
          withNote: true
        });

        await api("/api/events", {
          method: "POST",
          body: JSON.stringify({
            title,
            start_at: selInfo.startStr,
            end_at: selInfo.endStr,
            all_day: selInfo.allDay,
            note: note || null,
            passcode
          })
        });

        calendar.refetchEvents();
      } catch (e) {
        if (e.message !== "취소") alert(e.message);
      }
    },

    eventClick: async (clickInfo) => {
      const ev = clickInfo.event;
      const ownerId = ev.extendedProps.ownerUserId;
      const ownerName = ev.extendedProps.ownerName;

      const isMine = me && ownerId === me.id;

      // 작성자 아니면 수정/삭제 메뉴 자체를 안 줌 (쓸데없는 분노 방지)
      if (!isMine) {
        alert(`이 일정은 ${ownerName} 작성이라 너는 손대면 안 됨.`);
        return;
      }

      const action = prompt("입력: edit / delete");
      if (!action) return;

      try {
        if (action === "delete") {
          const { passcode } = await showModal({
            title: "삭제: 수정 암호 확인",
            foot: "삭제는 되돌릴 수 없음. 인간의 결심 체크."
          });

          await api(`/api/events/${ev.id}?passcode=${encodeURIComponent(passcode)}`, {
            method: "DELETE"
          });

          calendar.refetchEvents();
          return;
        }

        if (action === "edit") {
          const newTitle = prompt("새 제목", ev.title) ?? ev.title;

          const { passcode, note } = await showModal({
            title: "수정: 수정 암호 확인",
            foot: "작성자만 수정 가능 + 암호도 필요. 네가 원한 지옥 룰.",
            withNote: true
          });

          await api(`/api/events/${ev.id}`, {
            method: "PUT",
            body: JSON.stringify({
              title: newTitle,
              note: note || ev.extendedProps.note || null,
              passcode
            })
          });

          calendar.refetchEvents();
          return;
        }

        alert("edit 또는 delete만.");
      } catch (e) {
        if (e.message !== "취소") alert(e.message);
      }
    }
  });

  calendar.render();
}

init();
