import os


class Settings:
    line_channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
    line_channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    notion_token = os.getenv("NOTION_TOKEN", "")
    notion_database_id = os.getenv("NOTION_DATABASE_ID", "")
    app_base_url = os.getenv("APP_BASE_URL", "")


settings = Settings()
