from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    session_secret: str = "change-me-local-secret"
    initial_user_password: str = "password"
    initial_user_password_parameter_name: str | None = None
    initial_user_1_name: str = "User 1"
    initial_user_2_name: str = "User 2"
    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    line_channel_secret_parameter_name: str | None = None
    line_channel_access_token_parameter_name: str | None = None
    line_agent_mode: str = "rules"
    line_agent_trace_enabled: bool = True
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    aws_region: str = "ap-northeast-1"
    aws_access_key_id: str = "local"
    aws_secret_access_key: str = "local"
    dynamodb_table_name: str = "household-budget-app"
    dynamodb_endpoint_url: str | None = None
    dynamodb_auto_create: bool = True


settings = Settings()
