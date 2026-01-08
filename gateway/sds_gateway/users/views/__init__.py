# Re-exports for backward compatibility
# This ensures all existing imports continue to work

# User profile views
# API key views
from .api_keys import MAX_API_KEY_COUNT
from .api_keys import GenerateAPIKeyFormView
from .api_keys import GenerateAPIKeyView
from .api_keys import NewAPIKeyView
from .api_keys import RevokeAPIKeyView
from .api_keys import generate_api_key_form_view
from .api_keys import get_active_api_key_count
from .api_keys import new_api_key_view
from .api_keys import revoke_api_key_view
from .api_keys import user_api_key_view
from .api_keys import validate_uuid

# Capture views
from .captures import API_CAPTURES_LIMIT
from .captures import CapturesAPIView
from .captures import KeywordAutocompleteAPIView
from .captures import ListCapturesView
from .captures import _get_captures_for_template  # Exported for tests
from .captures import keyword_autocomplete_api_view
from .captures import user_capture_list_view
from .captures import user_captures_api_view

# Dataset views
from .datasets import DatasetDetailsView
from .datasets import GroupCapturesView
from .datasets import ListDatasetsView
from .datasets import user_dataset_details_view
from .datasets import user_dataset_list_view
from .datasets import user_group_captures_view

# Download views
from .downloads import DownloadItemView
from .downloads import TemporaryZipDownloadView
from .downloads import user_download_item_view
from .downloads import user_temporary_zip_download_view

# File views
from .files import CheckFileExistsView
from .files import FileContentView
from .files import FileDetailView
from .files import FileDownloadView
from .files import FileH5InfoView
from .files import FilesView
from .files import ListFilesView
from .files import files_view
from .files import user_check_file_exists_view
from .files import user_file_detail_view
from .files import user_file_list_view

# Share group views
from .share_groups import ShareGroupListView
from .share_groups import user_share_group_list_view

# Sharing views
from .sharing import ShareItemView
from .sharing import ShareOperationError
from .sharing import user_share_item_view

# Special pages
from .special_pages import SPXDACDatasetAltView
from .special_pages import spx_dac_dataset_alt_view

# Upload views
from .uploads import UploadCaptureView
from .uploads import user_upload_capture_view
from .user_profile import UserDetailView
from .user_profile import UserRedirectView
from .user_profile import UserUpdateView
from .user_profile import user_detail_view
from .user_profile import user_redirect_view
from .user_profile import user_update_view

# Utility views
from .utilities import RenderHTMLFragmentView
from .utilities import render_html_fragment_view

__all__ = [
    "API_CAPTURES_LIMIT",
    "MAX_API_KEY_COUNT",
    "CapturesAPIView",
    "CheckFileExistsView",
    "DatasetDetailsView",
    "DownloadItemView",
    "FileContentView",
    "FileDetailView",
    "FileDownloadView",
    "FileH5InfoView",
    "FilesView",
    "GenerateAPIKeyFormView",
    "GenerateAPIKeyView",
    "GroupCapturesView",
    "KeywordAutocompleteAPIView",
    "ListCapturesView",
    "ListDatasetsView",
    "ListFilesView",
    "NewAPIKeyView",
    "RenderHTMLFragmentView",
    "RevokeAPIKeyView",
    "SPXDACDatasetAltView",
    "ShareGroupListView",
    "ShareItemView",
    "ShareOperationError",
    "TemporaryZipDownloadView",
    "UploadCaptureView",
    "UserDetailView",
    "UserRedirectView",
    "UserUpdateView",
    "_get_captures_for_template",
    "files_view",
    "generate_api_key_form_view",
    "get_active_api_key_count",
    "keyword_autocomplete_api_view",
    "new_api_key_view",
    "render_html_fragment_view",
    "revoke_api_key_view",
    "spx_dac_dataset_alt_view",
    "user_api_key_view",
    "user_capture_list_view",
    "user_captures_api_view",
    "user_check_file_exists_view",
    "user_dataset_details_view",
    "user_dataset_list_view",
    "user_detail_view",
    "user_download_item_view",
    "user_file_detail_view",
    "user_file_list_view",
    "user_group_captures_view",
    "user_redirect_view",
    "user_share_group_list_view",
    "user_share_item_view",
    "user_temporary_zip_download_view",
    "user_update_view",
    "user_upload_capture_view",
    "validate_uuid",
]
