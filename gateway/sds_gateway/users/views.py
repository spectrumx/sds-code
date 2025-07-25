import datetime
import json
import logging
from pathlib import Path
from typing import Any
from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import EmptyPage
from django.core.paginator import PageNotAnInteger
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError
from django.db.models import Q
from django.db.models import Sum
from django.db.models.query import QuerySet
from django.db.utils import IntegrityError
from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import TemplateView
from django.views.generic import UpdateView
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import notify_shared_users
from sds_gateway.api_methods.tasks import send_item_files_email
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.forms import CaptureSearchForm
from sds_gateway.users.forms import DatasetInfoForm
from sds_gateway.users.forms import FileSearchForm
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.mixins import FileTreeMixin
from sds_gateway.users.mixins import FormSearchMixin
from sds_gateway.users.mixins import UserSearchMixin
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey
from sds_gateway.users.utils import deduplicate_composite_captures

# Add logger for debugging
logger = logging.getLogger(__name__)


class UserDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    slug_field = "id"
    slug_url_arg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(Auth0LoginRequiredMixin, SuccessMessageMixin, UpdateView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        # for mypy to know that the user is authenticated
        assert self.request.user.is_authenticated
        return self.request.user.get_absolute_url()

    def get_object(self, queryset=None) -> AbstractBaseUser | AnonymousUser:
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(Auth0LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self) -> str:
        return reverse("users:generate_api_key")


user_redirect_view = UserRedirectView.as_view()


class GenerateAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/user_api_key.html"

    def get(self, request, *args, **kwargs):
        # check if API key expired
        api_key = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .first()
        )
        if api_key is None:
            return render(
                request,
                template_name=self.template_name,
                context={
                    "api_key": False,
                    "expires_at": None,
                    "expired": False,
                },
            )

        return render(
            request,
            template_name=self.template_name,
            context={
                "api_key": True,  # return True if API key exists
                "expires_at": api_key.expiry_date.strftime("%Y-%m-%d %H:%M:%S")
                if api_key.expiry_date
                else "Does not expire",
                "expired": api_key.expiry_date < datetime.datetime.now(datetime.UTC)
                if api_key.expiry_date
                else False,
            },
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Regenerates an API key for the authenticated user."""
        existing_api_key = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .first()
        )
        if existing_api_key:
            existing_api_key.delete()

        # create an API key for the user (with no expiration date for now)
        _, raw_key = UserAPIKey.objects.create_key(
            name=request.user.email,
            user=request.user,
            source=KeySources.SDSWebUI,
        )
        return render(
            request,
            template_name=self.template_name,
            context={
                "api_key": raw_key,  # key only returned when API key is created
                "expires_at": None,
                "expired": False,
            },
        )


user_generate_api_key_view = GenerateAPIKeyView.as_view()


class ShareItemView(Auth0LoginRequiredMixin, UserSearchMixin, View):
    """
    View to handle item sharing functionality using
    the generalized UserSharePermission model.

    This view is used to search for users to share with,
    add users to item sharing, and remove users from item sharing.

    It also handles the notification of shared users.
    """

    # Map item types to their corresponding models
    ITEM_MODELS = {
        ItemType.DATASET: Dataset,
        ItemType.CAPTURE: Capture,
    }

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Handle user search requests."""
        item_uuid = kwargs.get("item_uuid")
        item_type = kwargs.get("item_type")

        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse(
                {"error": "Invalid item type"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get the item to check existing shared users
        try:
            model_class = self.ITEM_MODELS[item_type]
            # Verify the item exists and user owns it
            model_class.objects.get(uuid=item_uuid, owner=request.user)

            # Get users already shared with this item using the new model
            shared_user_ids = list(
                UserSharePermission.objects.filter(
                    item_uuid=item_uuid,
                    item_type=item_type,
                    owner=request.user,
                    is_deleted=False,
                    is_enabled=True,
                ).values_list("shared_with__id", flat=True)
            )
        except model_class.DoesNotExist:
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Use the enhanced mixin method with exclusions
        return self.search_users(request, exclude_user_ids=shared_user_ids)

    def _parse_remove_users(self, request: HttpRequest) -> list[str]:
        """Parse the remove_users JSON from the request."""
        remove_users_json = request.POST.get("remove_users", "")
        if not remove_users_json:
            return []
        try:
            return json.loads(remove_users_json)
        except json.JSONDecodeError as err:
            msg = "Invalid remove_users format"
            raise ValueError(msg) from err

    def _add_users_to_item(
        self,
        item_uuid: str,
        item_type: ItemType,
        user_emails_str: str,
        request_user: User,
        message: str = "",
    ) -> tuple[list[str], list[str]]:
        """
        Add users to item sharing using UserSharePermission
        and return (shared_users, errors).

        Args:
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum
            user_emails_str: A comma-separated string of user emails to share with
            request_user: The user sharing the item
            message: A message to share with the users

        Returns:
            A tuple containing a list of shared users and a list of errors
        """
        if not user_emails_str:
            return [], []

        user_emails = [
            email.strip() for email in user_emails_str.split(",") if email.strip()
        ]

        shared_users = []
        errors = []

        for user_email in user_emails:
            try:
                user_to_share_with = User.objects.get(
                    email=user_email, is_approved=True
                )

                if user_to_share_with.id == request_user.id:
                    errors.append(
                        f"You cannot share a {item_type.lower()} with yourself ({user_email})"  # noqa: E501
                    )
                    continue

                # Check if already shared using the new model
                existing_permission = UserSharePermission.objects.filter(
                    item_uuid=item_uuid,
                    item_type=item_type,
                    owner=request_user,
                    shared_with=user_to_share_with,
                    is_deleted=False,
                ).first()

                if existing_permission:
                    if existing_permission.is_enabled:
                        errors.append(
                            f"{item_type.capitalize()} is already shared with {user_email}"  # noqa: E501
                        )
                        continue
                    # Re-enable the existing disabled permission
                    existing_permission.is_enabled = True
                    existing_permission.message = message
                    existing_permission.save()
                    shared_users.append(user_email)
                    continue

                # Create the share permission
                UserSharePermission.objects.create(
                    owner=request_user,
                    shared_with=user_to_share_with,
                    item_type=item_type,
                    item_uuid=item_uuid,
                    message=message,
                    is_enabled=True,
                )
                shared_users.append(user_email)

            except User.DoesNotExist:
                errors.append(f"User with email {user_email} not found or not approved")

        return shared_users, errors

    def _remove_users_from_item(
        self,
        item_uuid: str,
        item_type: str,
        users_to_remove: list[str],
        request_user: User,
    ) -> tuple[list[str], list[str]]:
        """
        Remove users from item sharing using UserSharePermission
        and return (removed_users, errors).

        Args:
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum
            users_to_remove: A list of user emails to remove
            request_user: The user removing the users

        Returns:
            A tuple containing a list of removed users and a list of errors
        """
        removed_users = []
        errors = []

        for user_email in users_to_remove:
            try:
                user_to_remove = User.objects.get(email=user_email)

                # Check if the user is actually shared with this item
                share_permission = UserSharePermission.objects.filter(
                    item_uuid=item_uuid,
                    item_type=item_type,
                    owner=request_user,
                    shared_with=user_to_remove,
                    is_deleted=False,
                ).first()

                if not share_permission or not share_permission.is_enabled:
                    errors.append(
                        f"{item_type.capitalize()} is not shared with user: {user_email}"  # noqa: E501
                    )
                    continue

                # Disable the share permission instead of soft deleting
                share_permission.is_enabled = False
                share_permission.save()
                removed_users.append(user_email)

            except User.DoesNotExist:
                errors.append(f"User with email {user_email} not found")

        return removed_users, errors

    def _build_response(
        self,
        item_type: str,
        shared_users: list[str],
        removed_users: list[str],
        errors: list[str],
    ) -> JsonResponse:
        """
        Build the response message based on the results.

        Args:
            item_type: The type of item to share from ItemType enum
            shared_users: A list of user emails that were shared
            removed_users: A list of user emails that were removed
            errors: A list of error messages

        Returns:
            A JSON response containing the response message
        """
        response_parts = []
        if shared_users:
            response_parts.append(
                f"{item_type.capitalize()} shared with {', '.join(shared_users)}"
            )
        if removed_users:
            response_parts.append(f"Removed access for {', '.join(removed_users)}")

        if response_parts and not errors:
            message = ". ".join(response_parts)
            return JsonResponse({"success": True, "message": message})
        if response_parts and errors:
            message = ". ".join(response_parts) + f". Issues: {'; '.join(errors)}"
            return JsonResponse({"success": True, "message": message})
        if not response_parts and errors:
            return JsonResponse({"error": "; ".join(errors)}, status=400)

        return JsonResponse({"success": True, "message": "No changes made"})

    def post(
        self,
        request: HttpRequest,
        item_uuid: str,
        item_type: ItemType,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Share an item with another user using the generalized permission system.

        Args:
            request: The HTTP request object
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum

        Returns:
            A JSON response containing the response message
        """
        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse({"error": "Invalid item type"}, status=400)

        # Verify the item exists and user owns it
        try:
            model_class = self.ITEM_MODELS[item_type]
            # Verify ownership
            model_class.objects.get(uuid=item_uuid, owner=request.user)
        except model_class.DoesNotExist:
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found"}, status=404
            )

        # Get the user emails from the form (comma-separated string)
        user_emails_str = request.POST.get("user-search", "").strip()

        # Parse users to remove
        try:
            users_to_remove = self._parse_remove_users(request)
        except ValueError:
            return JsonResponse({"error": "Invalid remove_users format"}, status=400)

        # Get optional message
        message = request.POST.get("notify_message", "").strip() or ""

        # Handle adding new users
        shared_users, add_errors = self._add_users_to_item(
            item_uuid, item_type, user_emails_str, request.user, message
        )

        # Handle removing users
        removed_users, remove_errors = self._remove_users_from_item(
            item_uuid, item_type, users_to_remove, request.user
        )

        # Combine all errors
        errors = add_errors + remove_errors

        # Notify shared users if requested
        notify = request.POST.get("notify_users") == "1"
        if shared_users and notify:
            # Use the generalized notification task for all item types
            notify_shared_users.delay(
                item_uuid, item_type, shared_users, notify=True, message=message
            )

        # Build and return response
        return self._build_response(item_type, shared_users, removed_users, errors)

    def delete(
        self,
        request: HttpRequest,
        item_uuid: str,
        item_type: str,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """Remove a user from item sharing using the generalized permission system.

        Args:
            request: The HTTP request object
            item_uuid: The UUID of the item to share
            item_type: The type of item to share from ItemType enum

        Returns:
            A JSON response containing the response message
        """
        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse({"error": "Invalid item type"}, status=400)

        # Verify the item exists and user owns it
        try:
            model_class = self.ITEM_MODELS[item_type]
            # Verify ownership
            model_class.objects.get(uuid=item_uuid, owner=request.user)
        except model_class.DoesNotExist:
            return JsonResponse(
                {"error": f"{item_type.capitalize()} not found"}, status=404
            )

        # Get the user email from the request
        user_email = request.POST.get("user_email", "").strip()

        if not user_email:
            return JsonResponse({"error": "User email is required"}, status=400)

        try:
            # Find the user to remove
            user_to_remove = User.objects.get(email=user_email)

            # Check if the user is actually shared with this item
            share_permission = UserSharePermission.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                owner=request.user,
                shared_with=user_to_remove,
                is_deleted=False,
            ).first()

            if not share_permission or not share_permission.is_enabled:
                return JsonResponse(
                    {
                        "error": f"User {user_email} is not shared with this {item_type.lower()}"  # noqa: E501
                    },
                    status=400,
                )

            # Disable the share permission instead of soft deleting
            share_permission.is_enabled = False
            share_permission.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Removed {user_email} from {item_type.lower()} sharing",
                }
            )

        except User.DoesNotExist:
            return JsonResponse(
                {"error": f"User with email {user_email} not found"}, status=400
            )


user_share_item_view = ShareItemView.as_view()


class ListFilesView(Auth0LoginRequiredMixin, View):
    template_name = "users/file_list.html"
    items_per_page = 25

    def get(self, request, *args, **kwargs) -> HttpResponse:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        # Get filter parameters
        search = request.GET.get("search", "")
        date_start = request.GET.get("date_start", "")
        date_end = request.GET.get("date_end", "")
        center_freq = request.GET.get("center_freq", "")
        bandwidth = request.GET.get("bandwidth", "")
        location = request.GET.get("location", "")

        # Base queryset
        files_qs = request.user.files.filter(is_deleted=False)

        # Apply search filter
        if search:
            files_qs = files_qs.filter(name__icontains=search)

        # Apply date range filter
        if date_start:
            files_qs = files_qs.filter(created_at__gte=date_start)
        if date_end:
            files_qs = files_qs.filter(created_at__lte=date_end)

        # Apply other filters
        if center_freq:
            files_qs = files_qs.filter(center_frequency=center_freq)
        if bandwidth:
            files_qs = files_qs.filter(bandwidth=bandwidth)
        if location:
            files_qs = files_qs.filter(location=location)

        # Handle sorting
        if sort_by:
            if sort_order == "desc":
                files_qs = files_qs.order_by(f"-{sort_by}")
            else:
                files_qs = files_qs.order_by(sort_by)

        # Paginate the results
        paginator = Paginator(files_qs, self.items_per_page)
        try:
            files_page = paginator.page(page)
        except (EmptyPage, PageNotAnInteger):
            files_page = paginator.page(1)

        return render(
            request,
            template_name=self.template_name,
            context={
                "files": files_page,
                "total_pages": paginator.num_pages,
                "current_page": page,
                "total_items": paginator.count,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )


user_file_list_view = ListFilesView.as_view()


class FileDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = File
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    template_name = "users/file_detail.html"

    def get_queryset(self) -> QuerySet[File]:
        return self.request.user.files.filter(is_deleted=False).all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target_file = cast("File", self.get_object())
        if target_file is None:
            return context
        serializer = FileGetSerializer(target_file)
        context["returning_page"] = self.request.GET.get("returning_page", default=1)
        context["file"] = serializer.data
        context["skip_fields"] = [
            "bucket_name",
            "deleted_at",
            "file",
            "is_deleted",
            "name",
        ]
        return context


user_file_detail_view = FileDetailView.as_view()


def _get_captures_for_template(
    captures: QuerySet[Capture],
    request: HttpRequest,
) -> list[dict[str, Any]]:
    """Get enhanced captures for the template."""
    enhanced_captures = []
    for capture in captures:
        # Use composite serialization to handle multi-channel captures properly
        capture_data = serialize_capture_or_composite(capture)

        # Add ownership flags for template display
        capture_data["is_owner"] = capture.owner == request.user
        capture_data["is_shared_with_me"] = capture.owner != request.user
        capture_data["owner_name"] = (
            capture.owner.name if capture.owner.name else "Owner"
        )
        capture_data["owner_email"] = capture.owner.email if capture.owner.email else ""

        # Add shared users data for share modal
        if capture.owner == request.user:
            # Get shared users using the new model
            shared_permissions = UserSharePermission.objects.filter(
                item_uuid=capture.uuid,
                item_type=ItemType.CAPTURE,
                owner=request.user,
                is_deleted=False,
                is_enabled=True,
            ).select_related("shared_with")
            shared_users = [
                {"name": perm.shared_with.name, "email": perm.shared_with.email}
                for perm in shared_permissions
            ]
            capture_data["shared_users"] = shared_users
        else:
            capture_data["shared_users"] = []

        enhanced_captures.append(capture_data)

    return enhanced_captures


class ListCapturesView(Auth0LoginRequiredMixin, View):
    """Handle HTML requests for the captures list page."""

    template_name = "users/file_list.html"
    default_items_per_page = 25
    max_items_per_page = 100

    def _extract_request_params(self, request):
        """Extract and return request parameters for HTML view."""
        return {
            "page": int(request.GET.get("page", 1)),
            "sort_by": request.GET.get("sort_by", "created_at"),
            "sort_order": request.GET.get("sort_order", "desc"),
            "search": request.GET.get("search", ""),
            "date_start": request.GET.get("date_start", ""),
            "date_end": request.GET.get("date_end", ""),
            "cap_type": request.GET.get("capture_type", ""),
            "min_freq": request.GET.get("min_freq", ""),
            "max_freq": request.GET.get("max_freq", ""),
            "items_per_page": min(
                int(request.GET.get("items_per_page", self.default_items_per_page)),
                self.max_items_per_page,
            ),
        }

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Handle HTML page requests for captures list."""
        # Extract request parameters
        params = self._extract_request_params(request)

        # Get captures owned by the user
        owned_captures = request.user.captures.filter(is_deleted=False)

        # Get captures shared with the user using the new UserSharePermission model
        shared_permissions = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
            is_enabled=True,
        ).values_list("item_uuid", flat=True)

        shared_captures = Capture.objects.filter(
            uuid__in=shared_permissions, is_deleted=False
        ).exclude(owner=request.user)

        # Combine owned and shared captures
        qs = owned_captures.union(shared_captures)

        # Apply all filters
        qs = _apply_basic_filters(
            qs=qs,
            search=params["search"],
            date_start=params["date_start"],
            date_end=params["date_end"],
            cap_type=params["cap_type"],
        )
        qs = _apply_frequency_filters(
            qs=qs, min_freq=params["min_freq"], max_freq=params["max_freq"]
        )

        qs = _apply_sorting(
            qs=qs, sort_by=params["sort_by"], sort_order=params["sort_order"]
        )

        # Use utility function to deduplicate composite captures
        unique_captures = deduplicate_composite_captures(list(qs))

        # Paginate the unique captures
        paginator = Paginator(unique_captures, params["items_per_page"])
        try:
            page_obj = paginator.page(params["page"])
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)

        # Update the page_obj with enhanced captures
        page_obj.object_list = _get_captures_for_template(page_obj, request)

        return render(
            request,
            self.template_name,
            {
                "captures": page_obj,
                "sort_by": params["sort_by"],
                "sort_order": params["sort_order"],
                "search": params["search"],
                "date_start": params["date_start"],
                "date_end": params["date_end"],
                "capture_type": params["cap_type"],
                "min_freq": params["min_freq"],
                "max_freq": params["max_freq"],
                "items_per_page": params["items_per_page"],
            },
        )


class CapturesAPIView(Auth0LoginRequiredMixin, View):
    """Handle API/JSON requests for captures search."""

    def _extract_request_params(self, request):
        """Extract and return request parameters for API view."""
        return {
            "sort_by": request.GET.get("sort_by", "created_at"),
            "sort_order": request.GET.get("sort_order", "desc"),
            "search": request.GET.get("search", ""),
            "date_start": request.GET.get("date_start", ""),
            "date_end": request.GET.get("date_end", ""),
            "cap_type": request.GET.get("capture_type", ""),
            "min_freq": request.GET.get("min_freq", ""),
            "max_freq": request.GET.get("max_freq", ""),
        }

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Handle AJAX requests for the captures API."""
        logger = logging.getLogger(__name__)

        try:
            # Extract and validate parameters
            params = self._extract_request_params(request)

            # Get captures owned by the user
            owned_captures = Capture.objects.filter(
                owner=request.user, is_deleted=False
            )

            # Get captures shared with the user using the new UserSharePermission model
            shared_permissions = UserSharePermission.objects.filter(
                shared_with=request.user,
                item_type=ItemType.CAPTURE,
                is_deleted=False,
                is_enabled=True,
            ).values_list("item_uuid", flat=True)

            shared_captures = Capture.objects.filter(
                uuid__in=shared_permissions, is_deleted=False
            ).exclude(owner=request.user)

            # Combine owned and shared captures
            qs = owned_captures.union(shared_captures)

            # Apply filters
            qs = _apply_basic_filters(
                qs=qs,
                search=params["search"],
                date_start=params["date_start"],
                date_end=params["date_end"],
                cap_type=params["cap_type"],
            )
            qs = _apply_frequency_filters(
                qs=qs, min_freq=params["min_freq"], max_freq=params["max_freq"]
            )

            qs = _apply_sorting(
                qs=qs, sort_by=params["sort_by"], sort_order=params["sort_order"]
            )

            # Use utility function to deduplicate composite captures
            unique_captures = deduplicate_composite_captures(list(qs))

            # Limit results for API performance
            captures_list = list(unique_captures[:25])

            captures_data = _get_captures_for_template(captures_list, request)

            response_data = {
                "captures": captures_data,
                "has_results": len(captures_data) > 0,
                "total_count": len(captures_data),
            }
            return JsonResponse(response_data)

        except (ValueError, TypeError) as e:
            logger.warning("Invalid parameter in captures API request: %s", e)
            return JsonResponse({"error": "Invalid search parameters"}, status=400)
        except DatabaseError:
            logger.exception("Database error in captures API request")
            return JsonResponse({"error": "Database error occurred"}, status=500)


user_capture_list_view = ListCapturesView.as_view()
user_captures_api_view = CapturesAPIView.as_view()


class GroupCapturesView(
    Auth0LoginRequiredMixin, FormSearchMixin, FileTreeMixin, TemplateView
):
    template_name = "users/group_captures.html"

    def search_captures(self, search_data, request) -> list[Capture]:
        """Override to only return captures owned by the user for dataset creation."""
        # Only get captures owned by the user (no shared captures)
        queryset = Capture.objects.filter(
            owner=request.user,
            is_deleted=False,
        )

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_dir = sanitize_path_rel_to_user(
            unsafe_path="/",
            request=self.request,
        )

        # Check if we're editing an existing dataset
        dataset_uuid = self.request.GET.get("dataset_uuid", None)
        existing_dataset = None
        if dataset_uuid:
            existing_dataset = get_object_or_404(
                Dataset, uuid=dataset_uuid, owner=self.request.user
            )

        # Get form
        if self.request.method == "POST":
            dataset_form = DatasetInfoForm(self.request.POST, user=self.request.user)
        else:
            initial_data = {}
            if existing_dataset:
                initial_data = {
                    "name": existing_dataset.name,
                    "description": existing_dataset.description,
                    "author": existing_dataset.authors[0],
                }
            dataset_form = DatasetInfoForm(user=self.request.user, initial=initial_data)

        selected_files, selected_files_details = self._get_file_context(
            base_dir=base_dir, existing_dataset=existing_dataset
        )
        selected_captures, selected_captures_details = self._get_capture_context(
            existing_dataset=existing_dataset
        )

        # Add to context
        context.update(
            {
                "dataset_form": dataset_form,
                "capture_search_form": CaptureSearchForm(),
                "file_search_form": FileSearchForm(user=self.request.user),
                "selected_captures": json.dumps(
                    selected_captures, cls=DjangoJSONEncoder
                ),
                "selected_files": json.dumps(selected_files, cls=DjangoJSONEncoder),
                "form": dataset_form,
                "existing_dataset": existing_dataset,
                "selected_captures_details_json": json.dumps(
                    selected_captures_details, cls=DjangoJSONEncoder
                ),
                "selected_files_details_json": json.dumps(
                    selected_files_details, cls=DjangoJSONEncoder
                ),
            }
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            try:
                if "search_captures" in request.GET:
                    form = CaptureSearchForm(request.GET)
                    if form.is_valid():
                        captures = self.search_captures(form.cleaned_data, request)
                        return JsonResponse(
                            self.get_paginated_response(captures, request)
                        )
                    return JsonResponse({"error": form.errors}, status=400)

                if "search_files" in request.GET:
                    base_dir = sanitize_path_rel_to_user(
                        unsafe_path="/",
                        request=self.request,
                    )
                    form = FileSearchForm(request.GET, user=self.request.user)
                    if form.is_valid():
                        files = self.search_files(form.cleaned_data, request)
                        return JsonResponse(
                            {
                                "tree": self._get_directory_tree(files, str(base_dir)),
                                "extension_choices": form.fields[
                                    "file_extension"
                                ].choices,
                                "search_values": {
                                    "file_name": form.cleaned_data.get("file_name", ""),
                                    "file_extension": form.cleaned_data.get(
                                        "file_extension", ""
                                    ),
                                    "directory": form.cleaned_data.get("directory", ""),
                                },
                            },
                        )
                    return JsonResponse({"error": form.errors}, status=400)
            except (OSError, DatabaseError) as e:
                return JsonResponse({"error": str(e)}, status=500)

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Handle dataset creation/update with selected captures and files."""
        try:
            # Validate form and get selected items
            validation_result = self._validate_dataset_form(request)
            if validation_result:
                return validation_result

            dataset_form, selected_captures, selected_files = (
                self._get_form_and_selections(request)
            )

            # Create or update dataset
            dataset = self._create_or_update_dataset(request, dataset_form)

            # Add captures to dataset
            capture_error = self._add_captures_to_dataset(
                dataset, selected_captures, request
            )
            if capture_error:
                return capture_error

            # Add files to dataset
            self._add_files_to_dataset(dataset, selected_files)

            # Return success response with redirect URL
            return JsonResponse(
                {"success": True, "redirect_url": reverse("users:dataset_list")},
            )

        except (DatabaseError, IntegrityError) as e:
            logger.exception("Database error in dataset creation")
            return JsonResponse(
                {"success": False, "errors": {"non_field_errors": [str(e)]}},
                status=500,
            )

    def _validate_dataset_form(self, request) -> JsonResponse | None:
        """Validate the dataset form and return error response if invalid."""
        dataset_form = DatasetInfoForm(request.POST, user=request.user)
        if not dataset_form.is_valid():
            return JsonResponse(
                {"success": False, "errors": dataset_form.errors},
                status=400,
            )

        # Get selected captures and files from hidden fields
        selected_captures = request.POST.get("selected_captures", "").split(",")
        selected_files = request.POST.get("selected_files", "").split(",")

        # Validate that at least one capture or file is selected
        if not selected_captures[0] and not selected_files[0]:
            return JsonResponse(
                {
                    "success": False,
                    "errors": {
                        "non_field_errors": [
                            "Please select at least one capture or file.",
                        ],
                    },
                },
                status=400,
            )

        return None

    def _get_form_and_selections(
        self, request
    ) -> tuple[DatasetInfoForm, list[str], list[str]]:
        """Get the form and selected items from the request."""
        dataset_form = DatasetInfoForm(request.POST, user=request.user)
        dataset_form.is_valid()  # We already validated above

        selected_captures = request.POST.get("selected_captures", "").split(",")
        selected_files = request.POST.get("selected_files", "").split(",")

        return dataset_form, selected_captures, selected_files

    def _create_or_update_dataset(self, request, dataset_form) -> Dataset:
        """Create a new dataset or update an existing one."""
        dataset_uuid = request.GET.get("dataset_uuid", None)

        if dataset_uuid:
            dataset = get_object_or_404(Dataset, uuid=dataset_uuid, owner=request.user)
            dataset.name = dataset_form.cleaned_data["name"]
            dataset.description = dataset_form.cleaned_data["description"]
            dataset.authors = [dataset_form.cleaned_data["author"]]
            dataset.save()

            # Clear existing relationships
            dataset.captures.clear()
            dataset.files.clear()
        else:
            # Create new dataset
            dataset = Dataset.objects.create(
                name=dataset_form.cleaned_data["name"],
                description=dataset_form.cleaned_data["description"],
                authors=[dataset_form.cleaned_data["author"]],
                owner=request.user,
            )

        return dataset

    def _add_captures_to_dataset(
        self, dataset: Dataset, selected_captures: list[str], request
    ) -> JsonResponse | None:
        """Add selected captures to the dataset."""
        if not selected_captures[0]:
            return None

        for capture_id in selected_captures:
            if not capture_id:
                continue
            try:
                # Only allow adding captures owned by the user
                capture = Capture.objects.get(
                    uuid=capture_id, owner=request.user, is_deleted=False
                )
                if capture.is_multi_channel:
                    # Add all captures in this composite
                    all_captures = Capture.objects.filter(
                        top_level_dir=capture.top_level_dir,
                        owner=request.user,
                        is_deleted=False,
                    )
                    dataset.captures.add(*all_captures)
                else:
                    dataset.captures.add(capture)
            except Capture.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "errors": {
                            "non_field_errors": [
                                f"Capture {capture_id} not found or you don't have "
                                "permission to add it to a dataset.",
                            ],
                        },
                    },
                    status=400,
                )

        return None

    def _add_files_to_dataset(
        self, dataset: Dataset, selected_files: list[str]
    ) -> None:
        """Add selected files to the dataset."""
        if selected_files[0]:
            files = File.objects.filter(uuid__in=selected_files)
            dataset.files.add(*files)

    def _get_file_context(
        self,
        base_dir: Path | None = None,
        existing_dataset: Dataset | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        selected_files: list[dict[str, Any]] = []
        selected_files_details: dict[str, Any] = {}
        if not existing_dataset:
            return selected_files, selected_files_details

        files_queryset = existing_dataset.files.filter(
            is_deleted=False,
            owner=self.request.user,
        )

        # Prepare file details for JavaScript
        for selected_file in files_queryset:
            rel_path = (
                f"{selected_file.directory.replace(str(base_dir), '')}"
                if base_dir
                else None
            )
            selected_files.append(self.serialize_item(selected_file, rel_path))

            selected_files_details[str(selected_file.uuid)] = self.serialize_item(
                selected_file,
                rel_path,
            )

        return selected_files, selected_files_details

    def _get_capture_context(
        self, existing_dataset: Dataset | None = None
    ) -> tuple[list[str], dict[str, Any]]:
        selected_captures: list[str] = []
        selected_captures_details: dict[str, Any] = {}
        composite_capture_dirs: set[str] = set()
        if existing_dataset:
            captures_queryset = existing_dataset.captures.filter(
                is_deleted=False,
                owner=self.request.user,
            )

            # Only include one composite per group
            for capture in captures_queryset.order_by("-created_at"):
                if capture.is_multi_channel:
                    if capture.top_level_dir not in composite_capture_dirs:
                        capture_dict = self.serialize_item(capture)
                        capture_uuid = str(capture_dict["id"])
                        selected_captures.append(capture_uuid)
                        selected_captures_details[capture_uuid] = capture_dict
                        composite_capture_dirs.add(capture.top_level_dir)
                else:
                    capture_dict = self.serialize_item(capture)
                    capture_uuid = str(capture_dict["id"])
                    selected_captures.append(capture_uuid)
                    selected_captures_details[capture_uuid] = capture_dict

        return selected_captures, selected_captures_details


user_group_captures_view = GroupCapturesView.as_view()


class ListDatasetsView(Auth0LoginRequiredMixin, View):
    template_name = "users/dataset_list.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        # Get sort parameters from URL
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        # Define allowed sort fields
        allowed_sort_fields = {"name", "created_at", "updated_at", "authors"}

        # Apply sorting
        if sort_by in allowed_sort_fields:
            order_prefix = "-" if sort_order == "desc" else ""
            order_by = f"{order_prefix}{sort_by}"
        else:
            # Default sorting
            order_by = "-created_at"

        # Get datasets owned by the user
        owned_datasets = (
            request.user.datasets.filter(is_deleted=False).all().order_by(order_by)
        )

        # Get datasets shared with the user using the new UserSharePermission model
        shared_permissions = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.DATASET,
            is_deleted=False,
            is_enabled=True,
        ).select_related("owner")

        shared_dataset_uuids = [perm.item_uuid for perm in shared_permissions]
        shared_datasets = (
            Dataset.objects.filter(uuid__in=shared_dataset_uuids, is_deleted=False)
            .exclude(owner=request.user)
            .order_by(order_by)
        )

        # Prepare datasets with shared users and flags
        datasets_with_shared_users = []
        for dataset in owned_datasets:
            dataset_data = DatasetGetSerializer(dataset).data
            # Get shared users using the new model
            shared_permissions = UserSharePermission.objects.filter(
                item_uuid=dataset.uuid,
                item_type=ItemType.DATASET,
                owner=request.user,
                is_deleted=False,
                is_enabled=True,
            ).select_related("shared_with")
            shared_users = [
                {"name": perm.shared_with.name, "email": perm.shared_with.email}
                for perm in shared_permissions
            ]
            dataset_data["shared_users"] = shared_users
            dataset_data["is_owner"] = True
            dataset_data["is_shared_with_me"] = False
            dataset_data["owner_name"] = (
                dataset.owner.name if dataset.owner.name else "Owner"
            )
            dataset_data["owner_email"] = (
                dataset.owner.email if dataset.owner.email else ""
            )
            datasets_with_shared_users.append(dataset_data)

        for dataset in shared_datasets:
            dataset_data = DatasetGetSerializer(dataset).data
            # Get shared users using the new model
            shared_permissions = UserSharePermission.objects.filter(
                item_uuid=dataset.uuid,
                item_type=ItemType.DATASET,
                owner=dataset.owner,
                is_deleted=False,
                is_enabled=True,
            ).select_related("shared_with")
            shared_users = [
                {"name": perm.shared_with.name, "email": perm.shared_with.email}
                for perm in shared_permissions
            ]
            dataset_data["shared_users"] = shared_users
            dataset_data["is_owner"] = False
            dataset_data["is_shared_with_me"] = True
            dataset_data["owner_name"] = (
                dataset.owner.name if dataset.owner.name else "Owner"
            )
            dataset_data["owner_email"] = (
                dataset.owner.email if dataset.owner.email else ""
            )
            datasets_with_shared_users.append(dataset_data)

        paginator = Paginator(datasets_with_shared_users, per_page=15)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        return render(
            request,
            template_name=self.template_name,
            context={
                "page_obj": page_obj,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )


def _apply_basic_filters(
    qs: QuerySet[Capture],
    search: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    cap_type: str | None = None,
) -> QuerySet[Capture]:
    """Apply basic filters: search, date range, and capture type."""
    if search:
        # First get the base queryset with direct field matches
        base_filter = (
            Q(channel__icontains=search)
            | Q(index_name__icontains=search)
            | Q(capture_type__icontains=search)
            | Q(uuid__icontains=search)
        )

        # Then add any captures where the display value matches
        display_matches = [
            capture.pk
            for capture in qs
            if search.lower() in capture.get_capture_type_display().lower()
        ]

        if display_matches:
            base_filter |= Q(pk__in=display_matches)

        qs = qs.filter(base_filter)

    if date_start:
        qs = qs.filter(created_at__gte=date_start)
    if date_end:
        qs = qs.filter(created_at__lte=date_end)
    if cap_type:
        qs = qs.filter(capture_type=cap_type)

    return qs


def _apply_frequency_filters(
    qs: QuerySet[Capture], min_freq: str, max_freq: str
) -> QuerySet[Capture]:
    """Apply center frequency range filters using OpenSearch data (fast!)."""
    # Only apply frequency filtering if meaningful parameters are provided
    min_freq_str = str(min_freq).strip() if min_freq else ""
    max_freq_str = str(max_freq).strip() if max_freq else ""

    # If both frequency parameters are empty, don't apply frequency filtering
    if not min_freq_str and not max_freq_str:
        return qs

    # Convert to float, skip filtering if invalid values
    try:
        min_freq_val = float(min_freq_str) if min_freq_str else None
    except ValueError:
        min_freq_val = None

    try:
        max_freq_val = float(max_freq_str) if max_freq_str else None
    except ValueError:
        max_freq_val = None

    # If both conversions failed, don't apply frequency filtering
    if min_freq_val is None and max_freq_val is None:
        return qs

    try:
        # Bulk load frequency metadata for all captures
        frequency_data = Capture.bulk_load_frequency_metadata(qs)

        filtered_uuids = []
        for capture in qs:
            capture_uuid = str(capture.uuid)
            freq_info = frequency_data.get(capture_uuid, {})
            center_freq_hz = freq_info.get("center_frequency")

            if center_freq_hz is None:
                # If no frequency data and filters are active, exclude it
                continue  # Skip this capture

            center_freq_ghz = center_freq_hz / 1e9

            # Apply frequency range filter
            if min_freq_val is not None and center_freq_ghz < min_freq_val:
                continue  # Skip this capture
            if max_freq_val is not None and center_freq_ghz > max_freq_val:
                continue  # Skip this capture

            # Capture passed all filters
            filtered_uuids.append(capture.uuid)

        return qs.filter(uuid__in=filtered_uuids)

    except Exception:
        logger.exception("Error applying frequency filters")
        return qs  # Return unfiltered queryset on error


def _apply_sorting(
    qs: QuerySet[Capture],
    sort_by: str,
    sort_order: str = "desc",
):
    """Apply sorting to the queryset."""
    # Define allowed sort fields (actual database fields only)
    allowed_sort_fields = {
        "uuid",
        "created_at",
        "updated_at",
        "deleted_at",
        "is_deleted",
        "is_public",
        "channel",
        "scan_group",
        "capture_type",
        "top_level_dir",
        "index_name",
        "owner",
        "origin",
        "dataset",
    }

    # Handle computed properties with meaningful fallbacks
    computed_field_fallbacks = {
        # Could be enhanced with OpenSearch sorting later
        "center_frequency_ghz": "created_at",
        "sample_rate_mhz": "created_at",
    }

    # Check if it's a computed field first
    if sort_by in computed_field_fallbacks:
        # For now, fall back to a meaningful sort field
        # In the future, this could be enhanced to sort by OpenSearch data
        fallback_field = computed_field_fallbacks[sort_by]
        if sort_order == "desc":
            return qs.order_by(f"-{fallback_field}")
        return qs.order_by(fallback_field)

    # Only apply sorting if the field is allowed
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            return qs.order_by(f"-{sort_by}")
        return qs.order_by(sort_by)

    # Default sorting if field is not recognized
    return qs.order_by("-created_at")


user_dataset_list_view = ListDatasetsView.as_view()


class TemporaryZipDownloadView(Auth0LoginRequiredMixin, View):
    """View to display a temporary zip file download page and serve the file."""

    template_name = "users/temporary_zip_download.html"

    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Display download page for a temporary zip file or serve the file."""
        zip_uuid = kwargs.get("uuid")
        if not zip_uuid:
            logger.warning("No UUID provided in temporary zip download request")
            error_msg = "UUID is required"
            raise Http404(error_msg)

        # Check if this is a download request (automatic download from JavaScript)
        if request.GET.get("download") == "true":
            return self._serve_file_download(zip_uuid, request.user)

        try:
            # Get the temporary zip file
            temp_zip = get_object_or_404(
                TemporaryZipFile,
                uuid=zip_uuid,
                owner=request.user,
            )

            # Check if file still exists on disk
            file_exists = (
                Path(temp_zip.file_path).exists() if temp_zip.file_path else False
            )

            # Determine status and prepare context
            if temp_zip.is_deleted:
                status = "deleted"
                message = "This file has been deleted and is no longer available."
            elif temp_zip.is_expired:
                status = "expired"
                message = "This download link has expired and is no longer available."
            elif not file_exists:
                status = "file_missing"
                message = "The file was not found on the server."
            else:
                status = "available"
                message = None

            # Convert UTC expiry date to user's timezone for display
            expires_at_local = (
                timezone.localtime(temp_zip.expires_at) if temp_zip.expires_at else None
            )

            context = {
                "temp_zip": temp_zip,
                "status": status,
                "message": message,
                "file_exists": file_exists,
                "expires_at_local": expires_at_local,
            }

            return render(request, template_name=self.template_name, context=context)

        except TemporaryZipFile.DoesNotExist:
            logger.warning(
                "Temporary zip file not found: %s for user: %s",
                zip_uuid,
                request.user.id,
            )
            error_msg = "File not found."
            raise Http404(error_msg) from None

    def _serve_file_download(self, zip_uuid: str, user) -> HttpResponse:
        """Serve the zip file for download."""
        try:
            # Get the temporary zip file
            temp_zip = get_object_or_404(
                TemporaryZipFile,
                uuid=zip_uuid,
                owner=user,
            )

            logger.info("Found temporary zip file: %s", temp_zip.filename)

            file_path = Path(temp_zip.file_path)
            if not file_path.exists():
                logger.warning("File not found on disk: %s", temp_zip.file_path)
                return JsonResponse(
                    {"error": "The file was not found on the server."}, status=404
                )

            file_size = file_path.stat().st_size

            with file_path.open("rb") as f:
                file_content = f.read()
                response = HttpResponse(file_content, content_type="application/zip")
                response["Content-Disposition"] = (
                    f'attachment; filename="{temp_zip.filename}"'
                )
                response["Content-Length"] = file_size

                # Mark the file as downloaded
                temp_zip.mark_downloaded()

                return response

        except OSError:
            logger.exception("Error reading file: %s", temp_zip.file_path)
            return JsonResponse({"error": "Error reading file."}, status=500)


user_temporary_zip_download_view = TemporaryZipDownloadView.as_view()


class DownloadItemView(Auth0LoginRequiredMixin, View):
    """
    Unified view to handle item download requests for both datasets and captures.

    This view follows the same pattern as ShareItemView, accepting item_type
    as a URL parameter and handling the download logic generically.
    """

    # Map item types to their corresponding models
    ITEM_MODELS = {
        ItemType.DATASET: Dataset,
        ItemType.CAPTURE: Capture,
    }

    def post(
        self,
        request: HttpRequest,
        item_uuid: str,
        item_type: ItemType,
        *args: Any,
        **kwargs: Any,
    ) -> HttpResponse:
        """
        Handle item download request.

        Args:
            request: The HTTP request object
            item_uuid: The UUID of the item to download
            item_type: The type of item to download from ItemType enum

        Returns:
            A JSON response containing the download status
        """
        # Validate item type
        if item_type not in self.ITEM_MODELS:
            return JsonResponse(
                {"success": False, "message": "Invalid item type"},
                status=400,
            )

        # Check if user has access to the item (either as owner or shared user)
        if not user_has_access_to_item(request.user, item_uuid, item_type):
            return JsonResponse(
                {
                    "success": False,
                    "message": f"{item_type.capitalize()} not found or access denied",
                    "item_uuid": item_uuid,
                },
                status=404,
            )

        # Get the item
        try:
            model_class = self.ITEM_MODELS[item_type]
            item = get_object_or_404(
                model_class,
                uuid=item_uuid,
                is_deleted=False,
            )
        except model_class.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"{item_type.capitalize()} not found",
                    "item_uuid": item_uuid,
                },
                status=404,
            )

        # Get user email
        user_email = request.user.email
        if not user_email:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"User email is required for sending {item_type} files.",
                },
                status=400,
            )

        # Check if a user already has a task running
        task_name = f"{item_type}_download"
        if is_user_locked(str(request.user.id), task_name):
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        f"You already have a {item_type} download in progress. "
                        "Please wait for it to complete."
                    ),
                },
                status=400,
            )

        # Trigger the unified Celery task
        task = send_item_files_email.delay(
            str(item.uuid),
            str(request.user.id),
            item_type,
        )

        return JsonResponse(
            {
                "success": True,
                "message": (
                    f"{item_type.capitalize()} download request accepted. "
                    "You will receive an email with the files shortly."
                ),
                "task_id": task.id,
                "item_name": getattr(item, "name", str(item)),
                "user_email": user_email,
            },
            status=202,
        )


user_download_item_view = DownloadItemView.as_view()


class DatasetDetailsView(Auth0LoginRequiredMixin, FileTreeMixin, View):
    """View to handle dataset details modal requests."""

    def _get_dataset_files(self, dataset: Dataset) -> QuerySet[File]:
        """Get all files associated with a dataset, including files from linked captures."""
        # Get files directly associated with the dataset
        dataset_files = dataset.files.filter(is_deleted=False)

        # Get files from linked captures
        capture_file_ids = []
        dataset_captures = dataset.captures.filter(is_deleted=False)
        for capture in dataset_captures:
            capture_file_ids.extend(
                capture.files.filter(is_deleted=False).values_list("uuid", flat=True)
            )

        # Combine using Q objects to avoid union issues
        from django.db.models import Q

        combined_files = File.objects.filter(
            Q(uuid__in=dataset_files.values_list("uuid", flat=True))
            | Q(uuid__in=capture_file_ids)
        ).distinct()

        return combined_files

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Get dataset details and files for the modal."""
        dataset_uuid = request.GET.get("dataset_uuid")

        if not dataset_uuid:
            return JsonResponse({"error": "Dataset UUID is required"}, status=400)

        # Check if user has access to the dataset
        if not user_has_access_to_item(request.user, dataset_uuid, ItemType.DATASET):
            return JsonResponse(
                {"error": "Dataset not found or access denied"}, status=404
            )

        try:
            dataset = get_object_or_404(Dataset, uuid=dataset_uuid, is_deleted=False)

            # Get dataset information
            dataset_data = DatasetGetSerializer(dataset).data

            # Get all files associated with the dataset
            files_queryset = self._get_dataset_files(dataset)

            # Calculate statistics
            total_files = files_queryset.count()
            captures_count = files_queryset.filter(capture__isnull=False).count()
            artifacts_count = files_queryset.filter(capture__isnull=True).count()
            total_size = files_queryset.aggregate(total=Sum("size"))["total"] or 0

            # Use the same base directory logic as GroupCapturesView
            base_dir = sanitize_path_rel_to_user(
                unsafe_path="/",
                request=request,
            )
            tree_data = self._get_directory_tree(files_queryset, str(base_dir))

            response_data = {
                "dataset": dataset_data,
                "tree": tree_data,
                "statistics": {
                    "total_files": total_files,
                    "captures": captures_count,
                    "artifacts": artifacts_count,
                    "total_size": total_size,
                },
            }

            return JsonResponse(response_data)

        except Dataset.DoesNotExist:
            return JsonResponse({"error": "Dataset not found"}, status=404)
        except Exception:
            logger.exception("Error retrieving dataset details")
            return JsonResponse({"error": "Internal server error"}, status=500)


user_dataset_details_view = DatasetDetailsView.as_view()
