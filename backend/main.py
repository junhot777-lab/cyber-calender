import os
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base


# ----------------------------
# 설정
# ----------------------------
# Render에선 DATABASE_URL 환경변수로 Postgres URL 넣는게 정석
# 없으면 로컬용 sqlite로 동작
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL".lower())
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./dev.db"

# Render Postgres가 "postgres://"로 주는 경우가 있어서 보정
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# sqlite는 check_same_thread 옵션 필요
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ----------------------------
# DB 모델
# ----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    key = Column(String(20), unique=True, index=True, nullable=False)  # 예: HJ, KS, JH
    name = Column(String(50), nullable=False)
    color = Column(String(30), nullable=True)  # 예: red/blue/pink
    passcode = Column(String(200), nullable=False)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    user_key = Column(String(20), index=True, nullable=False)
    date = Column(String(20), index=True, nullable=False)  # "YYYY-MM-DD"
    title = Column(Text, nullable=False)


# ----------------------------
# 앱 초기화
# ----------------------------
app = FastAPI(title="친구 일정 공유 시스템")

# CORS (친구들 브라우저에서 호출할 수도 있으니 넉넉하게)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 프로젝트 루트 기준 static 폴더
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ----------------------------
# DB 준비 + 기본 유저 시드
# ----------------------------
def init_db_and_seed():
    Base.metadata.create_all(bind=engine)

    # 환경변수에서 비번 가져오기 (Render env vars에 PASS_HJ 같은거 넣었지?)
    # 없으면 기본값 "1234" (배포할 땐 바꾸셈, 안 바꾸면 친구가 아니라 랜덤이 들어온다)
    pass_hj = os.getenv("PASS_HJ", "1234")
    pass_ks = os.getenv("PASS_KS", "1234")
    pass_jh = os.getenv("PASS_JH", "1234")

    default_users = [
        ("HJ", "조현준", "red", pass_hj),
        ("KS", "김수겸", "blue", pass_ks),
        ("JH", "장준호", "hotpink", pass_jh),
    ]

    db = SessionLocal()
    try:
        for key, name, color, passcode in default_users:
            exists = db.query(User).filter(User.key == key).first()
            if not exists:
                db.add(User(key=key, name=name, color=color, passcode=passcode))
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    init_db_and_seed()


# ----------------------------
# 라우팅
# ----------------------------
@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=500, detail="static/index.html not found")
    return FileResponse(index_path)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def list_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return [{"key": u.key, "name": u.name, "color": u.color} for u in users]
    finally:
        db.close()


@app.post("/login")
def login(user_key: str, passcode: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.key == user_key).first()
        if not user or user.passcode != passcode:
            raise HTTPException(status_code=401, detail="인증 실패")
        return {"success": True, "key": user.key, "name": user.name, "color": user.color}
    finally:
        db.close()


@app.get("/events")
def get_events(user_key: Optional[str] = None):
    db = SessionLocal()
    try:
        q = db.query(Event)
        if user_key:
            q = q.filter(Event.user_key == user_key)
        events = q.order_by(Event.date.asc(), Event.id.asc()).all()
        return [{"id": e.id, "user_key": e.user_key, "date": e.date, "title": e.title} for e in events]
    finally:
        db.close()


@app.post("/events/upsert")
def upsert_event(user_key: str, passcode: str, date: str, title: str):
    # 인증
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.key == user_key).first()
        if not user or user.passcode != passcode:
            raise HTTPException(status_code=401, detail="권한 없음")

        # 같은 유저/같은 날짜 이벤트는 1개로 유지 (있으면 수정, 없으면 생성)
        ev = db.query(Event).filter(Event.user_key == user_key, Event.date == date).first()
        if ev:
            ev.title = title
        else:
            ev = Event(user_key=user_key, date=date, title=title)
            db.add(ev)

        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.post("/events/delete")
def delete_event(user_key: str, passcode: str, event_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.key == user_key).first()
        if not user or user.passcode != passcode:
            raise HTTPException(status_code=401, detail="권한 없음")

        ev = db.query(Event).filter(Event.id == event_id).first()
        if not ev:
            raise HTTPException(status_code=404, detail="일정 없음")

        # 남 삭제 방지: 자기 키만 삭제 가능
        if ev.user_key != user_key:
            raise HTTPException(status_code=403, detail="남의 일정 삭제 금지")

        db.delete(ev)
        db.commit()
        return {"success": True}
    finally:
        db.close()
