"""账号与鉴权：注册、登录、会话、绑定与访问控制（零第三方依赖）。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from . import database as db

ROLES = ("user", "guardian", "doctor")
SESSION_DAYS = 7
_ITER = 120_000


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITER).hex()


def _public(acct: dict) -> dict:
    return {
        "id": acct["id"],
        "username": acct["username"],
        "role": acct["role"],
        "display_name": acct.get("display_name"),
        "created_at": acct.get("created_at"),
    }


def create_account(username: str, password: str, role: str, display_name: str | None = None) -> dict:
    if role not in ROLES:
        raise ValueError("非法角色")
    if not username or len(password) < 6:
        raise ValueError("用户名不能为空，密码至少 6 位")
    if db.query_one("SELECT id FROM accounts WHERE username=?", (username,)):
        raise ValueError("用户名已存在")
    salt = secrets.token_hex(16)
    aid = db.new_id("acct_")
    db.execute(
        "INSERT INTO accounts(id,username,password_hash,salt,role,display_name,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (aid, username, _hash(password, salt), salt, role, display_name or username, db.now()),
    )
    return db.query_one("SELECT * FROM accounts WHERE id=?", (aid,))


def verify_login(username: str, password: str) -> dict | None:
    acct = db.query_one("SELECT * FROM accounts WHERE username=?", (username,))
    if not acct:
        return None
    if hmac.compare_digest(_hash(password, acct["salt"]), acct["password_hash"]):
        return acct
    return None


def create_session(account: dict) -> str:
    token = secrets.token_hex(32)
    exp = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO sessions(token,account_id,role,created_at,expires_at) VALUES(?,?,?,?,?)",
        (token, account["id"], account["role"], db.now(), exp),
    )
    return token


def account_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    row = db.query_one("SELECT * FROM sessions WHERE token=?", (token,))
    if not row:
        return None
    if row.get("expires_at") and row["expires_at"] < db.now():
        db.execute("DELETE FROM sessions WHERE token=?", (token,))
        return None
    return db.query_one("SELECT * FROM accounts WHERE id=?", (row["account_id"],))


def account_from_request(request) -> dict | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return account_from_token(auth[7:].strip())
    return None


def logout(token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token=?", (token,))


def bind(account_id: str, user_id: str, role: str) -> str:
    existing = db.query_one("SELECT id FROM bindings WHERE account_id=? AND user_id=?", (account_id, user_id))
    if existing:
        return existing["id"]
    bid = db.new_id("b_")
    db.execute(
        "INSERT INTO bindings(id,account_id,user_id,role,created_at) VALUES(?,?,?,?,?)",
        (bid, account_id, user_id, role, db.now()),
    )
    return bid


def bindings_for_account(account_id: str) -> list[dict]:
    return db.query("SELECT * FROM bindings WHERE account_id=?", (account_id,))


def accounts_for_user(user_id: str) -> list[dict]:
    rows = db.query(
        "SELECT b.id AS binding_id, b.role AS binding_role, a.id, a.username, a.display_name, a.role "
        "FROM bindings b JOIN accounts a ON a.id=b.account_id WHERE b.user_id=?",
        (user_id,),
    )
    return rows


def can_access(account: dict | None, user_id: str) -> bool:
    if not account:
        return False
    return bool(db.query_one(
        "SELECT id FROM bindings WHERE account_id=? AND user_id=?", (account["id"], user_id)))


def user_ids_for(account: dict | None) -> list[str]:
    if not account:
        return []
    return [r["user_id"] for r in db.query(
        "SELECT user_id FROM bindings WHERE account_id=?", (account["id"],))]


def me_payload(account: dict) -> dict:
    return {
        "account": _public(account),
        "bindings": [
            {"user_id": b["user_id"], "role": b["role"]}
            for b in bindings_for_account(account["id"])
        ],
    }
