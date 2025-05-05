from django.urls import path

from .api.views import GetAPIKeyView
from .views import ListCapturesView
from .views import user_dataset_list_view
from .views import ListCapturesView
from .views import user_dataset_list_view
from .views import user_detail_view
from .views import user_file_detail_view
from .views import user_generate_api_key_view
from .views import user_group_captures_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
    path("generate-api-key/", user_generate_api_key_view, name="generate_api_key"),
    path("file-list", ListCapturesView.as_view(), name="file_list"),
    path("file-detail/<uuid:uuid>/", user_file_detail_view, name="file_detail"),
    path("dataset-list/", user_dataset_list_view, name="dataset_list"),
    path("group-captures/", user_group_captures_view, name="group_captures"),
    # Used by SVI Server to get API key for a user
    path("get-svi-api-key/", GetAPIKeyView.as_view(), name="get_svi_api_key"),
]
