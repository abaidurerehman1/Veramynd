"""Auth API: signup, login, verify, logout, password reset, Google OAuth."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..layout import UPLOADS_DIR
from .config import settings
from .db import get_db, init_db
from .emailer import send_password_reset_email, send_verification_email
from .models import DashboardProject, EmailToken, User
from .security import (
    create_access_token,
    decode_access_token,
    hash_password,
    new_email_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "veramynd_token"
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,118}$")
_AVATAR_DIR = UPLOADS_DIR / "avatars"
_AVATAR_MAX_BYTES = 2 * 1024 * 1024
_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

oauth = OAuth()
_oauth_ready = False


def _ensure_oauth() -> bool:
    global _oauth_ready
    cfg = settings()
    cid = str(cfg["google_client_id"])
    secret = str(cfg["google_client_secret"])
    if not cid or not secret:
        return False
    if not _oauth_ready:
        oauth.register(
            name="google",
            client_id=cid,
            client_secret=secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth_ready = True
    return True


class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        name = " ".join(v.strip().split())
        if not _NAME_RE.match(name):
            raise ValueError("Name must use letters only (spaces and - ' . allowed)")
        return name

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must include letters and a number")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must include letters and a number")
        return v


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must include letters and a number")
        return v


class ProfileUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        name = " ".join(v.strip().split())
        if not _NAME_RE.match(name):
            raise ValueError("Name must use letters only (spaces and - ' . allowed)")
        return name


class ProjectLinkIn(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=255)
    meta_json: str | None = None


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=int(settings()["jwt_expire_hours"]) * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _avatar_public_url(user: User) -> str | None:
    raw = (user.avatar_url or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("/"):
        return raw
    return f"/api/auth/avatars/{Path(raw).name}"


def _clear_local_avatar_files(user_id: int) -> None:
    if not _AVATAR_DIR.is_dir():
        return
    for path in _AVATAR_DIR.glob(f"{user_id}.*"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "email_verified": user.email_verified,
        "oauth_provider": user.oauth_provider,
        "avatar_url": _avatar_public_url(user),
    }


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    auth = request.headers.get("Authorization") or ""
    if not token and auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        raise HTTPException(401, "Not authenticated")
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(401, "Invalid or expired session")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")
    return user


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


def _issue_email_token(db: Session, user: User, purpose: str, hours: int = 24) -> str:
    raw = new_email_token()
    row = EmailToken(
        user_id=user.id,
        token=raw,
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
        used=False,
    )
    db.add(row)
    db.commit()
    return raw


@router.get("/providers")
def auth_providers() -> dict:
    return {"google": _ensure_oauth()}


@router.post("/signup")
def signup(body: SignupIn, db: Annotated[Session, Depends(get_db)]) -> dict:
    email = body.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(400, "An account with this email already exists")

    user = User(
        name=body.name,
        email=email,
        password_hash=hash_password(body.password),
        email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = _issue_email_token(db, user, "verify", hours=48)
    verify_url = f"{settings()['app_base_url']}/verify-email?token={token}"
    try:
        send_verification_email(user.email, user.name, verify_url)
    except Exception as e:
        raise HTTPException(502, f"Account created but verification email failed: {e}") from e

    return {
        "ok": True,
        "message": "Check your email to verify your account before signing in.",
        "user": _user_out(user),
    }


@router.get("/verify-email")
def verify_email(token: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    row = db.scalar(select(EmailToken).where(EmailToken.token == token, EmailToken.purpose == "verify"))
    if not row or row.used:
        raise HTTPException(400, "Invalid or already used verification link")
    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Verification link expired")

    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(400, "User not found")
    user.email_verified = True
    row.used = True
    db.commit()
    return {"ok": True, "message": "Email verified. You can sign in now."}


@router.post("/login")
def login(body: LoginIn, response: Response, db: Annotated[Session, Depends(get_db)]) -> dict:
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.email_verified:
        raise HTTPException(403, "Please verify your email before signing in")

    token = create_access_token(user.id, user.email)
    _set_auth_cookie(response, token)
    return {"ok": True, "token": token, "user": _user_out(user)}


@router.post("/logout")
def logout(response: Response) -> dict:
    _clear_auth_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(user: Annotated[User, Depends(get_current_user)]) -> dict:
    return {"user": _user_out(user)}


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn, db: Annotated[Session, Depends(get_db)]) -> dict:
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    # Always return ok to avoid email enumeration
    if user and user.password_hash:
        token = _issue_email_token(db, user, "reset", hours=2)
        reset_url = f"{settings()['app_base_url']}/reset-password?token={token}"
        try:
            send_password_reset_email(user.email, user.name, reset_url)
        except Exception as e:
            raise HTTPException(502, f"Could not send reset email: {e}") from e
    return {"ok": True, "message": "If that email exists, a reset link was sent."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordIn, db: Annotated[Session, Depends(get_db)]) -> dict:
    row = db.scalar(select(EmailToken).where(EmailToken.token == body.token, EmailToken.purpose == "reset"))
    if not row or row.used:
        raise HTTPException(400, "Invalid or already used reset link")
    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset link expired")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(400, "User not found")
    user.password_hash = hash_password(body.password)
    user.email_verified = True
    row.used = True
    db.commit()
    return {"ok": True, "message": "Password updated. You can sign in now."}


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    if not user.password_hash:
        raise HTTPException(400, "This account uses Google sign-in. Set a password via reset email first.")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True, "message": "Password changed"}


@router.patch("/profile")
def update_profile(
    body: ProfileUpdateIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    user.name = body.name
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_out(user)}


@router.post("/avatar")
async def upload_avatar(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> dict:
    content_type = (file.content_type or "").lower().strip()
    ext = _AVATAR_TYPES.get(content_type)
    if not ext:
        raise HTTPException(400, "Use a JPG, PNG, WEBP, or GIF image")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > _AVATAR_MAX_BYTES:
        raise HTTPException(400, "Image must be 2MB or smaller")

    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    _clear_local_avatar_files(user.id)
    dest = _AVATAR_DIR / f"{user.id}{ext}"
    dest.write_bytes(data)
    user.avatar_url = f"/api/auth/avatars/{dest.name}"
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_out(user)}


@router.delete("/avatar")
def delete_avatar(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _clear_local_avatar_files(user.id)
    user.avatar_url = None
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _user_out(user)}


@router.get("/avatars/{filename}")
def get_avatar_file(filename: str) -> FileResponse:
    safe = Path(filename).name
    if not re.fullmatch(r"\d+\.(jpg|jpeg|png|webp|gif)", safe, flags=re.I):
        raise HTTPException(404, "Not found")
    path = _AVATAR_DIR / safe
    if not path.is_file():
        raise HTTPException(404, "Not found")
    media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media)


@router.get("/oauth/google/start")
async def google_start(request: Request):
    if not _ensure_oauth():
        raise HTTPException(400, "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
    redirect_uri = str(settings()["google_redirect_uri"])
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/oauth/google/callback")
async def google_callback(request: Request, db: Annotated[Session, Depends(get_db)]):
    if not _ensure_oauth():
        raise HTTPException(400, "Google OAuth is not configured")
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(400, f"Google OAuth failed: {e}") from e

    info = token.get("userinfo")
    if not info:
        raise HTTPException(400, "Google did not return user info")

    email = str(info.get("email") or "").lower().strip()
    sub = str(info.get("sub") or "")
    name = str(info.get("name") or email.split("@")[0] or "User")
    picture = str(info.get("picture") or "").strip() or None
    if not email or not sub:
        raise HTTPException(400, "Google account is missing email")

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            name=name[:120],
            email=email,
            password_hash=None,
            email_verified=True,
            oauth_provider="google",
            oauth_sub=sub,
            avatar_url=picture,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email_verified = True
        user.oauth_provider = user.oauth_provider or "google"
        user.oauth_sub = user.oauth_sub or sub
        if not user.name:
            user.name = name[:120]
        if picture and not (user.avatar_url or "").startswith("/api/auth/avatars/"):
            user.avatar_url = picture
        db.commit()

    jwt_token = create_access_token(user.id, user.email)
    redirect = RedirectResponse(url=f"{settings()['app_base_url']}/oauth/callback")
    _set_auth_cookie(redirect, jwt_token)
    return redirect


@router.get("/projects")
def list_my_projects(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    rows = db.scalars(select(DashboardProject).where(DashboardProject.owner_id == user.id)).all()
    return {
        "projects": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "name": r.name,
                "meta_json": r.meta_json,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/projects")
def link_project(
    body: ProjectLinkIn,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    existing = db.scalar(
        select(DashboardProject).where(
            DashboardProject.owner_id == user.id,
            DashboardProject.project_id == body.project_id,
        )
    )
    if existing:
        existing.name = body.name or existing.name
        existing.meta_json = body.meta_json if body.meta_json is not None else existing.meta_json
        db.commit()
        return {"ok": True, "id": existing.id}

    row = DashboardProject(
        owner_id=user.id,
        project_id=body.project_id,
        name=body.name or body.project_id,
        meta_json=body.meta_json,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id}


def bootstrap_auth() -> None:
    try:
        init_db()
    except Exception as e:
        # Keep API up even if Postgres is temporarily unavailable.
        print(f"WARN: auth DB init skipped: {e}")
    try:
        _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"WARN: avatar dir create skipped: {e}")
    try:
        _ensure_oauth()
    except Exception as e:
        print(f"WARN: oauth init skipped: {e}")
