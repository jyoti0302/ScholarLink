"""
Stage 5.2: Student Authentication Backend (`backend/api/auth.py`).

Implements:
- Salted `hashlib.scrypt` password hashing with self-describing parameters and
  constant-time verification (`hmac.compare_digest`).
- Dependency-free RFC 7519 JWT Bearer tokens signed with HMAC-SHA256 (`HS256`)
  using `JWT_SECRET_KEY` loaded strictly from environment configuration.
- `get_current_student` FastAPI dependency for ownership-enforced student routes.
- `POST /auth/register`, `POST /auth/login`, and `GET /auth/me`.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.schemas import (
    AuthTokenResponseSchema,
    StudentAuthSummarySchema,
    StudentLoginRequestSchema,
    StudentRegisterRequestSchema,
)
from backend.database.connection import get_db
from backend.database.models import Student

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
_bearer_scheme = HTTPBearer(auto_error=False)

# scrypt parameters (OWASP-aligned interactive login cost; stored in every hash string)
SCRYPT_N = 16384  # 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_SALT_BYTES = 16
SCRYPT_MAXMEM = 64 * 1024 * 1024  # 64 MiB

JWT_ALGORITHM = "HS256"
MIN_JWT_SECRET_LENGTH = 32
DEFAULT_JWT_EXPIRE_MINUTES = 1440  # 24 hours
_WEAK_SECRET_VALUES = {
    "changeme",
    "secret",
    "default",
    "replace-with-a-strong-random-secret-key-at-least-32-chars",
    "your-secret-key",
}

_EMAIL_RE = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$")


# -------------------------------------------------------------------------
# Email & Password Validation / Hashing
# -------------------------------------------------------------------------

def normalize_email(raw_email: str) -> str:
    return (raw_email or "").strip().lower()


def validate_email_format(email: str) -> str:
    norm = normalize_email(email)
    if not norm or len(norm) > 255 or not _EMAIL_RE.match(norm):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a valid email address.",
        )
    return norm


def validate_password_strength(password: str) -> None:
    if not password or len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters long.",
        )
    if len(password) > 128:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must not exceed 128 characters.",
        )
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must contain at least one letter and one number.",
        )


def hash_password(password: str) -> str:
    """Hashes a plaintext password with hashlib.scrypt and a unique 16-byte random salt."""
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=SCRYPT_DKLEN,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    dk_b64 = base64.urlsafe_b64encode(dk).decode("ascii")
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt_b64}${dk_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a plaintext password against a stored scrypt hash in constant time."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = base64.urlsafe_b64decode(parts[4].encode("ascii"))
        expected_dk = base64.urlsafe_b64decode(parts[5].encode("ascii"))
        candidate_dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=SCRYPT_MAXMEM,
            dklen=len(expected_dk),
        )
        return hmac.compare_digest(candidate_dk, expected_dk)
    except Exception:
        return False


# -------------------------------------------------------------------------
# Signed HMAC-SHA256 JWT Helpers (Dependency-Free)
# -------------------------------------------------------------------------

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


def _get_jwt_secret() -> bytes:
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret or len(secret) < MIN_JWT_SECRET_LENGTH or secret.lower() in _WEAK_SECRET_VALUES:
        logger.error("JWT_SECRET_KEY is missing or too weak (must be >= %d characters).", MIN_JWT_SECRET_LENGTH)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not properly configured.",
        )
    return secret.encode("utf-8")


def _get_jwt_expire_seconds() -> int:
    raw = os.getenv("JWT_EXPIRE_MINUTES", str(DEFAULT_JWT_EXPIRE_MINUTES)).strip()
    try:
        minutes = int(raw)
        if minutes <= 0:
            minutes = DEFAULT_JWT_EXPIRE_MINUTES
    except ValueError:
        minutes = DEFAULT_JWT_EXPIRE_MINUTES
    return minutes * 60


def create_access_token(student_id: int) -> Tuple[str, int]:
    """Creates a signed HS256 JWT containing only sub (student_id), iat, and exp."""
    secret = _get_jwt_secret()
    expires_in = _get_jwt_expire_seconds()
    now = int(time.time())

    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(student_id),
        "iat": now,
        "exp": now + expires_in,
    }
    h_seg = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    p_seg = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{h_seg}.{p_seg}".encode("ascii")
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{h_seg}.{p_seg}.{_b64url_encode(sig)}", expires_in


def decode_and_verify_token(token: str) -> Dict[str, Any]:
    """
    Strictly verifies HS256 signature, header algorithm (never trusting untrusted `alg`),
    token structure, `sub`, `iat`, and `exp`.
    """
    secret = _get_jwt_secret()
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token or token.count(".") != 2:
        raise unauthorized

    h_seg, p_seg, s_seg = token.split(".")
    try:
        header = json.loads(_b64url_decode(h_seg).decode("utf-8"))
        if not isinstance(header, dict) or header.get("alg") != JWT_ALGORITHM or header.get("typ") != "JWT":
            raise unauthorized

        signing_input = f"{h_seg}.{p_seg}".encode("ascii")
        expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
        provided_sig = _b64url_decode(s_seg)
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise unauthorized

        payload = json.loads(_b64url_decode(p_seg).decode("utf-8"))
        if not isinstance(payload, dict):
            raise unauthorized

        exp = payload.get("exp")
        iat = payload.get("iat")
        sub = payload.get("sub")
        now = int(time.time())
        if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)):
            raise unauthorized
        if now >= exp:
            raise unauthorized
        if not isinstance(sub, str) or not sub.isdigit() or int(sub) <= 0:
            raise unauthorized
        return payload
    except HTTPException:
        raise
    except Exception:
        raise unauthorized


# -------------------------------------------------------------------------
# Reusable FastAPI Dependency
# -------------------------------------------------------------------------

def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Student:
    """
    Extracts and verifies the Bearer JWT, then resolves and returns the
    authenticated Student ORM object from the database.
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_and_verify_token(credentials.credentials)
    student_id = int(payload["sub"])

    try:
        student = db.query(Student).filter(Student.id == student_id).first()
    except SQLAlchemyError as exc:
        logger.exception("Database error resolving authenticated student: %s", exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return student


# -------------------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------------------

@router.post("/register", response_model=AuthTokenResponseSchema, status_code=status.HTTP_201_CREATED)
def register_student(
    payload: StudentRegisterRequestSchema,
    db: Session = Depends(get_db),
):
    email = validate_email_format(payload.email)
    validate_password_strength(payload.password)

    # Validate JWT secret before creating DB records so misconfiguration never leaves orphan users
    _get_jwt_secret()

    student = Student(
        email=email,
        password_hash=hash_password(payload.password),
    )
    try:
        db.add(student)
        db.commit()
        db.refresh(student)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error during student registration: %s", exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    token, expires_in = create_access_token(student.id)
    return AuthTokenResponseSchema(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        student=StudentAuthSummarySchema.model_validate(student),
    )


@router.post("/login", response_model=AuthTokenResponseSchema)
def login_student(
    payload: StudentLoginRequestSchema,
    db: Session = Depends(get_db),
):
    email = normalize_email(payload.email)
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not email or not payload.password:
        raise invalid_exc

    try:
        student = db.query(Student).filter(Student.email == email).first()
    except SQLAlchemyError as exc:
        logger.exception("Database error during student login: %s", exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc

    if not student or not verify_password(payload.password, student.password_hash):
        raise invalid_exc

    token, expires_in = create_access_token(student.id)
    return AuthTokenResponseSchema(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        student=StudentAuthSummarySchema.model_validate(student),
    )


@router.get("/me", response_model=StudentAuthSummarySchema)
def get_authenticated_student(current_student: Student = Depends(get_current_student)):
    return StudentAuthSummarySchema.model_validate(current_student)
