PROJECT_NAME_HYPHEN=fastapi-auth-poc
PROJECT_NAME_UNDERSCORE=fastapi_auth_poc

pyenv:
	pyenv virtualenv-delete --force $(PROJECT_NAME_HYPHEN)
	pyenv virtualenv 3.9.13 $(PROJECT_NAME_HYPHEN)
	pyenv local $(PROJECT_NAME_HYPHEN)

configure-cloudsmith-index-url:
	$(eval CLOUDSMITH_TOKEN:=$(shell aws secretsmanager get-secret-value --secret-id lucid.production.cloudsmith.token --output text --query SecretString --region us-east-1))
	$(eval PIP_INDEX_URL:="https://token:$(CLOUDSMITH_TOKEN)@dl.posit.co/basic/hosted/python/simple/")

deps: configure-cloudsmith-index-url
	PIP_INDEX_URL=$(PIP_INDEX_URL) pip install -r requirements.txt