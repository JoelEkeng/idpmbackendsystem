import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, status
from app.core.config import get_settings

settings = get_settings()

jwks_client = PyJWKClient(settings.BETTERAUTH_PUBLIC_KEY)


def verify_token(token: str):
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )