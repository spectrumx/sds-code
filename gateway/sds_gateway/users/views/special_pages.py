from uuid import UUID

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View
from loguru import logger as log

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.models import UserAPIKey

from .api_keys import MAX_API_KEY_COUNT
from .api_keys import get_active_api_key_count


class SPXDACDatasetAltView(Auth0LoginRequiredMixin, View):
    """View for the SpectrumX Student Data Competition page."""

    template_name = "pages/spx_dac_dataset_alt.html"

    def get(self, request, *args, **kwargs):
        """Display the student data competition page and automatically share dataset."""
        dataset_id = settings.SPX_DAC_DATASET_ID
        if not dataset_id:
            log.warning("SPX_DAC_DATASET_ID not configured")
        else:
            try:
                dataset_uuid = UUID(dataset_id)
                # Get the dataset to find its owner
                try:
                    dataset = Dataset.objects.get(uuid=dataset_uuid, is_deleted=False)
                except Dataset.DoesNotExist:
                    log.warning(f"SpX-DAC dataset {dataset_id} not found")
                    dataset = None

                # Check if user is already the owner
                if dataset and dataset.owner != request.user:
                    # Check if permission already exists
                    existing_permission = UserSharePermission.objects.filter(
                        owner=dataset.owner,
                        shared_with=request.user,
                        item_type=ItemType.DATASET,
                        item_uuid=dataset_uuid,
                        is_deleted=False,
                    ).first()

                    if not existing_permission:
                        # Create share permission with VIEWER role
                        UserSharePermission.objects.create(
                            owner=dataset.owner,
                            shared_with=request.user,
                            item_type=ItemType.DATASET,
                            item_uuid=dataset_uuid,
                            message="Automatically shared for NSF SpectrumX "
                            "Data and Algorithm Competition (SpX-DAC)",
                            permission_level=PermissionLevel.VIEWER,
                            is_enabled=True,
                        )
                        log.info(
                            "Automatically shared SpX-DAC dataset "
                            f"with user {request.user.email}"
                        )
                    elif not existing_permission.is_enabled:
                        # Re-enable if it was previously disabled
                        existing_permission.is_enabled = True
                        existing_permission.save()
                        log.info(
                            "Re-enabled SpX-DAC dataset "
                            f"share for user {request.user.email}"
                        )
            except ValueError as e:
                log.warning(f"Invalid SpX-DAC dataset ID format: {e}")

        context = {
            "s3_bucket_url": settings.SPX_DAC_DATASET_S3_URL,
            "dataset_id": dataset_id or "458c3f72-8d7e-49cc-9be3-ed0b0cd7e03d",
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handle API key generation via AJAX."""
        # Check if user has reached the maximum number of active API keys
        api_keys = UserAPIKey.objects.filter(user=request.user).exclude(
            source=KeySources.SVIBackend
        )
        active_api_key_count = get_active_api_key_count(api_keys)
        if active_api_key_count >= MAX_API_KEY_COUNT:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You have reached the maximum number of API keys "
                    f"({MAX_API_KEY_COUNT}). Please revoke an existing key before "
                    "creating a new one.",
                },
                status=400,
            )

        # Get the name from the form (optional)
        api_key_name = request.POST.get("api_key_name", "SpX-DAC Competition")
        api_key_description = request.POST.get(
            "api_key_description",
            "Generated for NSF SpectrumX Data and Algorithm Competition (SpX-DAC)",
        )

        try:
            # Create an API key for the user
            _, raw_key = UserAPIKey.objects.create_key(
                name=api_key_name,
                description=api_key_description,
                user=request.user,
                source=KeySources.SDSWebUI,
                expiry_date=None,
            )
            return JsonResponse({"success": True, "api_key": raw_key})
        except Exception:  # noqa: BLE001
            log.exception("Error generating API key for student competition")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Failed to generate API key. Please try again.",
                },
                status=500,
            )


spx_dac_dataset_alt_view = SPXDACDatasetAltView.as_view()
