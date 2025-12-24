import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

def normalize_db_url(url: str) -> str:
    """
    DATABASE_URL을 SQLAlchemy가 이해할 형태로 정리.
    - sqlite:///./dev.db  (로컬 테스트용)  -> 그대로 사용
    - postgres://...      (Render/Heroku 스타일) -> postgresql+psycopg://... 로 변환
    - postgresql://...    -> postgresql+psycopg://... 로 변환
    """
    if not url:
        return url

    # SQLite는 그대로
    if url.startswith("sqlite:"):
        return url

    # Postgres URL 정규화
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


# ✅ 최종 정책:
# - DATABASE_URL이 없으면 로컬 개발 편의상 SQLite로 자동 fallback
# - 배포(Render)에서는 반드시 DATABASE_URL 환경변수를 설정해서 Postgres로 연결하면 됨
RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if RAW_DATABASE_URL:
    DATABASE_URL = normalize_db_url(RAW_DATABASE_URL)
else:
    # 로컬 테스트용 기본값 (프로젝트 루트에 dev.db 생성)
    DATABASE_URL = "sqlite:///./dev.db"


# SQLite일 때 connect_args 필요(멀티스레드 체크 완화)
engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
}

if DATABASE_URL.startswith("sqlite:"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
