"""Configuration management for GitHubTower."""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
# Try current directory first, then config directory
load_dotenv()  # Current working directory
config_env_path = Path.home() / ".githubtower" / ".env"
if config_env_path.exists():
    load_dotenv(config_env_path)  # Config directory


class Config:
    """Configuration manager for GitHubTower."""

    def __init__(self, config_dir: Optional[Path] = None, projects_dir: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_dir: Optional custom configuration directory.
                       Defaults to ~/.githubtower
            projects_dir: Optional custom projects directory.
                         If provided, overrides the default projects directory.
                         Defaults to config_dir / "projects"
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path.home() / ".githubtower"

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "config.yaml"
        
        if projects_dir:
            self.projects_dir = Path(projects_dir)
        else:
            self.projects_dir = self.config_dir / "projects"

        # Create projects directory if it doesn't exist
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    @property
    def github_token(self) -> Optional[str]:
        """Get GitHub token from environment or config."""
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            token = os.getenv("GH_TOKEN")
        return token

    @property
    def github_org(self) -> Optional[str]:
        """Get GitHub organization from environment."""
        return os.getenv("GITHUB_ORG")

    def get_project_dir(self, project_name: str) -> Path:
        """Get the directory for a specific project.

        Args:
            project_name: Name of the project

        Returns:
            Path to the project directory
        """
        return self.projects_dir / project_name

    def ensure_project_dir(self, project_name: str) -> Path:
        """Ensure project directory exists and return its path.

        Args:
            project_name: Name of the project

        Returns:
            Path to the project directory
        """
        project_dir = self.get_project_dir(project_name)
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

