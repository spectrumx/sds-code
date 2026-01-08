from typing import Any

from django.core.paginator import EmptyPage
from django.core.paginator import Page
from django.core.paginator import PageNotAnInteger
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Q
from django.db.models.query import QuerySet
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from loguru import logger as log

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import Keyword
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.models import User
from sds_gateway.users.utils import deduplicate_composite_captures
from sds_gateway.visualizations.config import get_visualization_compatibility

# API performance constant: maximum number of captures to return in API responses
API_CAPTURES_LIMIT = 25


def _get_captures_for_template(
    captures: QuerySet[Capture] | list[Capture] | Page[Capture],
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

        # Add the original model instance for template use
        capture_data["capture"] = capture

        # Add shared users data for share modal
        if user_has_access_to_item(request.user, capture.uuid, ItemType.CAPTURE):
            # Get shared users and groups using the new model
            shared_permissions = (
                UserSharePermission.objects.filter(
                    item_uuid=capture.uuid,
                    item_type=ItemType.CAPTURE,
                    is_deleted=False,
                    is_enabled=True,
                )
                .select_related("shared_with")
                .prefetch_related("share_groups__members")
            )

            shared_users = []
            group_permissions = {}

            for perm in shared_permissions:
                if perm.share_groups.exists():
                    # Group member - collect by group
                    for group in perm.share_groups.all():
                        group_uuid = str(group.uuid)
                        if group_uuid not in group_permissions:
                            group_permissions[group_uuid] = {
                                "name": group.name,
                                "email": f"group:{group_uuid}",
                                "type": "group",
                                "members": [],
                                "permission_level": perm.permission_level,
                                "owner": group.owner.name,
                                "owner_email": group.owner.email,
                                "is_group_owner": group.owner == request.user,
                            }
                        group_permissions[group_uuid]["members"].append(
                            {
                                "name": perm.shared_with.name,
                                "email": perm.shared_with.email,
                            }
                        )
                else:
                    # Individual user
                    shared_users.append(
                        {
                            "name": perm.shared_with.name,
                            "email": perm.shared_with.email,
                            "type": "user",
                            "permission_level": perm.permission_level,
                        }
                    )

            # Add groups with member counts
            for group_data in group_permissions.values():
                group_data["member_count"] = len(group_data["members"])
                shared_users.append(group_data)
            capture_data["shared_users"] = shared_users
        else:
            capture_data["shared_users"] = []

        enhanced_captures.append(capture_data)

    return enhanced_captures


def _get_user_captures_querysets(
    user: User,
) -> tuple[QuerySet[Capture], QuerySet[Capture]]:
    """Get owned and shared capture querysets for a user."""
    # Get captures owned by the user
    owned_captures = user.captures.filter(is_deleted=False)

    # Get captures shared with the user using the new UserSharePermission model
    shared_permissions = UserSharePermission.objects.filter(
        shared_with=user,
        item_type=ItemType.CAPTURE,
        is_deleted=False,
        is_enabled=True,
    ).values_list("item_uuid", flat=True)

    shared_captures = Capture.objects.filter(
        uuid__in=shared_permissions, is_deleted=False
    ).exclude(owner=user)

    return owned_captures, shared_captures


def _apply_frequency_filters_to_list(  # noqa: C901
    captures_list: list[Capture],
    min_freq: str | float | None,
    max_freq: str | float | None,
) -> list[Capture]:
    """Apply frequency filters to a list of captures."""
    if not captures_list or (not min_freq and not max_freq):
        return captures_list

    try:
        # Convert list to queryset for bulk frequency loading
        temp_qs = Capture.objects.filter(uuid__in=[c.uuid for c in captures_list])
        # Bulk load frequency metadata
        frequency_data = Capture.bulk_load_frequency_metadata(temp_qs)

        # Parse frequency values
        min_freq_str = str(min_freq).strip() if min_freq else ""
        max_freq_str = str(max_freq).strip() if max_freq else ""

        try:
            min_freq_val = float(min_freq_str) if min_freq_str else None
        except ValueError:
            min_freq_val = None

        try:
            max_freq_val = float(max_freq_str) if max_freq_str else None
        except ValueError:
            max_freq_val = None

        if min_freq_val is None and max_freq_val is None:
            return captures_list

        # Filter captures by frequency range
        filtered_captures: list[Capture] = []
        for capture in captures_list:
            capture_uuid = str(capture.uuid)
            freq_info = frequency_data.get(capture_uuid, {})
            center_freq_hz = freq_info.get("center_frequency")

            if center_freq_hz is None:
                continue

            try:
                center_freq_hz = float(center_freq_hz)
            except (ValueError, TypeError):
                continue

            center_freq_ghz = center_freq_hz / 1e9

            if min_freq_val is not None and center_freq_ghz < min_freq_val:
                continue
            if max_freq_val is not None and center_freq_ghz > max_freq_val:
                continue

            filtered_captures.append(capture)

    except (DatabaseError, AttributeError) as e:
        log.warning(f"Error in frequency filtering: {e}", exc_info=True)
        # Continue with unfiltered list on error
        return captures_list

    else:
        return filtered_captures


def _apply_sorting_to_list(
    captures_list: list[Capture],
    sort_by: str,
    sort_order: str,
) -> list[Capture]:
    """Apply sorting to a list of captures."""
    if not sort_by or not captures_list:
        return captures_list

    reverse = sort_order == "desc"
    try:
        allowed_sort_fields: set[str] = {
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
        }
        if sort_by in allowed_sort_fields:
            captures_list = sorted(
                captures_list,
                key=lambda c: (
                    getattr(c, sort_by, None) is None,
                    getattr(c, sort_by, ""),
                ),
                reverse=reverse,
            )
    except (TypeError, AttributeError) as e:
        log.warning(f"Sorting failed: {e}")

    return captures_list


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
            Q(name__icontains=search)
            | Q(channel__icontains=search)
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


def _get_filtered_and_sorted_captures(
    user: User,
    params: dict[str, Any],
    limit: int | None = None,
) -> list[Capture]:
    """
    Get filtered and sorted captures for a user based on parameters.

    Args:
        user:   The user to get captures for
        params: Dictionary of filter parameters
        limit:  Optional limit to apply to each queryset before union

    Returns:
        List of filtered, sorted, and deduplicated Capture objects
    """
    # Get owned and shared captures
    owned_captures, shared_captures = _get_user_captures_querysets(user)

    # Apply basic filters to each queryset
    owned_captures = _apply_basic_filters(
        qs=owned_captures,
        search=params["search"],
        date_start=params["date_start"],
        date_end=params["date_end"],
        cap_type=params["cap_type"],
    )
    shared_captures = _apply_basic_filters(
        qs=shared_captures,
        search=params["search"],
        date_start=params["date_start"],
        date_end=params["date_end"],
        cap_type=params["cap_type"],
    )

    # Apply limit to each queryset before union to reduce memory usage
    if limit is not None:
        # Add buffer to ensure we have enough after filtering/deduplication
        queryset_limit = int(limit * 1.5)  # 50% buffer
        owned_captures = owned_captures[:queryset_limit]
        shared_captures = shared_captures[:queryset_limit]

    # Union the querysets (all basic filters already applied)
    qs = owned_captures.union(shared_captures)

    # Convert to list (single DB query for union)
    captures_list: list[Capture] = list(qs)

    # Apply frequency filters to the combined list
    captures_list = _apply_frequency_filters_to_list(
        captures_list, params["min_freq"], params["max_freq"]
    )

    # Apply sorting to the combined list (union doesn't preserve order)
    captures_list = _apply_sorting_to_list(
        captures_list, params["sort_by"], params["sort_order"]
    )

    # Deduplicate composite captures
    unique_captures = deduplicate_composite_captures(captures_list)

    # Apply final limit if specified (after deduplication)
    if limit is not None:
        unique_captures = unique_captures[:limit]

    return unique_captures


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

        # Get filtered and sorted captures
        unique_captures = _get_filtered_and_sorted_captures(request.user, params)

        # Paginate the unique captures
        paginator = Paginator(unique_captures, params["items_per_page"])
        try:
            page_obj = paginator.page(params["page"])
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)

        # Update the page_obj with enhanced captures
        page_obj.object_list = _get_captures_for_template(page_obj, request)

        # Get visualization compatibility data
        visualization_compatibility = get_visualization_compatibility()

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
                "visualization_compatibility": visualization_compatibility,
            },
        )


