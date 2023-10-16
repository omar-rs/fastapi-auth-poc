import logging
import os

import httpx
import uvicorn
from fastapi import FastAPI
from starlette.responses import RedirectResponse

# publish_scope = 'posit:publish'
#
# auth = Auth0(domain=auth0_domain, api_audience=auth0_api_audience, scopes={
#     publish_scope: 'publish a content'
# })

logging.config.fileConfig('logging.conf', disable_existing_loggers=False)

logger = logging.getLogger(__name__)
app = FastAPI()

github_client_id = 'fc2e157d914ae7f2df9b'
github_client_secret = 'e774b9f8d6f736ab7291b5ee0c55398f938dc572'


@app.get('/github-login')
async def github_login():
    return RedirectResponse(f'https://github.com/login/oauth/authorize?client_id={github_client_id}',
                            status_code=302)


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
    async with httpx.AsyncClient() as client:
        headers.update({'Authorization': f'Bearer {access_token}'})
        response = await client.get('https://api.github.com/user', headers=headers)
    return response.json()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info("starting server on port {}".format(port))
    uvicorn.run("main_gh:app", host="0.0.0.0", port=port, log_level="warning", use_colors=True, reload=True)
