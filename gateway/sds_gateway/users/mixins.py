from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models import QuerySet
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.users.models import User
from sds_gateway.users.utils import deduplicate_composite_captures
from sds_gateway.users.utils import serialize_composite_capture_for_display

# Constants
MIN_SEARCH_QUERY_LENGTH = 2


class ApprovedUserRequiredMixin(AccessMixin):
    """Verify that the current user is approved."""

    def dispatch(self, request, *args, **kwargs) -> HttpResponseRedirect:
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_approved:
            messages.error(
                request=request,
                message=_(
                    "Your account is not approved to use API features. "
                    "Please contact the administrator.",
                ),
            )
            return redirect(reverse("home"))
        return super().dispatch(request, *args, **kwargs)


class Auth0LoginRequiredMixin(LoginRequiredMixin):
    """Custom mixin that redirects to Auth0 login instead of the default login page"""

    def get_login_url(self) -> str:
        return reverse("auth0_login")


class UserSearchMixin:
    """Mixin to handle user search functionality for sharing."""

    def search_users(
        self,
        request,
        exclude_user_ids=None,
        exclude_group_ids=None,
        include_groups: bool = True,  # noqa: FBT001, FBT002
    ) -> JsonResponse:
        """
        Search for users and groups to share with by name or email.

        This method searches for users by exact name or email, and also includes users
        that the current user has previously interacted with. Optionally includes
        share groups owned by the current user.

        Args:
            request: The HTTP request object
            exclude_user_ids: A list of user IDs to exclude from the search results
            include_groups: Whether to include share groups in the search results

        Returns:
            A JSON response containing the search results
        """
        query = request.GET.get("q", "").strip()
        limit = 10  # max 10 results

        if not query or len(query) < MIN_SEARCH_QUERY_LENGTH:
            return JsonResponse(
                {"error": "Search query must be at least 2 characters long"}, status=400
            )

        previously_shared_with_users = UserSharePermission.objects.filter(
            owner=request.user,
            is_deleted=False,
        ).values_list("shared_with__id", flat=True)

        previously_shared_from_users = UserSharePermission.objects.filter(
            shared_with=request.user,
            is_deleted=False,
        ).values_list("owner__id", flat=True)

        # Queryset of previously interacted with users
        previously_interacted_with_users = User.objects.filter(
            Q(id__in=previously_shared_with_users)
            | Q(id__in=previously_shared_from_users)
        )

        # Search for users by name or email, excluding the current user
        users = (
            User.objects.filter(
                Q(email=query)
                | (
                    Q(id__in=previously_interacted_with_users)
                    & (Q(name__icontains=query) | Q(email__icontains=query))
                )
            )
            .filter(
                is_approved=True,  # Only show approved users
            )
            .exclude(id=request.user.id)
        )

        # Exclude additional users if provided
        if exclude_user_ids:
            users = users.exclude(id__in=exclude_user_ids)

        users = users[:limit]

        # Serialize users for response
        users_data = [
            {"name": user.name, "email": user.email, "type": "user"} for user in users
        ]

        # Add groups if requested
        if include_groups:
            # Search for share groups owned by the current user
            groups = ShareGroup.objects.filter(
                owner=request.user, is_deleted=False, name__icontains=query
            )

            # Exclude groups if provided
            if exclude_group_ids:
                groups = groups.exclude(uuid__in=exclude_group_ids)

            groups = groups[:limit]

            groups_data = [
                {
                    "name": group.name,
                    "email": f"group:{group.uuid}",  # Use group UUID as identifier
                    "type": "group",
                    "member_count": group.members.count(),
                }
                for group in groups
            ]

            # Combine users and groups, prioritizing groups first
            all_results = []

            # Add exact email matches first (highest priority)
            exact_email_users = [u for u in users_data if u["email"] == query]
            all_results.extend(exact_email_users)

            # Add exact group name matches (second priority)
            exact_name_groups = [
                g for g in groups_data if g["name"].lower() == query.lower()
            ]
            all_results.extend(exact_name_groups)

            # Add remaining groups first (third priority)
            remaining_groups = [g for g in groups_data if g not in exact_name_groups]
            all_results.extend(remaining_groups)

            # Add remaining users last (lowest priority)
            remaining_users = [u for u in users_data if u not in exact_email_users]
            all_results.extend(remaining_users)

            # Limit total results
            all_results = all_results[:limit]
        else:
            all_results = users_data

        return JsonResponse(all_results, safe=False)


