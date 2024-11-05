from django.urls import path

from .views import user_detail_view
from .views import user_file_detail_view
from .views import user_file_list_view
from .views import user_generate_api_key_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
    path("generate-api-key/", user_generate_api_key_view, name="generate_api_key"),
    path("file-list/", user_file_list_view, name="file_list"),
    path("file-detail/<uuid:uuid>/", user_file_detail_view, name="file_detail"),
]
