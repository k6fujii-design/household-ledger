from functools import lru_cache

import boto3

from app.core.config import settings


@lru_cache(maxsize=1)
def initial_user_password() -> str:
    if not settings.initial_user_password_parameter_name:
        return settings.initial_user_password

    client = boto3.client("ssm", region_name=settings.aws_region)
    response = client.get_parameter(
        Name=settings.initial_user_password_parameter_name,
        WithDecryption=True,
    )
    return response["Parameter"]["Value"]