class FormSearchMixin:
    """Mixin for search form in group captures view"""

    def search_captures(self, search_data, request) -> list[Capture]:
        # Get captures owned by the user
        owned_captures = Capture.objects.filter(
            owner=request.user,
            is_deleted=False,
        )

        # Get captures shared with the user (exclude owned)
        shared_captures = Capture.objects.filter(
            shared_with=request.user,
            is_deleted=False,
        ).exclude(owner=request.user)

        # Combine owned and shared captures
        queryset = owned_captures.union(shared_captures)

        # Build a Q object for complex queries
        q_objects = Q()

        if search_data.get("directory"):
            q_objects &= Q(top_level_dir__icontains=search_data["directory"])
        if search_data.get("capture_type"):
            q_objects &= Q(capture_type=search_data["capture_type"])
        if search_data.get("scan_group"):
            q_objects &= Q(scan_group__icontains=search_data["scan_group"])
        if search_data.get("channel"):
            q_objects &= Q(channel__icontains=search_data["channel"])

        queryset = queryset.filter(q_objects).order_by("-created_at")

        # Use utility function to deduplicate composite captures
        return deduplicate_composite_captures(list(queryset))

    def search_files(
        self, search_data: dict[str, Any], request
    ) -> QuerySet[File, File]:
        # Only show files that are not associated with a capture
        queryset = File.objects.filter(
            owner=request.user,
            capture__isnull=True,
            is_deleted=False,
        )

        if search_data.get("file_name"):
            queryset = queryset.filter(Q(name__icontains=search_data["file_name"]))
        if search_data.get("directory"):
            queryset = queryset.filter(Q(directory__icontains=search_data["directory"]))
        if search_data.get("file_extension"):
            queryset = queryset.filter(Q(name__endswith=search_data["file_extension"]))

        return queryset.order_by("-created_at")

    def serialize_item(
        self,
        item: Capture | File,
        relative_path: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(item, Capture):
            # Use utility function for consistent composite capture serialization
            return serialize_composite_capture_for_display(item)
        if isinstance(item, File):
            return {
                "id": item.uuid,
                "name": item.name,
                "media_type": item.media_type,
                "size": item.size,
                "relative_path": relative_path,
                "owner": {
                    "id": item.owner.id if item.owner else None,
                    "name": item.owner.name if item.owner else None,
                    "email": item.owner.email if item.owner else None,
                }
                if item.owner
                else None,
            }

        # this should never happen
        return {}

    def get_paginated_response(
        self, queryset, request, page_size=10, page_param="page"
    ) -> dict[str, Any]:
        paginator = Paginator(queryset, page_size)
        page = paginator.get_page(request.GET.get(page_param, 1))

        return {
            "results": [self.serialize_item(item) for item in page],
            "pagination": {
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
                "number": page.number,
                "num_pages": paginator.num_pages,
            },
        }


class FileTreeMixin:
    """
    Mixin for file tree rendering functionality used by
    GroupCapturesView and DatasetDetailsView.
    """

    def _get_directory_tree(
        self, files: QuerySet[File], base_dir: str
    ) -> dict[str, Any]:
        """
        Build a nested directory tree structure with
        a specific base directory.

        Args:
            files: QuerySet of files to add to the tree
            base_dir: The base directory to add files to

        Returns:
            A dictionary representing the directory tree
        """

        tree = {}

        # Add files in base directory if they exist
        tree["files"] = self._add_files_to_tree_queryset(files, base_dir)

        # Initialize the children
        tree["children"] = {}

        # Get all directories that start with base_dir
        distinct_file_paths = (
            files.filter(directory__startswith=base_dir)
            .values_list("directory", flat=True)
            .distinct()
        )

        for file_path in distinct_file_paths:
            # Skip if it's the base directory itself
            if file_path == base_dir:
                continue

            # Get relative path from base_dir
            rel_path = file_path.replace(base_dir, "").strip("/")
            if not rel_path:
                continue

            # Split path into parts and build nested structure
            path_parts = rel_path.split("/")

            # initialize the children
            current_dict = tree["children"]

            # Build the path one level at a time
            current_path = base_dir
            for part in path_parts:
                current_path = f"{current_path}/{part}"

                if part not in current_dict:
                    current_dict[part] = {
                        "type": "directory",
                        "name": part,
                        "path": current_path,
                        "children": {},
                        "files": [],
                        "size": 0,
                        "created_at": None,
                    }
                    # Add files for this directory level
                    current_dict[part]["files"] = self._add_files_to_tree_queryset(
                        files,
                        current_path,
                    )

                # Move to the children dictionary for the next iteration
                current_dict = current_dict[part]["children"]

        # Now that the tree is built, calculate stats for all directories
        self._update_directory_stats(tree)
        return tree

    def _add_files_to_tree_queryset(
        self, files: QuerySet[File], directory: str
    ) -> list[dict[str, Any]]:
        """
        Add files to tree structure for a specific directory.

        Args:
            files: QuerySet of files to add to the tree
            directory: The directory to add files to

        Returns:
            A list of dictionaries representing the files in the directory
        """
        files_in_directory = files.filter(directory=directory)
        return [
            {
                "id": str(file.uuid),
                "name": file.name,
                "type": "file",
                "media_type": file.media_type,
                "size": file.size,
                "created_at": file.created_at,
                "owner": {
                    "id": file.owner.id if file.owner else None,
                    "name": file.owner.name if file.owner else None,
                    "email": file.owner.email if file.owner else None,
                }
                if file.owner
                else None,
            }
            for file in files_in_directory
        ]

    def _find_common_prefix(self, directories: list[str]) -> str:
        """Find the common prefix among all directories."""
        if not directories:
            return ""

        # Find the shortest directory
        shortest = min(directories, key=len)

        # Find common prefix
        common_prefix = ""
        for i, char in enumerate(shortest):
            if all(
                directory[i] == char for directory in directories if len(directory) > i
            ):
                common_prefix += char
            else:
                break

        # Return up to the last slash
        last_slash = common_prefix.rfind("/")
        if last_slash > 0:
            return common_prefix[: last_slash + 1]
        return ""

    def _add_files_to_tree(
        self, files: list[File], directory: str
    ) -> list[dict[str, Any]]:
        """
        Add files to tree structure for a specific directory.

        Args:
            files: List of files to add to the tree
            directory: The directory to add files to

        Returns:
            A list of dictionaries representing the files in the directory
        """
        files_in_directory = [f for f in files if str(f.directory) == directory]
        return [
            {
                "id": str(file.uuid),
                "name": file.name,
                "type": "file",
                "file_type": "Capture" if file.captures.exists() else "Artifact",
                "media_type": file.media_type,
                "size": file.size or 0,
                "created_at": file.created_at,
                "directory": str(file.directory),
            }
            for file in files_in_directory
        ]

    def _update_directory_stats(self, tree: dict[str, Any]) -> None:
        """
        Update size and date stats for all directories in the tree.

        Args:
            tree: The tree to update
        """
        # Process all directories first
        for dir_data in tree.get("children", {}).values():
            self._update_directory_stats(dir_data)

        # Then calculate stats for current directory
        total_size = 0
        earliest_date = None

        # Process files in current directory
        for file in tree.get("files", []):
            total_size += file.get("size", 0)
            if file.get("created_at"):
                if not earliest_date or file["created_at"] < earliest_date:
                    earliest_date = file["created_at"]

        # Add stats from all subdirectories
        for dir_data in tree.get("children", {}).values():
            total_size += dir_data.get("size", 0)
            dir_date = dir_data.get("created_at")
            if dir_date:
                if not earliest_date or dir_date < earliest_date:
                    earliest_date = dir_date

        # Update current directory stats
        tree["size"] = total_size
        tree["created_at"] = earliest_date

    def _get_file_extension_choices(self, files: list[File]) -> list[tuple[str, str]]:
        """
        Get file extension choices for the select dropdown.

        Args:
            files: List of files to get extension choices for

        Returns:
            A list of tuples representing the file extension choices
        """
        extensions = set()
        for file in files:
            if file.name and "." in file.name:
                ext = file.name.split(".")[-1].lower()
                extensions.add(ext)

        # Sort extensions and create choices
        return [("", "All Extensions")] + [
            (ext, f".{ext.upper()}") for ext in sorted(extensions)
        ]
