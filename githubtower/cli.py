"""Command-line interface for GitHubTower."""

import sys
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich import box

from .config import Config
from .github_api import GitHubProjectManager
from .yaml_handler import ProjectYAML
from .sync import ProjectSyncer
from .templates import select_template, apply_template, list_templates, TEMPLATES
from github.GithubException import GithubException

console = Console()


@click.group()
@click.option(
    "--config-dir",
    type=click.Path(path_type=Path),
    help="Custom configuration directory (default: ~/.githubtower)",
)
@click.pass_context
def cli(ctx, config_dir):
    """GitHubTower - Manage GitHub Projects through Python CLI."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config(config_dir)


@cli.command()
@click.argument("project_name")
@click.option("--name", help="Project name on GitHub (defaults to project_name)")
@click.option("--body", help="Project description")
@click.option("--owner", help="GitHub owner (org or user)")
@click.option(
    "--template",
    is_flag=True,
    help="Select a project template from available templates",
)
@click.option(
    "--template-name",
    type=click.Choice(list_templates(), case_sensitive=False),
    help="Use a specific template by name (kanban, scrum, bug-tracking, etc.)",
)
@click.option(
    "--folder",
    type=click.Path(path_type=Path),
    help="Folder path (relative to current working directory) to store the project. Creates folder if not exists. Defaults to ~/.githubtower/projects",
)
@click.pass_context
def create(ctx, project_name, name, body, owner, template, template_name, folder):
    """Create a new project locally and optionally on GitHub."""
    base_config = ctx.obj["config"]
    
    # If --folder is provided, create a custom config with that folder as projects_dir
    if folder:
        folder_path = Path.cwd() / folder
        folder_path = folder_path.resolve()
        folder_path.mkdir(parents=True, exist_ok=True)
        config = Config(config_dir=base_config.config_dir, projects_dir=folder_path)
        console.print(f"[dim]Using custom folder: {folder_path}[/dim]")
    else:
        config = base_config
    
    project_dir = config.ensure_project_dir(project_name)

    yaml_handler = ProjectYAML(project_dir)

    # Check if project already exists
    if yaml_handler.project_file.exists():
        if not click.confirm(f"Project '{project_name}' already exists. Overwrite?"):
            return

    # Handle template selection
    selected_template = None
    if template or template_name:
        if template_name:
            # Use specified template
            selected_template = template_name.lower()
        else:
            # Interactive template selection
            try:
                selected_template = select_template()
            except KeyboardInterrupt:
                console.print("\n[yellow]Cancelled project creation[/yellow]")
                return

        # Apply template
        template_data = apply_template(
            selected_template,
            name or project_name,
            body,
        )
        project_data = template_data["project"]
        columns_data = template_data["columns"]
        cards_data = template_data["cards"]

        # Save project data
        if owner:
            project_data["owner"] = owner
        yaml_handler.save_project(project_data)

        # Save columns and cards if template provided them
        if columns_data:
            yaml_handler.save_columns(columns_data)
        if cards_data:
            yaml_handler.save_cards(cards_data)

        console.print(f"[green]Created project with template '{selected_template}' in: {project_dir}[/green]")
    else:
        # Create basic template files (backward compatibility)
        yaml_handler.create_template()
        console.print(f"[green]Created template files in: {project_dir}[/green]")

        # Update project.yaml with provided values
        project_data = yaml_handler.load_project()
        if project_data:
            if name:
                project_data["name"] = name
            else:
                project_data["name"] = project_name

            if body:
                project_data["body"] = body

            if owner:
                project_data["owner"] = owner

            yaml_handler.save_project(project_data)

    # Create on GitHub if requested
    if click.confirm("Create project on GitHub now?"):
        target_owner = None  # Initialize for error handling
        try:
            github_manager = GitHubProjectManager(config)
            
            # Determine target owner
            target_owner = project_data.get("owner") or config.github_org
            owner_info = target_owner or "your account"
            
            # Show warning about what will be created
            console.print(f"\n[bold yellow]⚠ Warning: This will create a new project on GitHub[/bold yellow]")
            console.print(f"  Project name: {project_data['name']}")
            console.print(f"  Owner: {owner_info}")
            if project_data.get("body"):
                body_preview = project_data["body"][:100] + "..." if len(project_data.get("body", "")) > 100 else project_data.get("body", "")
                console.print(f"  Description: {body_preview}")
            
            if not click.confirm("\n[bold]Do you want to proceed with creating this project on GitHub?[/bold]"):
                console.print("[yellow]Cancelled. Project not created on GitHub.[/yellow]")
                return
            
            console.print(f"[cyan]Creating project '{project_data['name']}' on GitHub ({owner_info})...[/cyan]")
            
            # If organization is specified, verify it exists and is accessible
            is_org = False
            if target_owner:
                try:
                    # Try to get the organization/user to verify access
                    test_org = github_manager.github.get_organization(target_owner)
                    console.print(f"[dim]Verified access to organization: {target_owner}[/dim]")
                    is_org = True
                except Exception:
                    # If org fails, try as user
                    try:
                        test_user = github_manager.github.get_user(target_owner)
                        console.print(f"[dim]Using user account: {target_owner}[/dim]")
                    except Exception as e:
                        console.print(f"[yellow]Warning: Could not verify access to '{target_owner}': {e}[/yellow]")
                        if not click.confirm("Continue anyway?"):
                            return
            
            if is_org:
                console.print(f"[dim]Using GraphQL API for organization project...[/dim]")
            
            try:
                # Pass the owner explicitly - use the one we verified earlier
                project = github_manager.create_project(
                    name=project_data["name"],
                    body=project_data.get("body"),
                    owner=target_owner,  # Use the verified target_owner, not from project_data
                )
            except GithubException as ge:
                # Re-raise to be caught by outer exception handler
                raise ge
            if project:
                # REST API project (user projects)
                project_data["github_id"] = project.id
                yaml_handler.save_project(project_data)
                console.print(f"[green]✓ Created project on GitHub: {project.name} (ID: {project.id})[/green]")
            else:
                # GraphQL project (organization projects) - project was created but we need to fetch it
                # For now, we'll mark it as created and the user can sync later
                console.print("[green]✓ Project created on GitHub via GraphQL API[/green]")
                console.print("[yellow]Note: Organization projects use GraphQL API. You may need to sync to get the project ID.[/yellow]")
                # Try to get the project by name to get its ID
                try:
                    fetched_project = github_manager.get_project_by_name(
                        project_data["name"],
                        owner=project_data.get("owner") or target_owner,
                    )
                    if fetched_project:
                        project_data["github_id"] = fetched_project.id
                        yaml_handler.save_project(project_data)
                        console.print(f"[green]Project ID: {fetched_project.id}[/green]")
                except Exception:
                    console.print("[dim]Project created but ID not available yet. Run 'sync' command later to update.[/dim]")
        except GithubException as e:
            error_msg = str(e)
            status = getattr(e, "status", None)
            
            # Check if this is a GraphQL error - preserve and display it clearly
            # Also check for "GraphQL:" prefix that we add
            if ("GraphQL" in error_msg or "graphql" in error_msg.lower() or 
                "createProject" in error_msg or "createProjectV2" in error_msg or
                "project scope" in error_msg.lower() or "via GraphQL" in error_msg):
                console.print("[red]Error: GraphQL API error[/red]")
                console.print(f"[yellow]{error_msg}[/yellow]")
                if status == 403 or "FORBIDDEN" in error_msg or "permission" in error_msg.lower():
                    console.print("\n[yellow]This is a permissions issue. Your token needs:[/yellow]")
                    console.print("  • 'project' scope - Required for creating organization projects via GraphQL")
                    console.print("  • 'read:org' scope - Required for reading organization data")
                    console.print("\n[cyan]To fix:[/cyan]")
                    console.print("  1. Go to GitHub Settings → Developer settings → Personal access tokens")
                    console.print("  2. Edit your token and add the 'project' scope")
                    console.print("  3. Update your token in ~/.githubtower/.env")
                elif status == 404:
                    console.print("\n[yellow]Possible causes:[/yellow]")
                    console.print("  • Organization not found or you don't have access")
                    console.print("  • Token missing 'read:org' scope to query organization via GraphQL")
                    console.print("  • Token missing 'project' scope to create projects via GraphQL")
                return
            
            if status == 404 or "404" in error_msg or "Not Found" in error_msg:
                console.print("[red]Error: Project creation failed (404 Not Found)[/red]")
                console.print("[yellow]Possible causes:[/yellow]")
                if target_owner:
                    console.print(f"  • Organization/user '{target_owner}' not found or you don't have access")
                console.print("  • Token missing required permissions:")
                console.print("    - 'repo' scope for user projects")
                console.print("    - 'write:org' or 'project' scope for organization projects")
                console.print("  • GitHub Projects may not be enabled for this account/org")
                console.print(f"\n[dim]Full error: {error_msg}[/dim]")
                if is_org:
                    console.print("\n[yellow]Note:[/yellow] Organization projects use GraphQL API (Projects beta).")
                    console.print("Make sure your token has the 'project' scope enabled.")
            elif status == 403 or "403" in error_msg or "Permission" in error_msg:
                console.print("[red]Error: Permission denied[/red]")
                console.print("[yellow]Your token needs:[/yellow]")
                console.print("  • 'repo' scope for user projects")
                console.print("  • 'write:org' scope for organization projects")
                console.print(f"\n[dim]Full error: {error_msg}[/dim]")
            else:
                console.print(f"[red]Error creating project on GitHub: {error_msg}[/red]")
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")


@cli.command()
@click.option(
    "--folder",
    type=click.Path(path_type=Path),
    help="Folder path (relative to current working directory) to list projects from. Defaults to ~/.githubtower/projects",
)
@click.pass_context
def list_projects(ctx, folder):
    """List all local projects."""
    base_config = ctx.obj["config"]
    
    # If --folder is provided, create a custom config with that folder as projects_dir
    if folder:
        folder_path = Path.cwd() / folder
        folder_path = folder_path.resolve()
        config = Config(config_dir=base_config.config_dir, projects_dir=folder_path)
        console.print(f"[dim]Listing projects from: {folder_path}[/dim]")
    else:
        config = base_config
    
    projects_dir = config.projects_dir

    if not projects_dir.exists():
        console.print(f"[yellow]Projects directory does not exist: {projects_dir}[/yellow]")
        console.print("[cyan]Create a project first with: githubtower create <project-name> --template[/cyan]")
        return

    project_dirs = [d for d in projects_dir.iterdir() if d.is_dir()]
    if not project_dirs:
        console.print("[yellow]No projects found locally[/yellow]")
        console.print(f"[cyan]Projects directory: {projects_dir}[/cyan]")
        console.print("[cyan]Create a project first with: githubtower create <project-name> --template[/cyan]")
        return

    table = Table(title="Local Projects", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Directory", style="magenta")
    table.add_column("GitHub ID", style="green")
    table.add_column("Status", style="yellow")

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue

        yaml_handler = ProjectYAML(project_dir)
        project_data = yaml_handler.load_project()

        if project_data:
            github_id = project_data.get("github_id", "Not synced")
            status = "Synced" if github_id != "Not synced" else "Local only"
            table.add_row(
                project_data.get("name", project_dir.name),
                str(project_dir),
                str(github_id),
                status,
            )

    console.print(table)


@cli.command()
@click.argument("project_name")
@click.option("--github-id", type=int, help="GitHub project ID (for from-github sync)")
@click.option(
    "--direction",
    type=click.Choice(["to-github", "from-github", "auto"], case_sensitive=False),
    default="auto",
    help="Sync direction: to-github (local → GitHub), from-github (GitHub → local), or auto (detect automatically)",
)
@click.option(
    "--folder",
    type=click.Path(path_type=Path),
    help="Folder path (relative to current working directory) to sync GitHub projects content. Creates folder if not exists. Defaults to ~/.githubtower/projects",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompts and proceed with all GitHub modifications",
)
@click.pass_context
def sync(ctx, project_name, github_id, direction, folder, yes):
    """Sync project between local YAML and GitHub.
    
    If direction is 'auto' (default), the command will:
    - Use 'from-github' if the project exists on GitHub but not locally
    - Use 'to-github' if the project exists locally
    - Use 'from-github' if neither exists (will fail if project not found on GitHub)
    """
    base_config = ctx.obj["config"]
    
    # If --folder is provided, create a custom config with that folder as projects_dir
    if folder:
        # Resolve folder path relative to current working directory
        folder_path = Path.cwd() / folder
        folder_path = folder_path.resolve()
        # Create folder if it doesn't exist
        folder_path.mkdir(parents=True, exist_ok=True)
        # Create a new config instance with custom projects_dir
        config = Config(config_dir=base_config.config_dir, projects_dir=folder_path)
        console.print(f"[dim]Using custom folder: {folder_path}[/dim]")
    else:
        config = base_config

    try:
        github_manager = GitHubProjectManager(config)
        syncer = ProjectSyncer(config, github_manager)

        # Auto-detect direction if not specified
        if direction == "auto":
            project_dir = config.get_project_dir(project_name)
            local_exists = project_dir.exists()
            
            # Check if project exists on GitHub (both Projects classic and V2)
            github_exists = False
            try:
                # Try Projects classic first
                project = github_manager.get_project_by_name(project_name)
                if project:
                    github_exists = True
                else:
                    # Try Projects V2 via GraphQL for organizations
                    target_owner = config.github_org
                    if target_owner:
                        try:
                            org = github_manager.github.get_organization(target_owner)
                            owner_id = github_manager._get_owner_node_id(target_owner)
                            projects_v2 = github_manager._list_projects_via_graphql(owner_id)
                            for proj in projects_v2:
                                if proj.get("title") == project_name:
                                    github_exists = True
                                    break
                        except Exception:
                            pass
            except Exception:
                pass
            
            if local_exists and github_exists:
                # Both exist, default to to-github
                direction = "to-github"
                console.print(f"[dim]Both local and GitHub projects exist. Syncing local → GitHub...[/dim]")
            elif github_exists and not local_exists:
                # Exists on GitHub but not locally, use from-github
                direction = "from-github"
                console.print(f"[dim]Project exists on GitHub but not locally. Syncing GitHub → local...[/dim]")
            elif local_exists and not github_exists:
                # Exists locally but not on GitHub, use to-github
                direction = "to-github"
                console.print(f"[dim]Project exists locally but not on GitHub. Syncing local → GitHub...[/dim]")
            else:
                # Neither exists, try from-github (will fail if not found)
                direction = "from-github"
                console.print(f"[dim]Project not found locally. Attempting to sync from GitHub...[/dim]")

        if direction == "to-github":
            # Check if project directory exists before syncing
            project_dir = config.get_project_dir(project_name)
            if not project_dir.exists():
                console.print(f"[red]Project directory not found: {project_dir}[/red]")
                console.print(f"[cyan]Create the project first with: githubtower create {project_name}[/cyan]")
                console.print(f"[cyan]Or sync from GitHub with: githubtower sync {project_name} --direction from-github[/cyan]")
                sys.exit(1)
            
            success = syncer.sync_to_github(project_name, require_confirmation=not yes)
            if not success:
                sys.exit(1)
        else:
            # For from-github, the directory will be created if it doesn't exist
            success = syncer.sync_from_github(project_name, github_id)
            if not success:
                sys.exit(1)

    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("project_name")
@click.option(
    "--folder",
    type=click.Path(path_type=Path),
    help="Folder path (relative to current working directory) to look for the project. Defaults to ~/.githubtower/projects",
)
@click.pass_context
def show(ctx, project_name, folder):
    """Show project details."""
    base_config = ctx.obj["config"]
    
    # If --folder is provided, create a custom config with that folder as projects_dir
    if folder:
        folder_path = Path.cwd() / folder
        folder_path = folder_path.resolve()
        config = Config(config_dir=base_config.config_dir, projects_dir=folder_path)
        console.print(f"[dim]Looking for project in: {folder_path}[/dim]")
    else:
        config = base_config
    
    project_dir = config.get_project_dir(project_name)

    if not project_dir.exists():
        console.print(f"[red]Project not found: {project_name}[/red]")
        return

    yaml_handler = ProjectYAML(project_dir)
    project_data = yaml_handler.load_project()

    if project_data:
        console.print(f"\n[bold cyan]Project: {project_name}[/bold cyan]")
        console.print(f"  Name: {project_data.get('name')}")
        console.print(f"  Description: {project_data.get('body', 'N/A')}")
        console.print(f"  GitHub ID: {project_data.get('github_id', 'Not synced')}")
        console.print(f"  Directory: {project_dir}\n")

        # Show columns
        columns = yaml_handler.load_columns()
        if columns:
            console.print("[bold]Columns:[/bold]")
            for col in columns:
                console.print(f"  - {col.get('name')} (position: {col.get('position')})")

        # Show cards
        cards = yaml_handler.load_cards()
        if cards:
            console.print(f"\n[bold]Cards: {len(cards)}[/bold]")
            for card in cards[:10]:  # Show first 10
                note = card.get("note", "N/A")
                console.print(f"  - {note[:60]}... ({card.get('column')})")
            if len(cards) > 10:
                console.print(f"  ... and {len(cards) - 10} more")


@cli.command()
@click.argument("project_name")
@click.confirmation_option(prompt="Are you sure you want to delete this project?")
@click.option("--github", is_flag=True, help="Also delete from GitHub")
@click.option(
    "--folder",
    type=click.Path(path_type=Path),
    help="Folder path (relative to current working directory) to delete the project from. Defaults to ~/.githubtower/projects",
)
@click.pass_context
def delete(ctx, project_name, github, folder):
    """Delete a project locally and optionally on GitHub."""
    base_config = ctx.obj["config"]
    
    # If --folder is provided, create a custom config with that folder as projects_dir
    if folder:
        folder_path = Path.cwd() / folder
        folder_path = folder_path.resolve()
        config = Config(config_dir=base_config.config_dir, projects_dir=folder_path)
        console.print(f"[dim]Looking for project in: {folder_path}[/dim]")
    else:
        config = base_config
    
    project_dir = config.get_project_dir(project_name)

    if not project_dir.exists():
        console.print(f"[red]Project not found: {project_name}[/red]")
        return

    # Delete from GitHub if requested
    if github:
        console.print("\n[bold yellow]⚠ Warning: GitHub Projects deletion[/bold yellow]")
        console.print("[yellow]GitHub Projects cannot be deleted via the REST API.[/yellow]")
        console.print("[yellow]The --github flag is currently not supported for deletion.[/yellow]")
        console.print("[yellow]Please delete the project manually on GitHub.com if needed.[/yellow]")
        
        yaml_handler = ProjectYAML(project_dir)
        project_data = yaml_handler.load_project()
        
        if project_data and project_data.get("github_id"):
            try:
                github_manager = GitHubProjectManager(config)
                project = github_manager.get_project(project_data["github_id"])
                if project:
                    console.print(f"\n[yellow]Project on GitHub:[/yellow]")
                    console.print(f"  Name: {project.name}")
                    console.print(f"  ID: {project.id}")
                    console.print(f"  URL: {project.url if hasattr(project, 'url') else 'N/A'}")
            except Exception as e:
                console.print(f"[dim]Could not fetch project details: {e}[/dim]")

    # Delete local files
    import shutil
    shutil.rmtree(project_dir)
    console.print(f"[green]Deleted local project: {project_name}[/green]")


@cli.command()
@click.option(
    "--folder",
    type=click.Path(path_type=Path),
    help="Folder path (relative to current working directory). Note: This option is ignored for list-github as it lists GitHub projects, not local ones.",
)
@click.pass_context
def list_github(ctx, folder):
    """List all projects on GitHub."""
    if folder:
        console.print("[dim]Note: --folder option is ignored for list-github (lists GitHub projects, not local ones)[/dim]")
    config = ctx.obj["config"]

    try:
        github_manager = GitHubProjectManager(config)
        
        # Determine if we're listing organization projects
        target_owner = config.github_org
        is_org = False
        
        if target_owner:
            try:
                org = github_manager.github.get_organization(target_owner)
                is_org = True
            except Exception:
                pass

        if is_org:
            # List Projects V2 via GraphQL
            try:
                owner_id = github_manager._get_owner_node_id(target_owner)
                projects_v2 = github_manager._list_projects_via_graphql(owner_id)
                
                if not projects_v2:
                    console.print(f"[yellow]No projects found on GitHub for {target_owner}[/yellow]")
                    return

                table = Table(title=f"GitHub Projects ({target_owner})", box=box.ROUNDED)
                table.add_column("Number", style="cyan")
                table.add_column("Title", style="green")
                table.add_column("Description", style="yellow")
                table.add_column("Status", style="magenta")
                table.add_column("URL", style="blue")

                for project in projects_v2:
                    status = "Closed" if project.get("closed") else "Open"
                    description = project.get("shortDescription") or ""
                    if len(description) > 50:
                        description = description[:50] + "..."
                    
                    table.add_row(
                        str(project.get("number", "")),
                        project.get("title", ""),
                        description,
                        status,
                        project.get("url", ""),
                    )

                console.print(table)
                return
            except Exception as e:
                console.print(f"[yellow]Could not list Projects V2 via GraphQL: {e}[/yellow]")
                console.print("[dim]Falling back to REST API (Projects classic)...[/dim]")

        # Fall back to REST API (Projects classic)
        projects = github_manager.list_projects()

        if not projects:
            console.print("[yellow]No projects found on GitHub[/yellow]")
            return

        table = Table(title="GitHub Projects (Classic)", box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Body", style="yellow")
        table.add_column("State", style="magenta")

        for project in projects:
            table.add_row(
                str(project.id),
                project.name,
                project.body[:50] + "..." if project.body and len(project.body) > 50 else project.body or "",
                project.state,
            )

        console.print(table)

    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
def list_templates_cmd():
    """List all available project templates."""
    console.print("\n[bold cyan]Available Project Templates:[/bold cyan]\n")

    templates = list_templates()
    for idx, key in enumerate(templates, start=1):
        template = TEMPLATES[key]
        console.print(f"  [cyan]{idx}.[/cyan] [bold]{template['name']}[/bold]")
        console.print(f"     [dim]{template['description']}[/dim]")
        if template["columns"]:
            columns_str = " → ".join([col["name"] for col in template["columns"]])
            console.print(f"     [dim]Columns: {columns_str}[/dim]")
        console.print(f"     [dim]Key: {key}[/dim]\n")


@cli.command()
@click.pass_context
def check_token(ctx):
    """Check GitHub token permissions and access."""
    config = ctx.obj["config"]

    console.print("\n[bold cyan]Checking GitHub Token Permissions...[/bold cyan]\n")

    if not config.github_token:
        console.print("[red]✗ No GitHub token found[/red]")
        console.print("[yellow]Set GITHUB_TOKEN or GH_TOKEN environment variable[/yellow]")
        return

    console.print("[green]✓ Token found[/green]\n")

    try:
        github_manager = GitHubProjectManager(config)
        results = github_manager.check_token_permissions()

        # REST API check
        console.print("[bold]REST API:[/bold]")
        if results["rest_api"]["accessible"]:
            console.print(f"  [green]✓ Accessible[/green]")
            if results["rest_api"]["user"]:
                console.print(f"  [dim]Authenticated as: {results['rest_api']['user']}[/dim]")
        else:
            console.print("  [red]✗ Not accessible[/red]")
            if results["rest_api"]["errors"]:
                for error in results["rest_api"]["errors"]:
                    console.print(f"  [red]  Error: {error}[/red]")

        # GraphQL API check
        console.print("\n[bold]GraphQL API:[/bold]")
        if results["graphql_api"]["accessible"]:
            console.print("  [green]✓ Accessible[/green]")
            if results["graphql_api"].get("user"):
                console.print(f"  [dim]Authenticated as: {results['graphql_api']['user']}[/dim]")
        else:
            console.print("  [red]✗ Not accessible[/red]")
            if results["graphql_api"]["errors"]:
                for error in results["graphql_api"]["errors"]:
                    console.print(f"  [red]  Error: {error}[/red]")
            console.print("  [yellow]Note: GraphQL API requires 'read:org' scope at minimum[/yellow]")

        # Organization access check
        if results["organization_access"]:
            console.print("\n[bold]Organization Access:[/bold]")
            for org_name, org_results in results["organization_access"].items():
                console.print(f"\n  [bold]{org_name}:[/bold]")
                
                # REST API
                if org_results["rest_api"]["accessible"]:
                    console.print(f"    REST API: [green]✓ Accessible[/green]")
                else:
                    console.print(f"    REST API: [red]✗ Not accessible[/red]")
                    for error in org_results["rest_api"]["errors"]:
                        console.print(f"      [red]Error: {error}[/red]")
                
                # GraphQL API
                if org_results["graphql_api"]["accessible"]:
                    console.print(f"    GraphQL API: [green]✓ Accessible[/green]")
                    if org_results["graphql_api"]["node_id"]:
                        console.print(f"      [dim]Node ID: {org_results['graphql_api']['node_id']}[/dim]")
                else:
                    console.print(f"    GraphQL API: [red]✗ Not accessible[/red]")
                    for error in org_results["graphql_api"]["errors"]:
                        console.print(f"      [red]Error: {error}[/red]")
                    console.print("      [yellow]Required scopes: 'read:org' (to read), 'project' (to create projects)[/yellow]")

        # Summary and recommendations
        console.print("\n[bold]Summary:[/bold]")
        can_create_user_projects = results["rest_api"]["accessible"]
        can_create_org_projects = (
            results["graphql_api"]["accessible"] and
            results.get("organization_access", {}).get(config.github_org or "", {}).get("graphql_api", {}).get("accessible", False)
        )

        if can_create_user_projects:
            console.print("  [green]✓ Can create user projects (REST API)[/green]")
        else:
            console.print("  [red]✗ Cannot create user projects[/red]")
            console.print("    [yellow]Required scope: 'repo'[/yellow]")

        if config.github_org:
            if can_create_org_projects:
                console.print(f"  [green]✓ Can create organization projects for '{config.github_org}' (GraphQL API)[/green]")
            else:
                console.print(f"  [red]✗ Cannot create organization projects for '{config.github_org}'[/red]")
                console.print("    [yellow]Required scopes: 'read:org' and 'project'[/yellow]")
                console.print("    [yellow]Or alternatively: 'write:org'[/yellow]")

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()

