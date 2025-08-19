from django.urls import path

from .api.views import GetAPIKeyView
from .views import CheckFileExistsView
from .views import FileContentView
from .views import FileDownloadView
from .views import FileH5InfoView
from .views import FilesView
from .views import ListCapturesView
from .views import UploadFilesView
from .views import user_captures_api_view
from .views import user_dataset_details_view
from .views import user_dataset_list_view
from .views import user_detail_view
from .views import user_download_item_view
from .views import user_file_detail_view
from .views import user_generate_api_key_view
from .views import user_group_captures_view
from .views import user_redirect_view
from .views import user_share_item_view
from .views import user_temporary_zip_download_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
    path("generate-api-key/", user_generate_api_key_view, name="generate_api_key"),
    path("files/", FilesView.as_view(), name="files"),
    path("file-list/", ListCapturesView.as_view(), name="file_list"),
    path("file-list/api/", user_captures_api_view, name="captures_api"),
    path("file-detail/<uuid:uuid>/", user_file_detail_view, name="file_detail"),
    path(
        "files/<uuid:uuid>/download/",
        FileDownloadView.as_view(),
        name="file_download",
    ),
    path("files/<uuid:uuid>/content/", FileContentView.as_view(), name="file_content"),
    path("files/<uuid:uuid>/h5info/", FileH5InfoView.as_view(), name="file_h5info"),
    path("dataset-list/", user_dataset_list_view, name="dataset_list"),
    path("dataset-details/", user_dataset_details_view, name="dataset_details"),
    path("group-captures/", user_group_captures_view, name="group_captures"),
    path(
        "temporary-zip/<uuid:uuid>/download/",
        user_temporary_zip_download_view,
        name="temporary_zip_download",
    ),
    path(
        "share-item/<str:item_type>/<uuid:item_uuid>/",
        user_share_item_view,
        name="share_item",
    ),
    path(
        "download-item/<str:item_type>/<uuid:item_uuid>/",
        user_download_item_view,
        name="download_item",
    ),
    path("upload-files/", UploadFilesView.as_view(), name="upload_files"),
    # TODO: Use this endpoint when implementing the file upload mode multiplexer
    path("check-file-exists/", CheckFileExistsView.as_view(), name="check_file_exists"),
    # Used by SVI Server to get API key for a user
    path("get-svi-api-key/", GetAPIKeyView.as_view(), name="get_svi_api_key"),
]
