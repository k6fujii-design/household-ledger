from functools import lru_cache

import boto3

from app.core.config import settings


def _ssm_parameter(name: str) -> str:
    client = boto3.client("ssm", region_name=settings.aws_region)
    response = client.get_parameter(
        Name=name,
        WithDecryption=True,
    )
    return response["Parameter"]["Value"]


@lru_cache(maxsize=1)
def initial_user_password() -> str:
    if not settings.initial_user_password_parameter_name:
        return settings.initial_user_password

    return _ssm_parameter(settings.initial_user_password_parameter_name)


@lru_cache(maxsize=1)
def line_channel_secret() -> str | None:
    if settings.line_channel_secret_parameter_name:
        return _ssm_parameter(settings.line_channel_secret_parameter_name)
    return settings.line_channel_secret


@lru_cache(maxsize=1)
def line_channel_access_token() -> str | None:
    if settings.line_channel_access_token_parameter_name:
        return _ssm_parameter(settings.line_channel_access_token_parameter_name)
    return settings.line_channel_access_token
