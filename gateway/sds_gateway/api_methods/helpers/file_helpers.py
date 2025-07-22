from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from sds_gateway.api_methods.views.file_endpoints import CheckFileContentsExistView
from sds_gateway.api_methods.views.file_endpoints import FileViewSet


def upload_file_helper_simple(request, file_data):
    """
    Upload a single file using FileViewSet.create.
    file_data should contain all required fields: name, directory, file,
    media_type, etc.
    Returns ([response], []) for success, ([], [error]) for error, and handles
    409 as a warning.
    """
    factory = APIRequestFactory()
    django_request = factory.post(
        request.path,
        file_data,
        format="multipart",
    )
    django_request.user = request.user
    drf_request = Request(django_request, parsers=[MultiPartParser()])
    drf_request.user = request.user
    view = FileViewSet()
    view.request = drf_request
    view.action = "create"
    view.format_kwarg = None
    view.args = ()
    view.kwargs = {}
    try:
        response = view.create(drf_request)
        if (
            hasattr(response, "status_code")
            and status.HTTP_200_OK
            <= response.status_code
            < status.HTTP_300_MULTIPLE_CHOICES
        ):
            return [response], []
        if (
            hasattr(response, "status_code")
            and response.status_code == status.HTTP_409_CONFLICT
        ):
            # Already exists, treat as warning
            return [], [getattr(response, "data", str(response))]
        return [], [getattr(response, "data", str(response))]
    except Exception as e:  # noqa: BLE001
        return [], [str(e)]


def check_file_contents_exist_helper(request, check_data):
    """
    Call the post method of CheckFileContentsExistView with the given data and
    print the response. check_data should contain the required fields: directory,
    name, sum_blake3, etc.
    """
    factory = APIRequestFactory()
    django_request = factory.post(
        request.path,  # or a specific path for the check endpoint
        check_data,
        format="multipart",
    )
    django_request.user = request.user
    drf_request = Request(django_request, parsers=[MultiPartParser()])
    drf_request.user = request.user
    view = CheckFileContentsExistView()
    view.request = drf_request
    view.action = None
    view.format_kwarg = None
    view.args = ()
    view.kwargs = {}
    return view.post(drf_request)
