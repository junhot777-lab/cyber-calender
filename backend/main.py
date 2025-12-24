import os
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# -----------------------------
# 환경변수
# -----------------------------
# Render에서 Environment Variables로 넣은 값들
PASS_HJ = os.getenv("PASS_HJ", "").strip()
PASS_KS = os.getenv("PASS_KS", "").strip()
PASS_JH = os.getenv("PASS_JH", "").strip()

# 기본 사용자 목록(고정 3명)
USERS = [
    {"id": "HJ", "name": "HJ", "pass_env": "PASS_HJ", "password": PASS_HJ},
    {"id": "KS", "name": "KS", "pass_env": "PASS_KS", "password": PASS_KS},
    {"id": "JH", "name": "JH", "pass_env": "PASS_JH", "password": PASS_JH},
]

# 간단 DB: JSON 파일로 저장 (Render에서도 디스크는 일단 동작, 다만 free 플랜은 재배포/재시작 시 날아갈 수 있음)
# 제대로 영구 저장하려면 Postgres 붙여야 하는데, 너 지금 급한 건 "작동"이잖아.
DATA_PATH = os.getenv("DATA_PATH", "data.json")


def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_PATH):
        return {"events": []}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"events": []}


def save_data(data: Dict[str, Any]) -> None:
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# -----------------------------
# Pydantic 모델
# -----------------------------
class LoginBody(BaseModel):
    user_id: str
    password: str


class EventCreate(BaseModel):
    user_id: str
    password: str
    title: str
    day: str  # "YYYY-MM-DD"
    time: Optional[str] = None  # "HH:MM" optional
    memo: Optional[str] = ""


class EventUpdate(BaseModel):
    user_id: str
    password: str
    title: Optional[str] = None
    time: Optional[str] = None
    memo: Optional[str] = None


# -----------------------------
# FastAPI 앱
# -----------------------------
app = FastAPI(title="Cyber Calendar", version="1.0.0")

# 정적 파일(프론트) 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    # 루트에서 index.html 제공 (Render에서 빈 화면/404 뜨던 거 여기서 끝냄)
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}


# -----------------------------
# 유틸: 인증
# -----------------------------
def require_login(user_id: str, password: str) -> Dict[str, str]:
    user_id = (user_id or "").strip()
    password = (password or "").strip()

    user = next((u for u in USERS if u["id"] == user_id), None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")

    if not user["password"]:
        # 환경변수 자체가 비어있으면 서버가 인증 불가
        raise HTTPException(
            status_code=500,
            detail=f"Server missing env var {user['pass_env']}. Set it on Render.",
        )

    if password != user["password"]:
        raise HTTPException(status_code=401, detail="Wrong password")

    return {"id": user["id"], "name": user["name"]}


# -----------------------------
# API: 사용자 목록 (프론트가 /api/users 부르니까 반드시 있어야 함)
# -----------------------------
@app.get("/api/users")
def api_users():
    # 비번은 절대 내려주지 않음 (세상에…)
    return [{"id": u["id"], "name": u["name"]} for u in USERS]


# -----------------------------
# API: 로그인
# -----------------------------
@app.post("/api/login")
def api_login(body: LoginBody):
    user = require_login(body.user_id, body.password)
    return {"ok": True, "user": user}


# -----------------------------
# API: 이벤트 CRUD
# -----------------------------
@app.get("/api/events")
def api_list_events():
    data = load_data()
    events = data.get("events", [])
    # 정렬(날짜/시간)
    def key(e):
        return (e.get("day", ""), e.get("time") or "99:99", e.get("id", ""))
    events = sorted(events, key=key)
    return {"events": events}


@app.post("/api/events")
def api_create_event(body: EventCreate):
    user = require_login(body.user_id, body.password)

    # 날짜 검증
    try:
        date.fromisoformat(body.day)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid day (YYYY-MM-DD)")

    if body.time:
        # 아주 가벼운 시간 검증
        try:
            hh, mm = body.time.split(":")
            int(hh), int(mm)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid time (HH:MM)")

    data = load_data()
    events = data.get("events", [])

    new_id = f"e{int(datetime.utcnow().timestamp() * 1000)}"
    ev = {
        "id": new_id,
        "owner": user["id"],
        "title": body.title.strip(),
        "day": body.day,
        "time": (body.time or "").strip() or None,
        "memo": (body.memo or "").strip(),
        "created_at": datetime.utcnow().isoformat(),
    }
    events.append(ev)
    data["events"] = events
    save_data(data)
    return {"ok": True, "event": ev}


@app.patch("/api/events/{event_id}")
def api_update_event(event_id: str, body: EventUpdate):
    user = require_login(body.user_id, body.password)

    data = load_data()
    events = data.get("events", [])

    ev = next((x for x in events if x.get("id") == event_id), None)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    if ev.get("owner") != user["id"]:
        raise HTTPException(status_code=403, detail="Only owner can edit")

    if body.title is not None:
        ev["title"] = body.title.strip()
    if body.time is not None:
        t = body.time.strip()
        ev["time"] = t if t else None
    if body.memo is not None:
        ev["memo"] = body.memo.strip()

    ev["updated_at"] = datetime.utcnow().isoformat()
    save_data(data)
    return {"ok": True, "event": ev}


@app.delete("/api/events/{event_id}")
def api_delete_event(event_id: str, user_id: str, password: str):
    user = require_login(user_id, password)

    data = load_data()
    events = data.get("events", [])

    ev = next((x for x in events if x.get("id") == event_id), None)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    if ev.get("owner") != user["id"]:
        raise HTTPException(status_code=403, detail="Only owner can delete")

    data["events"] = [x for x in events if x.get("id") != event_id]
    save_data(data)
    return {"ok": True}
