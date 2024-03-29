import httpx
import logging
import os
from dotenv import load_dotenv
import pprint
from datetime import datetime, timedelta
from typing import Annotated, Optional, Dict

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Security, status, Request
from fastapi.openapi.models import OAuthFlows, OAuthFlowImplicit
from fastapi.security import (
    OAuth2,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes,
)
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ValidationError

load_dotenv()

# to get a string like this run:
# openssl rand -hex 32
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

github_client_id = os.getenv('GH_CLIENT_ID')
github_client_secret = os.getenv('GH_CLIENT_SECRET')

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)
logger = logging.getLogger(__name__)

fake_users_db = {
    # password: secret
    "johndoe": {
        "username": "johndoe",
        "full_name": "John Doe",
        "email": "johndoe@example.com",
        "hashed_password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        "disabled": False,
    },
    "alice": {
        "username": "alice",
        "full_name": "Alice Chains",
        "email": "alicechains@example.com",
        "hashed_password": "$2b$12$gSvqqUPvlXP2tfVFaWK1Be7DlH.PKZbv5H8KnzzVgXXbVxpva.pFm",
        "disabled": True,
    },
}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    scopes: list[str] = []


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None


class UserInDB(User):
    hashed_password: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# oauth2_scheme = OAuth2PasswordBearer(
#     tokenUrl="token",
#     scopes={"me": "Read information about the current user.", "items": "Read items."},
# )


class OAuth2ImplicitBearer(OAuth2):
    def __init__(self,
                 authorization_url: str,
                 scopes=None,
                 scheme_name: Optional[str] = None):
        if scopes is None:
            scopes = {}
        flows = OAuthFlows(implicit=OAuthFlowImplicit(authorizationUrl=authorization_url, scopes=scopes))
        super().__init__(flows=flows, scheme_name=scheme_name)

    async def __call__(self, request: Request) -> Optional[str]:
        # Overwrite parent call to prevent useless overhead, the actual auth is done in Auth0.get_user
        # This scheme is just for Swagger UI
        return None


oauth2_scheme = OAuth2ImplicitBearer(
    authorization_url='https://github.com/login/oauth/authorize',
    scopes={"me": "Read information about the current user.", "items": "Read items."},
    scheme_name='GH social'
)

app = FastAPI()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
        security_scopes: SecurityScopes, token: Annotated[str, Depends(oauth2_scheme)]
):
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_scopes = payload.get("scopes", [])
        token_data = TokenData(scopes=token_scopes, username=username)
    except (JWTError, ValidationError):
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )
    logger.info(f"Inside get_current_user, \npayload:{pprint.pformat(payload)} \nuser:{user}")
    return user


async def get_current_active_user(
        current_user: Annotated[User, Security(get_current_user, scopes=["me"])]
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# @app.post("/token", response_model=Token)
# async def login_for_access_token(
#         form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
# ):
#     user = authenticate_user(fake_users_db, form_data.username, form_data.password)
#     if not user:
#         raise HTTPException(status_code=400, detail="Incorrect username or password")
#     access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     access_token = create_access_token(
#         data={"sub": user.username, "scopes": form_data.scopes},
#         expires_delta=access_token_expires,
#     )
#     logger.info(f"After login with user/pass, generated access_token is: {access_token}")
#     return {"access_token": access_token, "token_type": "bearer"}

# NOTE: this url needs to match the GH app's callback URL
@app.get('/github-code')
async def github_code(code: str):
    params = {
        'client_id': github_client_id,
        'client_secret': github_client_secret,
        'code': code
    }
    headers = {'Accept': 'application/json'}
    async with httpx.AsyncClient() as client:
        response = await client.post(url='https://github.com/login/oauth/access_token',
                                     params=params, headers=headers)
    response_json = response.json()
    access_token = response_json['access_token']
    return access_token


@app.get("/users/me/", response_model=User, dependencies=[Depends(oauth2_scheme)])
async def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user


@app.get("/users/me/items/")
async def read_own_items(current_user: Annotated[User, Security(get_current_active_user, scopes=["items"])]):
    return [{"item_id": "Foo", "owner": current_user.username}]


@app.get("/status/", dependencies=[Depends(oauth2_scheme)])
async def read_system_status(current_user: Annotated[User, Depends(get_current_user)]):
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info("starting server on port {}".format(port))
    uvicorn.run("main_oauth2_scopes:app", host="0.0.0.0", port=port, log_level="warning", use_colors=True, reload=True)
