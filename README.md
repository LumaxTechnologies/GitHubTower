# GitHubTower

A powerful Python CLI tool to manage GitHub Projects through code, using custom folder structure and YAML files.

## Features

- 🗂️ **Custom Folder Structure**: Organize projects in a structured directory layout
- 📝 **YAML Configuration**: Define projects, columns, and cards using YAML files
- 🔄 **Bidirectional Sync**: Sync between local YAML files and GitHub Projects
- 🚀 **CLI Interface**: Easy-to-use command-line interface
- 📊 **Rich Output**: Beautiful terminal output with colors and tables

## Installation

### From Source

```bash
# Clone the repository
git clone <repository-url>
cd GitHubTower

# Install in development mode
pip install -e .

# Or install with dependencies
pip install -e ".[dev]"
```

## Configuration

### Environment Variables

You can configure GitHub credentials in one of the following ways:

#### Option 1: Environment Variables (Recommended for CI/CD)

Set the following environment variables:

```bash
export GITHUB_TOKEN="your_github_token_here"
export GITHUB_ORG="your_organization"  # Optional, for organization projects
```

#### Option 2: `.env` File

Create a `.env` file in one of these locations (checked in order):

1. **Current working directory** (where you run the command):
   ```bash
   # .env in current directory
   GITHUB_TOKEN=your_github_token_here
   GITHUB_ORG=your_organization
   ```

2. **Config directory** (recommended for persistent setup):
   ```bash
   # ~/.githubtower/.env
   GITHUB_TOKEN=your_github_token_here
   GITHUB_ORG=your_organization
   ```

   To create it:
   ```bash
   mkdir -p ~/.githubtower
   echo "GITHUB_TOKEN=your_github_token_here" > ~/.githubtower/.env
   echo "GITHUB_ORG=your_organization" >> ~/.githubtower/.env
   ```

**Note**: The config directory location (`~/.githubtower/.env`) is recommended as it persists across different working directories and is user-specific.

### GitHub Token

Create a Personal Access Token (PAT) on GitHub:
1. Go to Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate a new token with the following scopes:
   - **`repo`** - Required for creating user projects and accessing repositories
   - **`read:org`** - Recommended for reading organization information
   - **`project`** - Required for creating organization projects via GraphQL API
   - **`write:org`** - Alternative to `project` for organization projects
3. Set it as `GITHUB_TOKEN` environment variable

**Project Creation Methods**: 
- **User Projects**: Created via REST API (GitHub Projects classic)
- **Organization Projects**: Created via GraphQL API (GitHub Projects beta) - automatically handled by the tool

The tool automatically detects if you're creating an organization project and uses the appropriate API (GraphQL for orgs, REST for users).

## Usage

### Create a New Project

```bash
# Create a project with interactive template selection
githubtower create my-project --template

# Create with a specific template (no interactive menu)
githubtower create my-project --template --template-name kanban

# List all available templates
githubtower list-templates

# Create and immediately push to GitHub
githubtower create my-project --name "My Project" --body "Description" --owner myorg
```

**Available Templates:**
- `kanban` - Classic Kanban board (To Do, In Progress, Done)
- `scrum` - Scrum board (Backlog, Sprint Backlog, In Progress, Review, Done)
- `bug-tracking` - Bug tracking board (Triage, In Progress, Testing, Resolved)
- `feature-request` - Feature management (Ideas, Planned, In Development, Released)
- `simple` - Simple 3-column board (To Do, Doing, Done)
- `gtd` - Getting Things Done methodology (Inbox, Next Actions, Waiting, Completed)
- `minimal` - Minimal 2-column board (To Do, Done)
- `custom` - Empty project for custom structure

### Check Token Permissions

```bash
# Verify your GitHub token has the necessary permissions
githubtower check-token
```

This command checks:
- REST API access (for user projects)
- GraphQL API access (for organization projects)
- Organization access (if `GITHUB_ORG` is configured)
- Required scopes and provides recommendations

### List Projects

```bash
# List local projects
githubtower list-projects

# List projects on GitHub
githubtower list-github
```

### Sync Projects

```bash
# Sync local YAML to GitHub
githubtower sync my-project

# Sync from GitHub to local YAML
githubtower sync my-project --from-github
```

### Show Project Details

```bash
githubtower show my-project
```

### Delete a Project

```bash
# Delete locally only
githubtower delete my-project

# Delete locally and attempt GitHub deletion (requires manual deletion on GitHub)
githubtower delete my-project --github
```

## Project Structure

Projects are stored in `~/.githubtower/projects/` by default. Each project has:

```
~/.githubtower/projects/my-project/
├── project.yaml    # Project metadata
├── columns.yaml    # Column definitions
└── cards.yaml      # Card definitions
```

### project.yaml

```yaml
name: My Project
body: Project description
owner: myorg  # Optional, uses default from config if not set
github_id: 123456  # Set after syncing to GitHub
```

### columns.yaml

```yaml
columns:
  - name: To Do
    position: 1
    github_id: 789012  # Set after syncing
  - name: In Progress
    position: 2
    github_id: 789013
  - name: Done
    position: 3
    github_id: 789014
```

### cards.yaml

```yaml
cards:
  - note: "Example card"
    column: "To Do"
    position: "top"
  - note: "Another card"
    column: "In Progress"
    position: "bottom"
```

## Examples

### Workflow: Create and Manage a Project

```bash
# 1. Create project locally with templates
githubtower create sprint-2024-q1 --template

# 2. Edit YAML files in ~/.githubtower/projects/sprint-2024-q1/
#    - Update project.yaml with name and description
#    - Define columns in columns.yaml
#    - Add cards in cards.yaml

# 3. Sync to GitHub
githubtower sync sprint-2024-q1

# 4. View project
githubtower show sprint-2024-q1

# 5. Make changes on GitHub, then sync back
githubtower sync sprint-2024-q1 --from-github
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black githubtower/
ruff check githubtower/
```

## License

MIT
