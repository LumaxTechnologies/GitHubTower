"""Synchronization between local YAML files and GitHub Projects."""

from typing import Dict, List, Optional, Any
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .github_api import GitHubProjectManager
from .yaml_handler import ProjectYAML
from .config import Config

console = Console()


class ProjectSyncer:
    """Synchronize local YAML definitions with GitHub Projects."""

    def __init__(self, config: Config, github_manager: GitHubProjectManager):
        """Initialize syncer.

        Args:
            config: Configuration instance
            github_manager: GitHub API manager instance
        """
        self.config = config
        self.github = github_manager

    def sync_to_github(self, project_name: str, create_if_missing: bool = True) -> bool:
        """Sync local YAML files to GitHub.

        Args:
            project_name: Name of the project to sync
            create_if_missing: Create project on GitHub if it doesn't exist

        Returns:
            True if sync was successful
        """
        project_dir = self.config.get_project_dir(project_name)
        if not project_dir.exists():
            console.print(f"[red]Project directory not found: {project_dir}[/red]")
            return False

        yaml_handler = ProjectYAML(project_dir)
        project_data = yaml_handler.load_project()

        if not project_data:
            # Project YAML doesn't exist, try to fetch from GitHub and create it
            console.print(f"[yellow]Project YAML not found. Attempting to fetch from GitHub...[/yellow]")
            
            # Try to find the project on GitHub
            project = None
            project_v2_data = None
            
            # Check if it's an organization project (Projects V2)
            target_owner = self.config.github_org
            is_org = False
            
            if target_owner:
                try:
                    org = self.github.github.get_organization(target_owner)
                    is_org = True
                except Exception:
                    pass

            if is_org:
                # Try Projects V2 (GraphQL) first
                try:
                    owner_id = self.github._get_owner_node_id(target_owner)
                    projects_v2 = self.github._list_projects_via_graphql(owner_id)
                    
                    for proj_data in projects_v2:
                        if proj_data.get("title") == project_name:
                            project_v2_data = proj_data
                            break
                except Exception:
                    pass

            # If not found in V2, try Projects classic
            if not project_v2_data:
                project = self.github.get_project_by_name(project_name)

            if project_v2_data:
                # Create project data from V2
                project_data = {
                    "name": project_v2_data.get("title", project_name),
                    "body": project_v2_data.get("shortDescription", ""),
                    "github_id": project_v2_data.get("number"),
                    "github_node_id": project_v2_data.get("id"),
                    "project_v2": True,
                }
                yaml_handler.save_project(project_data)
                console.print(f"[green]Created project.yaml from GitHub Projects V2[/green]")
            elif project:
                # Create project data from classic project
                project_data = {
                    "name": project.name,
                    "body": project.body or "",
                    "github_id": project.id,
                }
                yaml_handler.save_project(project_data)
                console.print(f"[green]Created project.yaml from GitHub[/green]")
            else:
                console.print(f"[red]Project YAML not found and project not found on GitHub[/red]")
                console.print(f"[cyan]Create the project first with: githubtower create {project_name}[/cyan]")
                return False

        # Check if this is a Projects V2 project
        is_v2 = project_data.get("project_v2", False)
        
        if is_v2:
            # Projects V2 - limited sync support
            console.print(f"[yellow]Note: This is a Projects V2 (beta) project. Full sync not yet supported.[/yellow]")
            console.print(f"[green]Project metadata synced: {project_name}[/green]")
            return True

        # Get or create project (Projects classic)
        project = None
        if project_data.get("github_id"):
            project = self.github.get_project(project_data["github_id"])

        if not project:
            if create_if_missing:
                console.print(f"[yellow]Project not found on GitHub, creating...[/yellow]")
                project = self.github.create_project(
                    name=project_data["name"],
                    body=project_data.get("body"),
                    owner=project_data.get("owner"),
                )
                if project:
                    project_data["github_id"] = project.id
                    yaml_handler.save_project(project_data)
                    console.print(f"[green]Created project: {project.name} (ID: {project.id})[/green]")
            else:
                console.print(f"[red]Project not found on GitHub and create_if_missing=False[/red]")
                return False

        if not project:
            console.print(f"[red]Failed to get or create project[/red]")
            return False

        # Sync columns
        columns_data = yaml_handler.load_columns()
        if columns_data:
            self._sync_columns(project, columns_data)

        # Sync cards
        cards_data = yaml_handler.load_cards()
        if cards_data:
            self._sync_cards(project, cards_data)

        console.print(f"[green]Successfully synced project: {project_name}[/green]")
        return True

    def sync_from_github(self, project_name: str, github_id: Optional[int] = None) -> bool:
        """Sync GitHub project to local YAML files.

        Supports both Projects (classic) via REST API and Projects V2 (beta) via GraphQL.

        Args:
            project_name: Name of the project
            github_id: Optional GitHub project ID. If not provided, searches by name.

        Returns:
            True if sync was successful
        """
        project_dir = self.config.ensure_project_dir(project_name)
        yaml_handler = ProjectYAML(project_dir)

        # Try to get project from GitHub
        project = None
        project_v2_data = None
        
        # Determine if we're looking for an organization project
        target_owner = self.config.github_org
        is_org = False
        
        if target_owner:
            try:
                org = self.github.github.get_organization(target_owner)
                is_org = True
            except Exception:
                pass

        if is_org:
            # Try Projects V2 (GraphQL) first for organizations
            try:
                owner_id = self.github._get_owner_node_id(target_owner)
                projects_v2 = self.github._list_projects_via_graphql(owner_id)
                
                for proj_data in projects_v2:
                    if proj_data.get("title") == project_name:
                        project_v2_data = proj_data
                        break
            except Exception as e:
                console.print(f"[dim]Could not list Projects V2: {e}[/dim]")

        # If not found in V2, try Projects classic (REST API)
        if not project_v2_data:
            if github_id:
                project = self.github.get_project(github_id)
            else:
                project = self.github.get_project_by_name(project_name)

        if not project and not project_v2_data:
            console.print(f"[red]Project '{project_name}' not found on GitHub[/red]")
            if is_org:
                console.print(f"[yellow]Note: Searched in organization '{target_owner}' (Projects V2 and classic)[/yellow]")
            return False

        # Handle Projects V2 (GraphQL)
        if project_v2_data:
            console.print(f"[yellow]Note: This is a Projects V2 (beta) project. Limited sync support.[/yellow]")
            
            # Save project metadata
            project_data = {
                "name": project_v2_data.get("title", project_name),
                "body": project_v2_data.get("shortDescription", ""),
                "github_id": project_v2_data.get("number"),  # Use number as ID for V2
                "github_node_id": project_v2_data.get("id"),  # Store GraphQL node ID
                "project_v2": True,  # Mark as V2 project
            }
            yaml_handler.save_project(project_data)
            
            console.print(f"[green]Successfully synced Projects V2 from GitHub: {project_name}[/green]")
            console.print(f"[dim]Project URL: {project_v2_data.get('url')}[/dim]")
            console.print(f"[yellow]Note: Projects V2 columns and cards sync is not yet fully supported.[/yellow]")
            return True

        # Handle Projects classic (REST API)
        # Save project metadata
        project_data = {
            "name": project.name,
            "body": project.body,
            "github_id": project.id,
        }
        yaml_handler.save_project(project_data)

        # Get and save columns
        columns = self.github.get_project_columns(project)
        columns_data = []
        for idx, column in enumerate(columns, start=1):
            columns_data.append({
                "name": column.name,
                "position": idx,
                "github_id": column.id,
            })
        yaml_handler.save_columns(columns_data)

        # Get and save cards
        cards_data = []
        for column in columns:
            cards = self.github.get_column_cards(column)
            for card in cards:
                card_data = {
                    "column": column.name,
                    "note": card.note if hasattr(card, "note") and card.note else None,
                    "position": "top",  # Default position
                }
                if hasattr(card, "content_url") and card.content_url:
                    card_data["content_url"] = card.content_url
                cards_data.append(card_data)

        yaml_handler.save_cards(cards_data)

        console.print(f"[green]Successfully synced from GitHub: {project_name}[/green]")
        return True

    def _sync_columns(self, project, columns_data: List[Dict[str, Any]]) -> None:
        """Sync columns to GitHub project.

        Args:
            project: GitHub Project instance
            columns_data: List of column definitions
        """
        existing_columns = {col.name: col for col in self.github.get_project_columns(project)}

        for col_data in columns_data:
            col_name = col_data["name"]
            if col_name not in existing_columns:
                console.print(f"  [yellow]Creating column: {col_name}[/yellow]")
                self.github.create_column(project, col_name)

    def _sync_cards(self, project, cards_data: List[Dict[str, Any]]) -> None:
        """Sync cards to GitHub project.

        Args:
            project: GitHub Project instance
            cards_data: List of card definitions
        """
        columns = {col.name: col for col in self.github.get_project_columns(project)}

        for card_data in cards_data:
            column_name = card_data.get("column")
            if not column_name or column_name not in columns:
                console.print(f"  [red]Column not found: {column_name}[/red]")
                continue

            column = columns[column_name]
            note = card_data.get("note")

            if note:
                console.print(f"  [yellow]Creating card in {column_name}: {note[:50]}...[/yellow]")
                self.github.create_card(column, note=note)

