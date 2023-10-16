import httpx
import logging
import os
from dotenv import load_dotenv
import uvicorn

from fastapi import FastAPI, Depends, Security
from fastapi_auth0 import Auth0, Auth0User

load_dotenv()

auth0_domain = os.getenv('AUTH0_DOMAIN')
auth0_api_audience = os.getenv('AUTH0_API_AUDIENCE')
auth0_mgmt_client_id = os.getenv('AUTH0_MGMT_CLIENT_ID')
auth0_mgmt_client_secret = os.getenv('AUTH0_MGMT_CLIENT_SECRET')

publish_scope = 'posit:publish'

auth = Auth0(domain=auth0_domain, api_audience=auth0_api_audience, scopes={
    publish_scope: 'publish a content'
})

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)

logger = logging.getLogger(__name__)
app = FastAPI()


async def get_gh_user_profile(user_id: str):
    headers = {'Accept': 'application/json'}
    data = {
        'client_id': auth0_mgmt_client_id,
        'client_secret': auth0_mgmt_client_secret,
        'audience': f'https://{auth0_domain}/api/v2/',
        'grant_type': 'client_credentials',
    }
    # get the auth0 mgmt api access token
    async with httpx.AsyncClient() as client:
        response = await client.post(url=f'https://{auth0_domain}/oauth/token',
                                     headers=headers,
                                     data=data)
    response_json = response.json()
    mgmt_access_token = response_json['access_token']
    logger.info(f"mgmt_access_token={mgmt_access_token}")

    # get the gh user profile
    headers = {
        'Accept': 'application/json',
        'authorization': f'Bearer {mgmt_access_token}'
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url=f'https://{auth0_domain}/api/v2/users/{user_id}',
                                    headers=headers)
    response_json = response.json()
    logger.info(f"response_json={response_json}")
    return response_json


@app.get("/public")
async def get_public():
    logger.info("called /public")
    return {"user": "anonymous"}


@app.get("/secure", dependencies=[Depends(auth.implicit_scheme)])
async def get_secure_implicit_oauth_flow_no_scopes_required(user: Auth0User = Security(auth.get_user)):
    logger.info("called /secure, dep=auth.implicit_scheme, required scopes=[]")
    gh_user_profile = await get_gh_user_profile(user.id)
    return {"user": f"{user}", "identities": f"{gh_user_profile['identities']}"}


@app.get("/secure/publish", dependencies=[Depends(auth.implicit_scheme)])
async def get_secure_implicit_oauth_flow_requires_scope(user: Auth0User = Security(auth.get_user,
                                                                                   scopes=[publish_scope])):
    logger.info(f"called /secure/publish using auth.implicit_scheme, required scopes=[{publish_scope}]")
    gh_user_profile = await get_gh_user_profile(user.id)
    return {"user": f"{user}", "identities": f"{gh_user_profile['identities']}"}


@app.get("/secure/publish2")
async def get_secure_bearer_flow_requires_scope(user: Auth0User = Security(auth.get_user, scopes=["publish_scope"])):
    logger.info(f"called /secure/publish2 using M2M bearer token, required scopes=[{publish_scope}]")
    return {"user": f"{user}"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info("starting server on port {}".format(port))
    uvicorn.run("main_auth0:app", host="0.0.0.0", port=port, log_level="warning", use_colors=True, reload=True)