user_capture_list_view = ListCapturesView.as_view()


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

        try:
            # Extract and validate parameters
            params = self._extract_request_params(request)

            # Get filtered and sorted captures with API limit applied before union
            captures_list = _get_filtered_and_sorted_captures(
                request.user, params, limit=API_CAPTURES_LIMIT
            )

            try:
                captures_data = _get_captures_for_template(captures_list, request)
                # remove the Capture model instance from each
                #   capture_data dict for JSON serialization
                for capture_data in captures_data:
                    capture_data.pop("capture", None)
            except Exception as e:
                log.exception(f"Error in _get_captures_for_template: {e}")
                msg = f"Error getting capture data: {e!s}"
                raise ValueError(msg) from e

            response_data = {
                "captures": captures_data,
                "has_results": len(captures_data) > 0,
                "total_count": len(captures_data),
            }
            return JsonResponse(response_data)

        except (ValueError, TypeError) as e:
            error_msg = str(e)
            log.warning(
                f"Invalid parameter in captures API request: {error_msg}",
                exc_info=True,
            )
            return JsonResponse(
                {"error": f"Invalid search parameters: {error_msg}"},
                status=400,
            )
        except DatabaseError:
            log.exception("Database error in captures API request")
            return JsonResponse({"error": "Database error occurred"}, status=500)


user_captures_api_view = CapturesAPIView.as_view()


class KeywordAutocompleteAPIView(Auth0LoginRequiredMixin, View):
    """Handle API requests for keyword autocomplete suggestions."""

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """
        Return keyword suggestions based on search query.

        Returns up to 10 unique keyword suggestions that match the query
        anywhere in the keyword.
        """
        query = request.GET.get("q", "").strip()

        if not query:
            return JsonResponse({"suggestions": []})

        try:
            # Search for keywords that contain the query anywhere (case-insensitive)
            keywords = Keyword.objects.filter(
                name__icontains=query,
                is_deleted=False,
            ).values_list("name", flat=True)[:10]

            return JsonResponse({"suggestions": list(keywords)})

        except DatabaseError:
            log.exception("Database error in keyword autocomplete")
            return JsonResponse({"error": "Database error occurred"}, status=500)


keyword_autocomplete_api_view = KeywordAutocompleteAPIView.as_view()
