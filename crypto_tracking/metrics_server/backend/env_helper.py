import os
from pathlib import Path

from dotenv import dotenv_values

from crypto_tracking.logging_config import logger


class EnvHelper:
    """Class to get environment variables."""

    def __init__(self) -> None:
        self.project_folder: Path = Path(__file__).resolve().parents[3]
        assert self.project_folder.name == "crypto_tracking", "Project folder not found"

    def get_env_var(self, name: str) -> str:
        """Get the environment variable or load it from the .env file if it's not found."""
        variable: str | None = os.environ.get(name)

        if variable is None:
            env_path: Path = self.project_folder / ".env"
            if env_path.exists():
                env_vars = dotenv_values(".env")
                if variable := env_vars.get(name):
                    logger.info("Environment variable %s loaded from .env file", name)
                    return variable

            raise AssertionError(f"Environment variable {name} not found in env nor in .env file")

        logger.info("Environment variable %s loaded from environment", name)
        return variable
