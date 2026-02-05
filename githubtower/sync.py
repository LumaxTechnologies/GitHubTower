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

    def sync_to_github(self, project_name: str, create_if_missing: bool = True, require_confirmation: bool = True) -> bool:
        """Sync local YAML files to GitHub.

        Args:
            project_name: Name of the project to sync
            create_if_missing: Create project on GitHub if it doesn't exist
            require_confirmation: If True, prompt for confirmation before modifying GitHub

        Returns:
            True if sync was successful
        """
        project_dir = self.config.get_project_dir(project_name)
        if not project_dir.exists():
            console.print(f"[red]Project directory not found: {project_dir}[/red]")
            return False

        yaml_handler = ProjectYAML(project_dir)
        
        # Try to load unified structure first
        unified_data = yaml_handler.load_unified_project()
        if unified_data and unified_data.get("project"):
            project_data = yaml_handler.get_project_from_unified(unified_data)
            columns_data = yaml_handler.get_columns_from_unified(unified_data)
            cards_data = yaml_handler.get_cards_from_unified(unified_data)
        else:
            # Fall back to separate files for backward compatibility
            project_data = yaml_handler.load_project()
            columns_data = yaml_handler.load_columns()
            cards_data = yaml_handler.load_cards()

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
            # Projects V2 - sync support for reading is implemented, but writing is limited
            project_node_id = project_data.get("github_node_id")
            if not project_node_id:
                console.print(f"[red]Project V2 node ID not found. Please sync from GitHub first.[/red]")
                return False
            
            console.print(f"[yellow]Note: This is a Projects V2 (beta) project.[/yellow]")
            console.print(f"[yellow]Writing to Projects V2 (creating fields/items) requires GraphQL mutations and is not yet fully implemented.[/yellow]")
            console.print(f"[yellow]You can sync FROM GitHub to get fields and items, but syncing TO GitHub is limited.[/yellow]")
            console.print(f"[green]Project metadata available: {project_name}[/green]")
            
            # For now, we can't create fields/items via GraphQL mutations easily
            # This would require implementing:
            # - addProjectV2FieldById mutation for fields
            # - addProjectV2ItemById mutation for items  
            # - updateProjectV2ItemFieldValue mutation for field values
            # These are complex and would need careful implementation
            
            return True

        # Get or create project (Projects classic)
        project = None
        if project_data.get("github_id"):
            project = self.github.get_project(project_data["github_id"])

        if not project:
            if create_if_missing:
                owner_info = project_data.get("owner") or self.config.github_org or "your account"
                console.print(f"\n[bold yellow]⚠ Warning: This will create a new project on GitHub[/bold yellow]")
                console.print(f"  Project name: {project_data['name']}")
                console.print(f"  Owner: {owner_info}")
                if project_data.get("body"):
                    body_preview = project_data["body"][:100] + "..." if len(project_data.get("body", "")) > 100 else project_data.get("body", "")
                    console.print(f"  Description: {body_preview}")
                
                if require_confirmation:
                    # Import click here to avoid dependency if not in CLI context
                    try:
                        import click
                        if not click.confirm("\n[bold]Do you want to create this project on GitHub?[/bold]"):
                            console.print("[yellow]Cancelled. Project not created on GitHub.[/yellow]")
                            return False
                    except ImportError:
                        # If click is not available, assume confirmation is given
                        pass
                
                console.print(f"[cyan]Creating project on GitHub...[/cyan]")
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

        # Warn if syncing to existing project
        if require_confirmation:
            existing_columns = self.github.get_project_columns(project)
            existing_cards_count = 0
            for col in existing_columns:
                existing_cards_count += len(self.github.get_column_cards(col))
            
            if existing_columns or existing_cards_count > 0:
                console.print(f"\n[yellow]⚠ Warning: Syncing to existing GitHub project[/yellow]")
                console.print(f"  Project: {project.name} (ID: {project.id})")
                console.print(f"  Existing columns: {len(existing_columns)}")
                console.print(f"  Existing cards: {existing_cards_count}")
                console.print(f"[yellow]This will add new columns and cards, but will not delete or modify existing ones.[/yellow]")
                try:
                    import click
                    if not click.confirm("\n[bold]Do you want to proceed with syncing to this GitHub project?[/bold]"):
                        console.print("[yellow]Cancelled. No changes made to GitHub.[/yellow]")
                        return False
                except ImportError:
                    pass

        # Sync columns (use columns_data loaded above)
        if columns_data:
            self._sync_columns(project, columns_data, require_confirmation)

        # Sync cards (use cards_data loaded above)
        if cards_data:
            self._sync_cards(project, cards_data, require_confirmation)

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
            project_node_id = project_v2_data.get("id")
            
            # Prepare project metadata
            project_data = {
                "name": project_v2_data.get("title", project_name),
                "body": project_v2_data.get("shortDescription", ""),
                "github_id": project_v2_data.get("number"),  # Use number as ID for V2
                "github_node_id": project_node_id,  # Store GraphQL node ID
                "project_v2": True,  # Mark as V2 project
            }
            
            # Fetch items (fields will be extracted from items)
            try:
                console.print(f"[cyan]Fetching Projects V2 items...[/cyan]")
                items = self.github.get_project_v2_items(project_node_id)
                
                # Extract Status field options from items' fieldValues
                # This works around the GraphQL union type issue with fields query
                status_field_id = None
                status_options = {}  # Map of option name -> option data
                columns_data = []
                seen_status_values = set()
                
                # First pass: collect all Status field values from items
                for item in items:
                    field_values = item.get("fieldValues", {}).get("nodes", [])
                    for field_value in field_values:
                        field = field_value.get("field", {})
                        if field.get("name") == "Status":
                            if not status_field_id:
                                # Try to get field ID from the field object
                                status_field_id = field.get("id", "")
                            status_value = field_value.get("name")
                            if status_value and status_value not in seen_status_values:
                                seen_status_values.add(status_value)
                                # Create a column entry for this status value
                                columns_data.append({
                                    "name": status_value,
                                    "position": len(columns_data) + 1,
                                    "github_id": field_value.get("id", ""),  # Use field value ID
                                    "field_id": status_field_id,
                                })
                
                # Sort columns by position
                columns_data.sort(key=lambda x: x["position"])
                
                # Map items to cards
                cards_data = []
                column_names = {col["name"] for col in columns_data}
                
                for item in items:
                    # Extract note/content
                    content = item.get("content")
                    note = None
                    if content:
                        if isinstance(content, dict):
                            note = content.get("title") or content.get("body", "")
                        else:
                            note = str(content)
                    
                    # If no content, use item ID as note
                    if not note:
                        note = f"Item {item.get('id', '')[:8]}"
                    
                    # Find the Status field value (which column this item is in)
                    column_name = "Backlog"  # Default
                    field_values = item.get("fieldValues", {}).get("nodes", [])
                    for field_value in field_values:
                        field = field_value.get("field", {})
                        if field.get("name") == "Status":
                            status_value = field_value.get("name")
                            if status_value and status_value in column_names:
                                column_name = status_value
                            elif status_value:
                                # Status value exists but not in our column map, add it
                                column_name = status_value
                                columns_data.append({
                                    "name": status_value,
                                    "position": len(columns_data) + 1,
                                    "github_id": field_value.get("id", ""),
                                    "field_id": status_field_id,
                                })
                                column_names.add(status_value)
                            break
                    
                    cards_data.append({
                        "column": column_name,
                        "note": note,
                        "position": "top",
                        "item_id": item.get("id"),
                        "item_type": item.get("type"),
                    })
                
                # Re-sort columns in case we added new ones
                columns_data.sort(key=lambda x: x["position"])
                
                # Save unified YAML file
                yaml_handler.save_unified_project(project_data, columns_data, cards_data)
                
                console.print(f"[green]Successfully synced Projects V2 from GitHub: {project_name}[/green]")
                console.print(f"[dim]Project URL: {project_v2_data.get('url')}[/dim]")
                console.print(f"[green]Synced {len(columns_data)} columns and {len(cards_data)} cards[/green]")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not sync fields and items: {e}[/yellow]")
                console.print(f"[yellow]Project metadata synced, but columns and cards sync failed.[/yellow]")
                # Save project metadata only
                yaml_handler.save_unified_project(project_data, [], [])
                console.print(f"[green]Successfully synced Projects V2 from GitHub: {project_name}[/green]")
                console.print(f"[dim]Project URL: {project_v2_data.get('url')}[/dim]")
            
            return True

        # Handle Projects classic (REST API)
        # Prepare project metadata
        project_data = {
            "name": project.name,
            "body": project.body,
            "github_id": project.id,
        }

        # Get columns
        columns = self.github.get_project_columns(project)
        columns_data = []
        for idx, column in enumerate(columns, start=1):
            columns_data.append({
                "name": column.name,
                "position": idx,
                "github_id": column.id,
            })

        # Get cards
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

        # Save unified YAML file
        yaml_handler.save_unified_project(project_data, columns_data, cards_data)

        console.print(f"[green]Successfully synced from GitHub: {project_name}[/green]")
        return True

    def _sync_columns(self, project, columns_data: List[Dict[str, Any]], require_confirmation: bool = True) -> None:
        """Sync columns to GitHub project.

        Args:
            project: GitHub Project instance
            columns_data: List of column definitions
            require_confirmation: If True, prompt for confirmation before creating columns
        """
        existing_columns = {col.name: col for col in self.github.get_project_columns(project)}
        
        new_columns = [col_data["name"] for col_data in columns_data if col_data["name"] not in existing_columns]
        
        if new_columns and require_confirmation:
            console.print(f"\n[yellow]⚠ Warning: This will create {len(new_columns)} new column(s) on GitHub:[/yellow]")
            for col_name in new_columns:
                console.print(f"  - {col_name}")
            try:
                import click
                if not click.confirm("\n[bold]Do you want to create these columns on GitHub?[/bold]"):
                    console.print("[yellow]Skipping column creation.[/yellow]")
                    return
            except ImportError:
                pass

        for col_data in columns_data:
            col_name = col_data["name"]
            if col_name not in existing_columns:
                console.print(f"  [yellow]Creating column: {col_name}[/yellow]")
                self.github.create_column(project, col_name)

    def _sync_cards(self, project, cards_data: List[Dict[str, Any]], require_confirmation: bool = True) -> None:
        """Sync cards to GitHub project.

        Args:
            project: GitHub Project instance
            cards_data: List of card definitions
            require_confirmation: If True, prompt for confirmation before creating cards
        """
        columns = {col.name: col for col in self.github.get_project_columns(project)}
        
        # Count cards that will be created
        cards_to_create = [card_data for card_data in cards_data 
                          if card_data.get("note") and card_data.get("column") in columns]
        
        if cards_to_create and require_confirmation:
            console.print(f"\n[yellow]⚠ Warning: This will create {len(cards_to_create)} new card(s) on GitHub[/yellow]")
            console.print("[yellow]Note: This may create duplicate cards if cards with the same content already exist.[/yellow]")
            if len(cards_to_create) <= 10:
                console.print("[yellow]Cards to be created:[/yellow]")
                for card_data in cards_to_create:
                    note_preview = (card_data.get("note", "")[:60] + "...") if len(card_data.get("note", "")) > 60 else card_data.get("note", "")
                    console.print(f"  - {note_preview} (in column: {card_data.get('column')})")
            else:
                console.print(f"[yellow]First 5 cards:[/yellow]")
                for card_data in cards_to_create[:5]:
                    note_preview = (card_data.get("note", "")[:60] + "...") if len(card_data.get("note", "")) > 60 else card_data.get("note", "")
                    console.print(f"  - {note_preview} (in column: {card_data.get('column')})")
                console.print(f"[yellow]  ... and {len(cards_to_create) - 5} more cards[/yellow]")
            
            try:
                import click
                if not click.confirm("\n[bold]Do you want to create these cards on GitHub?[/bold]"):
                    console.print("[yellow]Skipping card creation.[/yellow]")
                    return
            except ImportError:
                pass

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

