"""Project templates for GitHub Projects."""

from typing import Dict, List, Any
from rich.console import Console
from rich.prompt import Prompt

console = Console()


# Predefined project templates
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "kanban": {
        "name": "Kanban Board",
        "description": "Classic Kanban board with To Do, In Progress, and Done columns",
        "columns": [
            {"name": "To Do", "position": 1},
            {"name": "In Progress", "position": 2},
            {"name": "Done", "position": 3},
        ],
        "cards": [],
    },
    "scrum": {
        "name": "Scrum Board",
        "description": "Scrum-style board with Backlog, Sprint Backlog, In Progress, Review, and Done",
        "columns": [
            {"name": "Backlog", "position": 1},
            {"name": "Sprint Backlog", "position": 2},
            {"name": "In Progress", "position": 3},
            {"name": "Review", "position": 4},
            {"name": "Done", "position": 5},
        ],
        "cards": [],
    },
    "bug-tracking": {
        "name": "Bug Tracking",
        "description": "Board for tracking bugs with Triage, In Progress, Testing, and Resolved",
        "columns": [
            {"name": "Triage", "position": 1},
            {"name": "In Progress", "position": 2},
            {"name": "Testing", "position": 3},
            {"name": "Resolved", "position": 4},
        ],
        "cards": [],
    },
    "feature-request": {
        "name": "Feature Requests",
        "description": "Board for managing feature requests with Ideas, Planned, In Development, and Released",
        "columns": [
            {"name": "Ideas", "position": 1},
            {"name": "Planned", "position": 2},
            {"name": "In Development", "position": 3},
            {"name": "Released", "position": 4},
        ],
        "cards": [],
    },
    "simple": {
        "name": "Simple Board",
        "description": "Simple 3-column board: To Do, Doing, Done",
        "columns": [
            {"name": "To Do", "position": 1},
            {"name": "Doing", "position": 2},
            {"name": "Done", "position": 3},
        ],
        "cards": [],
    },
    "gtd": {
        "name": "Getting Things Done (GTD)",
        "description": "GTD methodology with Inbox, Next Actions, Waiting, and Completed",
        "columns": [
            {"name": "Inbox", "position": 1},
            {"name": "Next Actions", "position": 2},
            {"name": "Waiting", "position": 3},
            {"name": "Completed", "position": 4},
        ],
        "cards": [],
    },
    "minimal": {
        "name": "Minimal",
        "description": "Minimal 2-column board: To Do and Done",
        "columns": [
            {"name": "To Do", "position": 1},
            {"name": "Done", "position": 2},
        ],
        "cards": [],
    },
    "custom": {
        "name": "Custom",
        "description": "Start with empty project and define your own structure",
        "columns": [],
        "cards": [],
    },
}


def list_templates() -> List[str]:
    """Get list of available template keys.

    Returns:
        List of template keys
    """
    return list(TEMPLATES.keys())


def get_template(template_key: str) -> Dict[str, Any]:
    """Get template by key.

    Args:
        template_key: Template identifier

    Returns:
        Template dictionary

    Raises:
        ValueError: If template key is invalid
    """
    if template_key not in TEMPLATES:
        raise ValueError(f"Unknown template: {template_key}")
    return TEMPLATES[template_key]


def select_template() -> str:
    """Interactive template selection with numbered menu.

    Returns:
        Selected template key

    Raises:
        KeyboardInterrupt: If user cancels
    """
    console.print("\n[bold cyan]Select a project template:[/bold cyan]\n")

    templates = list_templates()
    template_items = []

    for idx, key in enumerate(templates, start=1):
        template = TEMPLATES[key]
        template_items.append((idx, key, template))

    # Display templates in a nice format
    for idx, key, template in template_items:
        console.print(f"  [cyan]{idx}.[/cyan] [bold]{template['name']}[/bold]")
        console.print(f"     [dim]{template['description']}[/dim]")
        if template["columns"]:
            columns_str = " → ".join([col["name"] for col in template["columns"]])
            console.print(f"     [dim]Columns: {columns_str}[/dim]")
        console.print()

    # Get user selection
    while True:
        try:
            choice = Prompt.ask(
                f"[cyan]Select template[/cyan] [dim](1-{len(templates)})[/dim]",
                default="1",
            )
            choice_num = int(choice)
            if 1 <= choice_num <= len(templates):
                selected_key = template_items[choice_num - 1][1]
                selected_template = TEMPLATES[selected_key]
                console.print(
                    f"\n[green]✓ Selected: {selected_template['name']}[/green]\n"
                )
                return selected_key
            else:
                console.print(
                    f"[red]Please enter a number between 1 and {len(templates)}[/red]"
                )
        except ValueError:
            console.print("[red]Please enter a valid number[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled[/yellow]")
            raise


def apply_template(
    template_key: str, project_name: str, project_body: str = None
) -> Dict[str, Any]:
    """Apply template to create project structure.

    Args:
        template_key: Template identifier
        project_name: Name for the project
        project_body: Optional project description

    Returns:
        Dictionary with project, columns, and cards data
    """
    template = get_template(template_key)

    project_data = {
        "name": project_name,
        "body": project_body or f"Project: {project_name}",
        "owner": None,
        "github_id": None,
    }

    columns_data = template["columns"].copy()
    cards_data = template["cards"].copy()

    return {
        "project": project_data,
        "columns": columns_data,
        "cards": cards_data,
    }

