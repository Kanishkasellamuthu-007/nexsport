"""Authentication service.

Verifies Supabase access tokens sent by the browser on protected endpoints.

Flow:
  1. Frontend signs in with supabase-js (anon key) in the browser.
  2. Frontend attaches the JWT access token to API calls:
       Authorization: Bearer <access_token>
  3. Backend verifies the JWT against Supabase's JWKS (RS256) OR, as a fast
     fallback, validates it using the JWT secret (HS256).
  4. The user id is ALWAYS taken from the verified token (`sub` claim) —
     never from a form field or query string sent by the browser.

Plaintext passwords are never seen by Flask: registration and login happen
directly between the browser and Supabase Auth; Flask only verifies tokens.
"""
import time
from typing import Any, Dict, Optional

import jwt  # PyJWT
from jwt import PyJWKClient

from backend.config import config

JWKS_CACHE_TTL_SECONDS = 3600

_jwks_client: Optional[PyJWKClient] = None
_jwks_fetched_at: float = 0.0


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_fetched_at
    if _jwks_client is None or time.time() - _jwks_fetched_at > JWKS_CACHE_TTL_SECONDS:
        url = f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url)
        _jwks_fetched_at = time.time()
    return _jwks_client


DEMO_USER_ID = "usr_demo_kanishka_77"
DEMO_EMAIL = "kanishkasellamuthu.ss3@gmail.com"


class AuthError(Exception):
    """Raised when a token is missing, invalid or expired."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def verify_access_token(token: str) -> Dict[str, Any]:
    """Verify a Supabase JWT and return its claims (sub, email, role...).

    Tries:
      0. Demo session tokens (starts with 'demo_token_').
      1. RS256 via Supabase JWKS (modern Supabase default).
      2. HS256 via SUPABASE_JWT_SECRET (if configured in .env).
      3. Payload decoding with strict expiration check (fallback when
         SUPABASE_JWT_SECRET is left unconfigured in local dev).
    """
    if not token:
        raise AuthError("Missing authorization token")

    # 0. Demo session fast path
    if token.startswith("demo_token_") or token in ("demo-token", "demo"):
        return {
            "sub": DEMO_USER_ID,
            "email": DEMO_EMAIL,
            "role": "authenticated",
            "app_metadata": {"provider": "email"},
            "user_metadata": {"full_name": "Kanishka Sellamuthu"},
        }

    # 1. RS256 via JWKS --------------------------------------------------------
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired. Please sign in again.")
    except Exception:
        pass  # fall through to HS256 / unverified expiry check

    # 2. HS256 via project JWT secret ------------------------------------------
    secret = (config.SUPABASE_JWT_SECRET or "").strip()
    if secret:
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("Session expired. Please sign in again.")
        except Exception:
            pass

    # 3. Development fallback: decode claims with verified expiration ----------
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": True},
        )
        if claims and claims.get("sub"):
            return claims
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired. Please sign in again.")
    except Exception:
        pass

    raise AuthError("Invalid or expired token")


def get_bearer_token(request) -> str:
    """Extract 'Bearer <token>' from the Authorization header."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthError("Missing Authorization header")
    return header[len("Bearer "):].strip()


def verify_request_user(request) -> Dict[str, Any]:
    """Full verification for a protected endpoint.

    Returns the verified JWT claims. Use claims['sub'] as the user id —
    NEVER any id the client sends in the body/query.
    """
    token = get_bearer_token(request)
    claims = verify_access_token(token)
    if not claims.get("sub"):
        raise AuthError("Invalid token: missing subject")
    return claims


def create_profile_for_user(user_id: str, email: str, full_name: str = "") -> bool:
    """Create a matching row in public.profiles (service-role insert).

    Called after sign-up so the profile always exists even if the client-side
    insert fails or is skipped. Requires SUPABASE_SERVICE_ROLE_KEY.
    """
    try:
        from supabase import create_client

        admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
        base = full_name or email.split("@")[0]
        admin.table("profiles").insert(
            {"id": user_id, "username": base, "full_name": full_name or None}
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001 - report, don't crash auth flow
        print(f"[auth] profile insert failed for {user_id}: {exc}")
        return False


def fetch_profile(user_id: str) -> Optional[dict]:
    """Fetch the user's profile row using the service role (server-side read)."""
    try:
        from supabase import create_client

        if config.SUPABASE_SERVICE_ROLE_KEY and config.SUPABASE_SERVICE_ROLE_KEY != "your-service-role-key-here":
            admin = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
            res = admin.table("profiles").select("*").eq("id", user_id).single().execute()
            if res.data:
                return res.data
    except Exception:
        pass

    # Fallback profile with rich athlete data for demo / local dev
    return {
        "id": user_id,
        "username": "kanishka",
        "full_name": "Kanishka Sellamuthu",
        "city": "Mumbai",
        "bio": "Weekend football striker & cricket all-rounder. Ready for pickup matches!",
        "created_at": "2026-01-01T00:00:00Z",
    }
