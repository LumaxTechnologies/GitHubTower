"""YAML file handlers for project definitions."""

from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml


class ProjectYAML:
    """Handler for project YAML definitions."""

    def __init__(self, project_dir: Path):
        """Initialize YAML handler.

        Args:
            project_dir: Directory containing project YAML files
        """
        self.project_dir = Path(project_dir)
        self.project_file = self.project_dir / "project.yaml"
        self.columns_file = self.project_dir / "columns.yaml"
        self.cards_file = self.project_dir / "cards.yaml"

    def load_project(self) -> Optional[Dict[str, Any]]:
        """Load project definition from YAML.

        Returns:
            Project definition dictionary or None if file doesn't exist
        """
        if not self.project_file.exists():
            return None

        try:
            with open(self.project_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading project YAML: {e}")
            return None

    def save_project(self, project_data: Dict[str, Any]) -> bool:
        """Save project definition to YAML.

        Args:
            project_data: Project definition dictionary

        Returns:
            True if save was successful, False otherwise
        """
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            with open(self.project_file, "w", encoding="utf-8") as f:
                yaml.dump(project_data, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving project YAML: {e}")
            return False

    def load_columns(self) -> List[Dict[str, Any]]:
        """Load columns definition from YAML.

        Returns:
            List of column definitions
        """
        if not self.columns_file.exists():
            return []

        try:
            with open(self.columns_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("columns", []) if data else []
        except Exception as e:
            print(f"Error loading columns YAML: {e}")
            return []

    def save_columns(self, columns: List[Dict[str, Any]]) -> bool:
        """Save columns definition to YAML.

        Args:
            columns: List of column definitions

        Returns:
            True if save was successful, False otherwise
        """
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            with open(self.columns_file, "w", encoding="utf-8") as f:
                yaml.dump({"columns": columns}, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving columns YAML: {e}")
            return False

    def load_cards(self) -> List[Dict[str, Any]]:
        """Load cards definition from YAML.

        Returns:
            List of card definitions
        """
        if not self.cards_file.exists():
            return []

        try:
            with open(self.cards_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("cards", []) if data else []
        except Exception as e:
            print(f"Error loading cards YAML: {e}")
            return []

    def save_cards(self, cards: List[Dict[str, Any]]) -> bool:
        """Save cards definition to YAML.

        Args:
            cards: List of card definitions

        Returns:
            True if save was successful, False otherwise
        """
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cards_file, "w", encoding="utf-8") as f:
                yaml.dump({"cards": cards}, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving cards YAML: {e}")
            return False

    def create_template(self) -> bool:
        """Create template YAML files for a new project.

        Returns:
            True if templates were created successfully
        """
        # Create project.yaml template
        project_template = {
            "name": "My Project",
            "body": "Project description",
            "owner": None,  # Will use default from config
            "github_id": None,  # Will be set after creation
        }

        # Create columns.yaml template
        columns_template = {
            "columns": [
                {"name": "To Do", "position": 1},
                {"name": "In Progress", "position": 2},
                {"name": "Done", "position": 3},
            ]
        }

        # Create cards.yaml template
        cards_template = {
            "cards": [
                {
                    "note": "Example card",
                    "column": "To Do",
                    "position": "top",
                }
            ]
        }

        success = True
        success &= self.save_project(project_template)
        success &= self.save_columns(columns_template["columns"])
        success &= self.save_cards(cards_template["cards"])

        return success

