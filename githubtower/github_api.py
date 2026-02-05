"""GitHub API wrapper for managing Projects."""

import json
from typing import List, Optional, Dict, Any
from github import Github
from github.Project import Project
from github.ProjectCard import ProjectCard
from github.ProjectColumn import ProjectColumn
from github.Repository import Repository
from github.Organization import Organization
from github.GithubException import GithubException
import requests

from .config import Config


class GitHubProjectManager:
    """Manager for GitHub Projects via API."""

    def __init__(self, config: Config):
        """Initialize GitHub API client.

        Args:
            config: Configuration instance

        Raises:
            ValueError: If GitHub token is not configured
        """
        token = config.github_token
        if not token:
            raise ValueError(
                "GitHub token not found. Set GITHUB_TOKEN or GH_TOKEN environment variable."
            )

        self.github = Github(token)
        self.config = config
        self._org: Optional[Organization] = None

    @property
    def org(self) -> Optional[Organization]:
        """Get organization instance if configured."""
        if not self._org and self.config.github_org:
            try:
                self._org = self.github.get_organization(self.config.github_org)
            except GithubException:
                pass
        return self._org

    def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID.

        Args:
            project_id: GitHub project ID

        Returns:
            Project instance or None if not found
        """
        try:
            if self.org:
                # Try organization projects first
                projects = self.org.get_projects()
                for project in projects:
                    if project.id == project_id:
                        return project
            else:
                # Try user projects
                user = self.github.get_user()
                projects = user.get_projects()
                for project in projects:
                    if project.id == project_id:
                        return project
        except GithubException:
            pass
        return None

    def get_project_by_name(self, name: str, owner: Optional[str] = None) -> Optional[Project]:
        """Get a project by name.

        For organizations, tries GraphQL API (Projects V2) first, then falls back to REST API.
        For users, uses REST API (Projects classic).

        Args:
            name: Project name
            owner: Optional owner (org or user). Uses config default if not provided.

        Returns:
            Project instance or None if not found
        """
        target_owner = owner or (self.org.name if self.org else None)
        is_org = False

        if target_owner:
            try:
                org = self.github.get_organization(target_owner)
                is_org = True
            except GithubException:
                pass

        if is_org:
            # Try GraphQL API first for Projects V2
            try:
                owner_id = self._get_owner_node_id(target_owner)
                projects_v2 = self._list_projects_via_graphql(owner_id)
                
                for project_data in projects_v2:
                    if project_data.get("title") == name:
                        # Projects V2 are not compatible with PyGithub Project objects
                        # Return None for now - we'll need to handle this differently
                        # For now, we'll fall back to REST API
                        break
            except GithubException:
                pass

        # Fall back to REST API (Projects classic)
        try:
            if owner:
                org = self.github.get_organization(owner)
                projects = org.get_projects()
            elif self.org:
                projects = self.org.get_projects()
            else:
                user = self.github.get_user()
                projects = user.get_projects()

            for project in projects:
                if project.name == name:
                    return project
        except GithubException:
            pass
        return None

    def _list_projects_via_graphql(self, owner_id: str) -> List[Dict[str, Any]]:
        """List projects using GraphQL API (for Projects V2).

        Args:
            owner_id: GitHub node ID of the organization or user

        Returns:
            List of project data dictionaries
        """
        token = self.config.github_token
        if not token:
            raise ValueError("GitHub token is required for GraphQL API")

        query = """
        query ListProjectsV2($ownerId: ID!, $first: Int!) {
            node(id: $ownerId) {
                ... on Organization {
                    projectsV2(first: $first) {
                        nodes {
                            id
                            number
                            title
                            shortDescription
                            url
                            public
                            closed
                            createdAt
                            updatedAt
                        }
                    }
                }
                ... on User {
                    projectsV2(first: $first) {
                        nodes {
                            id
                            number
                            title
                            shortDescription
                            url
                            public
                            closed
                            createdAt
                            updatedAt
                        }
                    }
                }
            }
        }
        """

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

        all_projects = []
        has_next_page = True
        cursor = None
        first = 100  # GitHub allows up to 100 items per page

        while has_next_page:
            variables = {
                "ownerId": owner_id,
                "first": first,
            }
            if cursor:
                query_with_pagination = query.replace(
                    "projectsV2(first: $first)",
                    "projectsV2(first: $first, after: $after)"
                )
                variables["after"] = cursor
            else:
                query_with_pagination = query

            try:
                response = requests.post(
                    "https://api.github.com/graphql",
                    json={"query": query_with_pagination, "variables": variables},
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
                    raise GithubException(
                        400,
                        f"GraphQL errors: {', '.join(error_messages)}",
                        {},
                    )

                if "data" in data and "node" in data["data"] and data["data"]["node"]:
                    node = data["data"]["node"]
                    if "projectsV2" in node:
                        projects_data = node["projectsV2"]["nodes"]
                        all_projects.extend(projects_data)
                        
                        # Check for pagination
                        page_info = node["projectsV2"].get("pageInfo", {})
                        has_next_page = page_info.get("hasNextPage", False)
                        cursor = page_info.get("endCursor")
                    else:
                        has_next_page = False
                else:
                    has_next_page = False
            except requests.exceptions.RequestException as e:
                raise GithubException(
                    500,
                    f"GraphQL request failed: {str(e)}",
                    {},
                )

        return all_projects

    def list_projects(self, owner: Optional[str] = None) -> List[Project]:
        """List all projects.

        For organizations, uses GraphQL API to list Projects V2 (beta).
        For users, uses REST API to list Projects (classic).

        Args:
            owner: Optional owner (org or user). Uses config default if not provided.

        Returns:
            List of Project instances (empty for GraphQL projects, as they're not compatible)
        """
        target_owner = owner or (self.org.name if self.org else None)
        is_org = False

        if target_owner:
            try:
                org = self.github.get_organization(target_owner)
                is_org = True
            except GithubException:
                pass

        if is_org:
            # Use GraphQL API for organization projects (Projects V2)
            try:
                owner_id = self._get_owner_node_id(target_owner)
                projects_v2 = self._list_projects_via_graphql(owner_id)
                # Return empty list for now - Projects V2 are not compatible with PyGithub Project objects
                # The CLI will handle displaying them differently
                return []
            except GithubException:
                # Fall back to REST API if GraphQL fails
                try:
                    if owner:
                        org = self.github.get_organization(owner)
                        return list(org.get_projects())
                    elif self.org:
                        return list(self.org.get_projects())
                except GithubException:
                    return []
        else:
            # Use REST API for user projects (Projects classic)
            try:
                if owner:
                    user = self.github.get_user(owner)
                    return list(user.get_projects())
                else:
                    user = self.github.get_user()
                    return list(user.get_projects())
            except GithubException:
                return []
        
        return []

    def _create_project_via_graphql(
        self,
        name: str,
        body: Optional[str] = None,
        owner_id: str = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a project using GraphQL API (for organizations).

        Args:
            name: Project name
            body: Optional project description
            owner_id: GitHub node ID of the organization or user

        Returns:
            Project data dictionary with 'id' and 'number' or None if creation failed
        """
        token = self.config.github_token
        if not token:
            raise ValueError("GitHub token is required for GraphQL API")

        # GraphQL mutation to create a ProjectV2 (Projects beta for organizations)
        mutation = """
        mutation CreateProjectV2($input: CreateProjectV2Input!) {
            createProjectV2(input: $input) {
                projectV2 {
                    id
                    number
                    title
                    url
                    public
                }
            }
        }
        """

        variables = {
            "input": {
                "ownerId": owner_id,
                "title": name,
                # Note: shortDescription is not available in CreateProjectV2Input
                # Description can be updated later via updateProjectV2 mutation if needed
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

        try:
            response = requests.post(
                "https://api.github.com/graphql",
                json={"query": mutation, "variables": variables},
                headers=headers,
                timeout=30,
            )
            
            # Check HTTP status first
            if response.status_code != 200:
                raise GithubException(
                    response.status_code,
                    f"GraphQL HTTP error {response.status_code}: {response.text[:200]}",
                    {},
                )
            
            data = response.json()

            if "errors" in data:
                error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
                error_types = [err.get("type", "") for err in data["errors"]]
                error_paths = [err.get("path", []) for err in data["errors"]]
                
                # Build detailed error message
                full_error = f"GraphQL errors: {', '.join(error_messages)}"
                if error_types:
                    full_error += f" (types: {', '.join(error_types)})"
                if any(paths for paths in error_paths):
                    paths_str = ", ".join([str(p) for paths in error_paths for p in paths if paths])
                    if paths_str:
                        full_error += f" (paths: {paths_str})"
                
                # Check for specific permission errors
                if any("FORBIDDEN" in t or "permission" in msg.lower() or "scope" in msg.lower() 
                       for t, msg in zip(error_types, error_messages)):
                    full_error += "\nThis might indicate missing scopes. Required: 'project' scope for creating organization projects."
                
                raise GithubException(
                    400,
                    full_error,
                    {},
                )

            if "data" in data:
                if "createProjectV2" in data["data"]:
                    if data["data"]["createProjectV2"] is None:
                        # createProjectV2 returned null - this usually means permission denied
                        raise GithubException(
                            403,
                            "GraphQL createProjectV2 returned null. This usually means your token lacks the 'project' scope "
                            "required for creating organization projects. Check your token permissions.",
                            {},
                        )
                    project_data = data["data"]["createProjectV2"]["projectV2"]
                    return project_data
                else:
                    # No createProjectV2 in response - unexpected
                    raise GithubException(
                        500,
                        f"GraphQL response missing 'createProjectV2' field. Response: {json.dumps(data, indent=2)}",
                        {},
                    )

            # If we get here, something unexpected happened
            raise GithubException(
                500,
                f"Unexpected GraphQL response format. Response: {json.dumps(data, indent=2)}",
                {},
            )
        except requests.exceptions.RequestException as e:
            raise GithubException(
                500,
                f"GraphQL request failed: {str(e)}",
                {},
            )

    def _get_owner_node_id(self, owner: str) -> Optional[str]:
        """Get the GraphQL node ID for an organization or user.

        Args:
            owner: Organization or user login

        Returns:
            Node ID string or None if not found

        Raises:
            GithubException: If request fails or organization/user not found
        """
        token = self.config.github_token
        if not token:
            raise GithubException(401, "GitHub token is required", {})

        # Try organization first
        query_org = """
        query GetOrganization($login: String!) {
            organization(login: $login) {
                id
            }
        }
        """

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                "https://api.github.com/graphql",
                json={"query": query_org, "variables": {"login": owner}},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                # Check if it's a "not found" error - try as user
                error_types = [err.get("type", "") for err in data["errors"]]
                if "NOT_FOUND" in error_types:
                    # Try as user instead
                    query_user = """
                    query GetUser($login: String!) {
                        user(login: $login) {
                            id
                        }
                    }
                    """
                    response = requests.post(
                        "https://api.github.com/graphql",
                        json={"query": query_user, "variables": {"login": owner}},
                        headers=headers,
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if "errors" in data:
                        error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
                        error_types = [err.get("type", "") for err in data["errors"]]
                        # Check for permission errors
                        if any("FORBIDDEN" in t or "permission" in msg.lower() for t, msg in zip(error_types, error_messages)):
                            raise GithubException(
                                403,
                                f"Permission denied accessing '{owner}' via GraphQL. "
                                f"Make sure your token has 'read:org' scope. "
                                f"Errors: {', '.join(error_messages)}",
                                {},
                            )
                        raise GithubException(
                            404,
                            f"GraphQL: Could not find organization or user '{owner}' via GraphQL: {', '.join(error_messages)}",
                            {},
                        )
                else:
                    # Other GraphQL errors
                    error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
                    raise GithubException(
                        400,
                        f"GraphQL errors: {', '.join(error_messages)}",
                        {},
                    )

            if "data" in data:
                if "organization" in data["data"] and data["data"]["organization"]:
                    return data["data"]["organization"]["id"]
                elif "user" in data["data"] and data["data"]["user"]:
                    return data["data"]["user"]["id"]

            # If we get here, the query succeeded but returned no data
            raise GithubException(
                404, 
                f"GraphQL: Could not find organization or user '{owner}' via GraphQL. "
                f"Response: {json.dumps(data, indent=2)}",
                {}
            )
        except requests.exceptions.RequestException as e:
            raise GithubException(500, f"GraphQL request failed: {str(e)}", {})

    def create_project(
        self,
        name: str,
        body: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> Optional[Project]:
        """Create a new project.

        Uses GraphQL API for organization projects and REST API for user projects.

        Args:
            name: Project name
            body: Optional project description
            owner: Optional owner (org or user). Uses config default if not provided.

        Returns:
            Created Project instance or None if creation failed (None for GraphQL projects)

        Raises:
            GithubException: If project creation fails
        """
        # Determine target owner and is_org flag BEFORE the try block
        # so they're available in the except block
        target_owner = None
        is_org = False
        
        # Get owner from parameter, config, or org property
        if owner:
            target_owner = owner
        else:
            # Try to get from org property
            try:
                if self.org:
                    target_owner = self.org.name
                elif self.config.github_org:
                    target_owner = self.config.github_org
            except Exception:
                target_owner = self.config.github_org if self.config.github_org else None

        if target_owner:
            # Check if it's an organization
            try:
                org = self.github.get_organization(target_owner)
                is_org = True
            except GithubException:
                # Not an org, will try as user
                pass

        try:
            if is_org:
                # Use GraphQL API for organization projects
                try:
                    # _get_owner_node_id raises exception if it fails
                    owner_id = self._get_owner_node_id(target_owner)
                    
                    # _create_project_via_graphql raises exception if it fails
                    project_data = self._create_project_via_graphql(name, body, owner_id)
                    if not project_data:
                        raise GithubException(
                            500,
                            "GraphQL: Failed to create project via GraphQL API. Check that your token has 'project' scope.",
                            {},
                        )

                    # GraphQL creates Projects (beta), not Projects (classic)
                    # We return None and let the caller handle it
                    # The project was created successfully via GraphQL
                    return None
                except GithubException as ge:
                    # Re-raise GraphQL exceptions with their original message
                    # This ensures GraphQL error messages are preserved
                    # Make sure the error message contains "GraphQL" if it doesn't already
                    error_msg = str(ge)
                    if "GraphQL" not in error_msg and "graphql" not in error_msg.lower():
                        # Wrap it to ensure it's detected as GraphQL error
                        raise GithubException(
                            ge.status,
                            f"GraphQL: {error_msg}",
                            ge.headers,
                        )
                    raise ge
                except Exception as e:
                    # Wrap unexpected errors
                    raise GithubException(
                        500,
                        f"GraphQL: Unexpected error creating organization project via GraphQL: {str(e)}",
                        {},
                    )
            else:
                # Create user project via REST API
                if owner and not is_org:
                    user = self.github.get_user(owner)
                    return user.create_project(name, body=body)
                else:
                    # Create project for authenticated user
                    user = self.github.get_user()
                    return user.create_project(name, body=body)
        except GithubException as e:
            # Check if this is a GraphQL error (from the inner try/except)
            error_msg = str(e)
            error_status = e.status
            
            # CRITICAL: If is_org is True, this MUST be a GraphQL error
            # Force it to be treated as GraphQL error regardless of error message content
            if is_org:
                # Always prefix with GraphQL to ensure it's detected
                if "GraphQL" not in error_msg and "graphql" not in error_msg.lower():
                    raise GithubException(
                        error_status,
                        f"GraphQL: {error_msg}",
                        e.headers,
                    )
                # Already has GraphQL indicator, re-raise as-is
                raise
            
            # Preserve GraphQL error messages - they already have good context
            # Check for various GraphQL error indicators
            graphql_indicators = [
                "GraphQL",
                "graphql",
                "Could not find organization",
                "Could not find organization or user",
                "project scope",
                "read:org",
                "GraphQL request failed",
                "GraphQL errors:",
                "createProject",
                "createProjectV2",
                "GraphQL HTTP error",
                "via GraphQL",
            ]
            
            if any(indicator.lower() in error_msg.lower() for indicator in graphql_indicators):
                # Re-raise GraphQL errors as-is - they have good error messages
                raise
            
            # Otherwise, add context for REST API errors
            if e.status == 404:
                # If is_org is True, this MUST be a GraphQL error that wasn't detected
                if is_org:
                    # Force it to be treated as GraphQL error
                    raise GithubException(
                        e.status,
                        f"GraphQL: Organization '{target_owner}' project creation failed (404). "
                        f"Make sure your token has 'read:org' and 'project' scopes for GraphQL API. "
                        f"Original error: {error_msg}",
                        e.headers,
                    )
                elif owner:
                    error_msg = f"Owner '{owner}' not found or you don't have access. Check if the organization/user exists and your token has the required permissions."
                else:
                    error_msg = "Project creation failed. Your token may not have the required permissions (repo scope for user projects)."
            elif e.status == 403:
                if is_org:
                    error_msg = "Permission denied. Your token needs 'project' or 'write:org' scope for organization projects (GraphQL API)."
                else:
                    error_msg = "Permission denied. Your token needs 'repo' scope for user projects."
            raise GithubException(e.status, error_msg, e.headers)

    def get_project_columns(self, project: Project) -> List[ProjectColumn]:
        """Get all columns for a project.

        Args:
            project: Project instance

        Returns:
            List of ProjectColumn instances
        """
        try:
            return list(project.get_columns())
        except GithubException:
            return []

    def get_column_cards(self, column: ProjectColumn) -> List[ProjectCard]:
        """Get all cards in a column.

        Args:
            column: ProjectColumn instance

        Returns:
            List of ProjectCard instances
        """
        try:
            return list(column.get_cards())
        except GithubException:
            return []

    def create_column(self, project: Project, name: str) -> Optional[ProjectColumn]:
        """Create a new column in a project.

        Args:
            project: Project instance
            name: Column name

        Returns:
            Created ProjectColumn instance or None if creation failed
        """
        try:
            return project.create_column(name)
        except GithubException as e:
            print(f"Error creating column: {e}")
            return None

    def create_card(
        self,
        column: ProjectColumn,
        note: Optional[str] = None,
        issue: Optional[Any] = None,
    ) -> Optional[ProjectCard]:
        """Create a new card in a column.

        Args:
            column: ProjectColumn instance
            note: Optional note text for the card
            issue: Optional issue to attach to the card

        Returns:
            Created ProjectCard instance or None if creation failed
        """
        try:
            if issue:
                return column.create_card(content_id=issue.id, content_type="Issue")
            elif note:
                return column.create_card(note=note)
            else:
                raise ValueError("Either note or issue must be provided")
        except (GithubException, ValueError) as e:
            print(f"Error creating card: {e}")
            return None

    def move_card(self, card: ProjectCard, column: ProjectColumn, position: str = "top") -> bool:
        """Move a card to a different column.

        Args:
            card: ProjectCard instance to move
            column: Target ProjectColumn instance
            position: Position in column ("top", "bottom", or "after:<card_id>")

        Returns:
            True if move was successful, False otherwise
        """
        try:
            card.move(position=position, column_id=column.id)
            return True
        except GithubException as e:
            print(f"Error moving card: {e}")
            return False

    def get_project_v2_fields(self, project_node_id: str) -> List[Dict[str, Any]]:
        """Get all fields for a Projects V2 project.
        
        Note: Due to GraphQL union type limitations with ProjectV2FieldConfiguration,
        we extract field information from items instead of querying fields directly.

        Args:
            project_node_id: GraphQL node ID of the project

        Returns:
            List of field data dictionaries (extracted from items)
        """
        # Instead of querying fields directly (which has union type issues),
        # we'll extract field information from the items we query
        # This method returns an empty list - field extraction happens in sync.py
        # when processing items
        return []

    def get_project_v2_items(self, project_node_id: str) -> List[Dict[str, Any]]:
        """Get all items for a Projects V2 project.

        Args:
            project_node_id: GraphQL node ID of the project

        Returns:
            List of item data dictionaries with their field values
        """
        token = self.config.github_token
        if not token:
            raise ValueError("GitHub token is required for GraphQL API")

        query = """
        query GetProjectItems($projectId: ID!, $first: Int!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: $first) {
                        nodes {
                            id
                            type
                            content {
                                ... on Issue {
                                    title
                                    body
                                    number
                                    url
                                }
                                ... on PullRequest {
                                    title
                                    body
                                    number
                                    url
                                }
                                ... on DraftIssue {
                                    title
                                    body
                                }
                            }
                            fieldValues(first: 20) {
                                nodes {
                                    ... on ProjectV2ItemFieldTextValue {
                                        text
                                        field {
                                            ... on ProjectV2FieldCommon {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldNumberValue {
                                        number
                                        field {
                                            ... on ProjectV2FieldCommon {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldDateValue {
                                        date
                                        field {
                                            ... on ProjectV2FieldCommon {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldSingleSelectValue {
                                        name
                                        field {
                                            ... on ProjectV2FieldCommon {
                                                name
                                            }
                                        }
                                    }
                                    ... on ProjectV2ItemFieldIterationValue {
                                        title
                                        field {
                                            ... on ProjectV2FieldCommon {
                                                name
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                    }
                }
            }
        }
        """

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

        all_items = []
        has_next_page = True
        cursor = None
        first = 100

        while has_next_page:
            variables = {
                "projectId": project_node_id,
                "first": first,
            }
            if cursor:
                query_with_pagination = query.replace(
                    "items(first: $first)",
                    "items(first: $first, after: $after)"
                )
                variables["after"] = cursor
            else:
                query_with_pagination = query

            try:
                response = requests.post(
                    "https://api.github.com/graphql",
                    json={"query": query_with_pagination, "variables": variables},
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    error_messages = [err.get("message", "Unknown error") for err in data["errors"]]
                    raise GithubException(
                        400,
                        f"GraphQL errors: {', '.join(error_messages)}",
                        {},
                    )

                if "data" in data and "node" in data["data"] and data["data"]["node"]:
                    node = data["data"]["node"]
                    if "items" in node:
                        items_data = node["items"]["nodes"]
                        all_items.extend(items_data)
                        
                        page_info = node["items"].get("pageInfo", {})
                        has_next_page = page_info.get("hasNextPage", False)
                        cursor = page_info.get("endCursor")
                    else:
                        has_next_page = False
                else:
                    has_next_page = False
            except requests.exceptions.RequestException as e:
                raise GithubException(
                    500,
                    f"GraphQL request failed: {str(e)}",
                    {},
                )

        return all_items

    def get_repository(self, owner: str, repo: str) -> Optional[Repository]:
        """Get a repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository instance or None if not found
        """
        try:
            return self.github.get_repo(f"{owner}/{repo}")
        except GithubException:
            return None

    def check_token_permissions(self) -> Dict[str, Any]:
        """Check token permissions and access.

        Returns:
            Dictionary with permission check results
        """
        results = {
            "token_set": bool(self.config.github_token),
            "rest_api": {"accessible": False, "user": None, "scopes": []},
            "graphql_api": {"accessible": False, "errors": []},
            "organization_access": {},
        }

        if not self.config.github_token:
            return results

        # Check REST API access
        try:
            user = self.github.get_user()
            results["rest_api"]["accessible"] = True
            results["rest_api"]["user"] = user.login
            
            # Try to get rate limit info which shows scopes
            try:
                rate_limit = self.github.get_rate_limit()
                # Note: PyGithub doesn't expose scopes directly, but we can infer from what works
            except Exception:
                pass
        except Exception as e:
            results["rest_api"]["errors"] = [str(e)]

        # Check GraphQL API access
        token = self.config.github_token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Test GraphQL query
        query = """
        query {
            viewer {
                login
            }
        }
        """

        try:
            import requests
            response = requests.post(
                "https://api.github.com/graphql",
                json={"query": query},
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                results["graphql_api"]["errors"] = [
                    err.get("message", "Unknown error") for err in data["errors"]
                ]
            else:
                results["graphql_api"]["accessible"] = True
                if "data" in data and "viewer" in data["data"]:
                    results["graphql_api"]["user"] = data["data"]["viewer"].get("login")
        except Exception as e:
            results["graphql_api"]["errors"] = [str(e)]

        # Check organization access if configured
        if self.config.github_org:
            org_name = self.config.github_org
            results["organization_access"][org_name] = {
                "rest_api": {"accessible": False, "errors": []},
                "graphql_api": {"accessible": False, "node_id": None, "errors": []},
            }

            # REST API check
            try:
                org = self.github.get_organization(org_name)
                results["organization_access"][org_name]["rest_api"]["accessible"] = True
                results["organization_access"][org_name]["rest_api"]["name"] = org.name
            except Exception as e:
                results["organization_access"][org_name]["rest_api"]["errors"] = [str(e)]

            # GraphQL API check
            try:
                owner_id = self._get_owner_node_id(org_name)
                if owner_id:
                    results["organization_access"][org_name]["graphql_api"]["accessible"] = True
                    results["organization_access"][org_name]["graphql_api"]["node_id"] = owner_id
            except Exception as e:
                results["organization_access"][org_name]["graphql_api"]["errors"] = [str(e)]

        return results

