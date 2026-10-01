"""Settings for the agent, read from environment variables.

Outside Docker the values come from the .env file in the repository root (see
.env.example). In Docker, compose passes the same variables into the container.
"""

import os

from dotenv import find_dotenv, load_dotenv


class ConfigError(Exception):
    pass


class Settings:
    def __init__(self):
        self.azure_endpoint = ""
        self.azure_api_key = ""
        self.azure_deployment = ""
        self.azure_api_version = ""
        self.ticket_api_url = ""


def load_settings() -> Settings:
    # Reads a .env file if there is one, searching upwards from the working directory.
    # A variable that is already set in the environment is not overwritten.
    load_dotenv(find_dotenv(usecwd=True))

    settings = Settings()
    settings.azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    settings.azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    settings.azure_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
    settings.azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "")
    settings.ticket_api_url = os.environ.get("TICKET_API_URL", "http://localhost:8080")

    missing = []
    if settings.azure_endpoint == "":
        missing.append("AZURE_OPENAI_ENDPOINT")
    if settings.azure_api_key == "":
        missing.append("AZURE_OPENAI_API_KEY")
    if settings.azure_deployment == "":
        missing.append("AZURE_OPENAI_DEPLOYMENT")
    if settings.azure_api_version == "":
        missing.append("AZURE_OPENAI_API_VERSION")

    if len(missing) > 0:
        names = ", ".join(missing)
        raise ConfigError(
            f"Missing settings: {names}. Copy .env.example to .env and fill in the values."
        )

    return settings
