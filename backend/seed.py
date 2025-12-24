import os
from sqlalchemy.orm import Session
from .models import User
from .auth import hash_passcode

USERS = [
    {"id": "hj", "name": "조현준", "color": "#ff3b3b", "env": "PASS_HJ"},
    {"id": "sk", "name": "김수겸", "color": "#3b6bff", "env": "PASS_SK"},
    {"id": "jh", "name": "장준호", "color": "#ff4fd8", "env": "PASS_JH"},
]

def seed_users(db: Session):
    # 이미 있으면 건드리지 않음(운영에서 갑자기 비번 바뀌면 난리남)
    for u in USERS:
        existing = db.get(User, u["id"])
        if existing:
            continue

        passcode = os.getenv(u["env"])
        if not passcode:
            raise RuntimeError(f"{u['env']} 환경변수가 필요합니다.")

        user = User(
            id=u["id"],
            name=u["name"],
            color=u["color"],
            passcode_hash=hash_passcode(passcode),
        )
        db.add(user)

    db.commit()
