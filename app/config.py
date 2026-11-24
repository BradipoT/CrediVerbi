import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://crediverbi:crediverbi@localhost:5432/crediverbi",
        )
        self.token = os.getenv("CREDIVERBI_TOKEN", "")


settings = Settings()
