from django.urls import path

from .api.views import GetAPIKeyView
from .views import ListCapturesView
from .views import user_capture_download_view
from .views import user_captures_api_view
from .views import user_dataset_download_view
from .views import user_dataset_list_view
from .views import user_detail_view
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
    path("file-list/", ListCapturesView.as_view(), name="file_list"),
    path("file-list/api/", user_captures_api_view, name="captures_api"),
    path("file-detail/<uuid:uuid>/", user_file_detail_view, name="file_detail"),
    path("dataset-list/", user_dataset_list_view, name="dataset_list"),
    path(
        "dataset-download/<uuid:uuid>/",
        user_dataset_download_view,
        name="dataset_download",
    ),
    path(
        "capture-download/<uuid:uuid>/",
        user_capture_download_view,
        name="capture_download",
    ),
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
    # Used by SVI Server to get API key for a user
    path("get-svi-api-key/", GetAPIKeyView.as_view(), name="get_svi_api_key"),
]
