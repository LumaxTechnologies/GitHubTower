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
        self.card_column_map_file = self.project_dir / "card_column_map.yaml"

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

    def save_card_column_map(self, cards: List[Dict[str, Any]]) -> bool:
        """Save card-to-column mapping to YAML.

        Creates a mapping file organized by column, showing which cards belong to each column.

        Args:
            cards: List of card definitions (must have 'column' field)

        Returns:
            True if save was successful, False otherwise
        """
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            
            # Organize cards by column
            column_map = {}
            for card in cards:
                column_name = card.get("column", "Unknown")
                if column_name not in column_map:
                    column_map[column_name] = []
                
                # Create a simplified card entry for the map
                card_entry = {
                    "note": card.get("note", ""),
                    "position": card.get("position", "top"),
                }
                # Include item_id if present (for Projects V2)
                if "item_id" in card:
                    card_entry["item_id"] = card.get("item_id")
                if "item_type" in card:
                    card_entry["item_type"] = card.get("item_type")
                if "github_id" in card:
                    card_entry["github_id"] = card.get("github_id")
                
                column_map[column_name].append(card_entry)
            
            # Convert to list format for YAML (ordered by column name)
            mapping_data = {
                "card_column_mapping": [
                    {
                        "column": column_name,
                        "cards": cards_list,
                        "card_count": len(cards_list)
                    }
                    for column_name, cards_list in sorted(column_map.items())
                ]
            }
            
            with open(self.card_column_map_file, "w", encoding="utf-8") as f:
                yaml.dump(mapping_data, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving card-column mapping YAML: {e}")
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

    def save_unified_project(self, project_data: Dict[str, Any], columns_data: List[Dict[str, Any]], cards_data: List[Dict[str, Any]]) -> bool:
        """Save project, columns, and cards in a single unified YAML file with tree structure.

        Structure:
            project:
              name: ...
              body: ...
              github_id: ...
              columns:
                - name: ...
                  position: ...
                  github_id: ...
                  cards:
                    - note: ...
                      position: ...

        Args:
            project_data: Project definition dictionary
            columns_data: List of column definitions
            cards_data: List of card definitions

        Returns:
            True if save was successful, False otherwise
        """
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            
            # Organize cards by column
            cards_by_column = {}
            for card in cards_data:
                column_name = card.get("column", "Unknown")
                if column_name not in cards_by_column:
                    cards_by_column[column_name] = []
                
                # Create card entry (exclude column name as it's implicit in the structure)
                card_entry = {}
                if "note" in card:
                    card_entry["note"] = card["note"]
                if "position" in card:
                    card_entry["position"] = card["position"]
                if "item_id" in card:
                    card_entry["item_id"] = card["item_id"]
                if "item_type" in card:
                    card_entry["item_type"] = card["item_type"]
                if "content_url" in card:
                    card_entry["content_url"] = card["content_url"]
                if "github_id" in card:
                    card_entry["github_id"] = card["github_id"]
                
                cards_by_column[column_name].append(card_entry)
            
            # Build unified structure
            unified_data = {
                "project": {
                    **project_data,
                    "columns": []
                }
            }
            
            # Add columns with their cards
            for col_data in columns_data:
                column_name = col_data.get("name", "")
                column_entry = {
                    "name": column_name,
                }
                if "position" in col_data:
                    column_entry["position"] = col_data["position"]
                if "github_id" in col_data:
                    column_entry["github_id"] = col_data["github_id"]
                if "field_id" in col_data:
                    column_entry["field_id"] = col_data["field_id"]
                
                # Add cards for this column
                if column_name in cards_by_column:
                    column_entry["cards"] = cards_by_column[column_name]
                else:
                    column_entry["cards"] = []
                
                unified_data["project"]["columns"].append(column_entry)
            
            # Save to a single file (use project.yaml as the unified file)
            with open(self.project_file, "w", encoding="utf-8") as f:
                yaml.dump(unified_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            return True
        except Exception as e:
            print(f"Error saving unified project YAML: {e}")
            return False

    def load_unified_project(self) -> Optional[Dict[str, Any]]:
        """Load unified project structure from YAML.

        Returns:
            Dictionary with project, columns, and cards, or None if file doesn't exist
        """
        if not self.project_file.exists():
            return None

        try:
            with open(self.project_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data
        except Exception as e:
            print(f"Error loading unified project YAML: {e}")
            return None

    def get_project_from_unified(self, unified_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract project data from unified structure.

        Args:
            unified_data: Unified project data structure

        Returns:
            Project definition dictionary
        """
        project_section = unified_data.get("project", {})
        if not project_section:
            return None
        
        # Extract project fields (exclude columns)
        project_data = {}
        for key in ["name", "body", "github_id", "github_node_id", "project_v2", "owner"]:
            if key in project_section:
                project_data[key] = project_section[key]
        
        return project_data if project_data else None

    def get_columns_from_unified(self, unified_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract columns data from unified structure.

        Args:
            unified_data: Unified project data structure

        Returns:
            List of column definitions
        """
        project_section = unified_data.get("project", {})
        columns = project_section.get("columns", [])
        
        # Extract column data (exclude cards)
        columns_data = []
        for col in columns:
            col_data = {}
            for key in ["name", "position", "github_id", "field_id"]:
                if key in col:
                    col_data[key] = col[key]
            columns_data.append(col_data)
        
        return columns_data

    def get_cards_from_unified(self, unified_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract cards data from unified structure.

        Args:
            unified_data: Unified project data structure

        Returns:
            List of card definitions
        """
        project_section = unified_data.get("project", {})
        columns = project_section.get("columns", [])
        
        cards_data = []
        for col in columns:
            column_name = col.get("name", "")
            cards = col.get("cards", [])
            
            for card in cards:
                card_data = {
                    "column": column_name,
                    **card  # Include all card fields
                }
                cards_data.append(card_data)
        
        return cards_data

