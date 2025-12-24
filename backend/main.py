import os
from datetime import date
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv()  # ✅ .env 로드 (가장 중요)

from sqlalchemy import Column, Integer, String, Date, Text, UniqueConstraint, select
from sqlalchemy.orm import Session

from .db import Base, engine, get_db


# =========================
# 상수/정책
# =========================
APP_TITLE = "친구 일정 공유 시스템"

START_DATE = date(2025, 12, 1)
END_DATE = date(2026, 12, 31)

FRIENDS = [
    {"key": "HJ", "name": "조현준", "color": "#ff2d2d", "env": "PASS_HJ"},
    {"key": "SK", "name": "김수겸", "color": "#2d6bff", "env": "PASS_SK"},
    {"key": "JH", "name": "장준호", "color": "#ff4dbe", "env": "PASS_JH"},
]


# =========================
# DB Models
# =========================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    key = Column(String(10), unique=True, nullable=False)     # HJ / SK / JH
    name = Column(String(50), nullable=False)                 # 표시 이름
    color = Column(String(20), nullable=False)                # HEX color
    passcode = Column(String(200), nullable=False)            # 간단 passcode(요구사항 그대로)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    day = Column(Date, nullable=False)
    owner_key = Column(String(10), nullable=False)            # HJ / SK / JH
    title = Column(String(120), nullable=False)
    note = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("day", "owner_key", name="uq_day_owner"),
    )


# =========================
# Schemas
# =========================
class LoginRequest(BaseModel):
    key: str
    passcode: str

class LoginResponse(BaseModel):
    ok: bool
    name: str
    color: str

class EventUpsertRequest(BaseModel):
    key: str                 # 누가 작성/수정? HJ/SK/JH
    passcode: str            # 해당 사용자 고유 암호
    day: date                # 일정 날짜
    title: str               # 일정 제목
    note: Optional[str] = "" # 메모

class EventDeleteRequest(BaseModel):
    key: str
    passcode: str
    day: date


class EventOut(BaseModel):
    day: date
    owner_key: str
    owner_name: str
    color: str
    title: str
    note: Optional[str] = ""


# =========================
# Helpers
# =========================
def ensure_env_ready():
    """
    요구사항: 친구별 고유 암호 env 필요
    """
    missing = []
    for f in FRIENDS:
        if not os.getenv(f["env"]):
            missing.append(f["env"])
    if missing:
        raise RuntimeError(f"{', '.join(missing)} 환경변수가 필요합니다.")


def in_range(d: date) -> bool:
    return START_DATE <= d <= END_DATE


def seed_users(db: Session):
    """
    최초 실행 시 3명 유저를 DB에 시드.
    - 환경변수 PASS_HJ/PASS_SK/PASS_JH 필수
    - 이미 있으면 업데이트(색상/이름/암호 반영)
    """
    ensure_env_ready()

    for f in FRIENDS:
        passcode = os.getenv(f["env"]).strip()
        existing = db.execute(select(User).where(User.key == f["key"])).scalar_one_or_none()
        if existing:
            existing.name = f["name"]
            existing.color = f["color"]
            existing.passcode = passcode
        else:
            db.add(User(key=f["key"], name=f["name"], color=f["color"], passcode=passcode))
    db.commit()


def auth_user(db: Session, key: str, passcode: str) -> User:
    key = key.strip().upper()
    u = db.execute(select(User).where(User.key == key)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="존재하지 않는 사용자입니다.")
    if u.passcode != passcode:
        raise HTTPException(status_code=401, detail="암호가 틀렸습니다.")
    return u


# =========================
# App
# =========================
app = FastAPI(title=APP_TITLE)


@app.on_event("startup")
def _startup():
    # 테이블 생성
    Base.metadata.create_all(bind=engine)

    # 유저 시드 (필요 env 없으면 여기서 명확하게 터짐)
    # -> 너 지금 보고있는 PASS_HJ 같은 에러는 여기서 나오는 게 정상임
    from sqlalchemy.orm import Session as _S
    with _S(bind=engine) as db:
        seed_users(db)


# =========================
# Routes
# =========================
@app.get("/health")
def health():
    return {"ok": True, "service": APP_TITLE, "range": {"from": str(START_DATE), "to": str(END_DATE)}}


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User)).scalars().all()
    return [
        {"key": u.key, "name": u.name, "color": u.color}
        for u in users
    ]


@app.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    u = auth_user(db, payload.key, payload.passcode)
    return LoginResponse(ok=True, name=u.name, color=u.color)


@app.get("/events", response_model=List[EventOut])
def get_events(from_date: Optional[date] = None, to_date: Optional[date] = None, db: Session = Depends(get_db)):
    # 기본: 전체 범위(2025-12 ~ 2026-12)
    fd = from_date or START_DATE
    td = to_date or END_DATE

    if fd < START_DATE:
        fd = START_DATE
    if td > END_DATE:
        td = END_DATE
    if fd > td:
        raise HTTPException(status_code=400, detail="날짜 범위가 이상합니다.")

    events = db.execute(
        select(Event).where(Event.day >= fd).where(Event.day <= td)
    ).scalars().all()

    # 사용자 맵
    users = {u.key: u for u in db.execute(select(User)).scalars().all()}

    out = []
    for e in events:
        u = users.get(e.owner_key)
        out.append(EventOut(
            day=e.day,
            owner_key=e.owner_key,
            owner_name=u.name if u else e.owner_key,
            color=u.color if u else "#999999",
            title=e.title,
            note=e.note or ""
        ))
    return out


@app.post("/events/upsert")
def upsert_event(payload: EventUpsertRequest, db: Session = Depends(get_db)):
    # 권한 체크
    u = auth_user(db, payload.key, payload.passcode)

    if not in_range(payload.day):
        raise HTTPException(status_code=400, detail="허용 범위(2025-12 ~ 2026-12) 밖입니다.")

    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title은 비어있을 수 없습니다.")

    note = (payload.note or "").strip()

    # 동일 (day, owner_key) 있으면 업데이트, 없으면 생성
    existing = db.execute(
        select(Event).where(Event.day == payload.day).where(Event.owner_key == u.key)
    ).scalar_one_or_none()

    if existing:
        existing.title = title
        existing.note = note
    else:
        db.add(Event(day=payload.day, owner_key=u.key, title=title, note=note))

    db.commit()
    return {"ok": True}


@app.post("/events/delete")
def delete_event(payload: EventDeleteRequest, db: Session = Depends(get_db)):
    u = auth_user(db, payload.key, payload.passcode)

    if not in_range(payload.day):
        raise HTTPException(status_code=400, detail="허용 범위(2025-12 ~ 2026-12) 밖입니다.")

    existing = db.execute(
        select(Event).where(Event.day == payload.day).where(Event.owner_key == u.key)
    ).scalar_one_or_none()

    if not existing:
        return {"ok": True, "deleted": 0}

    db.delete(existing)
    db.commit()
    return {"ok": True, "deleted": 1}


# =========================
# Friendly error
# =========================
@app.exception_handler(RuntimeError)
def runtime_error_handler(request, exc: RuntimeError):
    # env 누락 같은 문제를 프론트에서 보기 쉽게
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})
