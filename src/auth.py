from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from deps.config import Config


class UnauthorizedException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail=detail)


class UnauthenticatedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Requires authentication"
        )


class Jwt(BaseModel):
    sub: str = Field()


class JwksClient:
    def __init__(self, config: Annotated[Config, Depends(Config)]) -> None:
        # This gets the JWKS from a given URL and does processing so you can
        # use any of the keys available
        jwks_url = f"https://{config.auth0_domain}/.well-known/jwks.json"
        self.client = jwt.PyJWKClient(jwks_url)

    def key(self, credentials: str) -> str:
        return self.client.get_signing_key_from_jwt(credentials).key


async def verify_token(
    config: Annotated[Config, Depends(Config)],
    jwks_client: Annotated[JwksClient, Depends(JwksClient)],
    token: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer()),
) -> Jwt:
    if token is None:
        raise UnauthenticatedException

    # This gets the 'kid' from the passed token
    try:
        signing_key = jwks_client.key(token.credentials)
    except jwt.exceptions.PyJWKClientError as error:
        raise UnauthorizedException(str(error))
    except jwt.exceptions.DecodeError as error:
        raise UnauthorizedException(str(error))

    try:
        payload = jwt.decode(
            token.credentials,
            signing_key,
            algorithms=config.auth0_algorithms,
            audience=config.auth0_api_audience,
            issuer=config.auth0_issuer,
        )
    except Exception as error:
        raise UnauthorizedException(str(error))

    return Jwt(**payload)
