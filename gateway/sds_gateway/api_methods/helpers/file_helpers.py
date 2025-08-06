from http import HTTPStatus

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet
from sds_gateway.api_methods.views.file_endpoints import HTTP_499_CLIENT_CLOSED_REQUEST
from sds_gateway.api_methods.views.file_endpoints import CheckFileContentsExistView
from sds_gateway.api_methods.views.file_endpoints import FileViewSet


def upload_file_helper_simple(request, file_data):
    """Upload a single file using FileViewSet.create.

    file_data should contain all required fields: name, directory, file,
    media_type, etc. Returns ([response], []) for success, ([], [error]) for
    error, and handles 409 as a warning.
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
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        return [], [f"Data validation error: {e}"]
    else:
        responses = []
        errors = []

        if not hasattr(response, "status_code"):
            errors.append(getattr(response, "data", str(response)))
        else:
            http_status = HTTPStatus(response.status_code)
            response_data = getattr(response, "data", str(response))

            if http_status.is_success:
                responses.append(response)
            elif (
                response.status_code == HTTP_499_CLIENT_CLOSED_REQUEST
            ):  # Client closed request
                errors.append("Client closed request")
                return [], ["Client closed request"]
            elif response.status_code == status.HTTP_409_CONFLICT:
                # Already exists, treat as warning
                errors.append(response_data)
            elif http_status.is_server_error:
                # Handle 500 and other server errors
                errors.append("Internal server error")
            elif http_status.is_client_error:
                # Handle 4xx client errors
                errors.append(f"Client error ({response.status_code}): {response_data}")
            else:
                # Handle any other status codes
                errors.append(response_data)

        return responses, errors


# TODO: Use this helper method when implementing the file upload mode multiplexer.
def check_file_contents_exist_helper(request, check_data):
    """Call the post method of CheckFileContentsExistView with the given data.

    check_data should contain the required fields: directory, name, sum_blake3,
    etc.
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


def create_capture_helper_simple(request, capture_data):
    """Create a capture using CaptureViewSet.create.

    capture_data should contain all required fields for capture creation:
    owner, top_level_dir, capture_type, channel, index_name, etc.
    Returns ([response], []) for success, ([], [error]) for error, and handles
    409 as a warning.
    """
    factory = APIRequestFactory()
    django_request = factory.post(
        request.path,
        capture_data,
        format="multipart",
    )
    django_request.user = request.user
    drf_request = Request(django_request, parsers=[MultiPartParser()])
    drf_request.user = request.user
    view = CaptureViewSet()
    view.request = drf_request
    view.action = "create"
    view.format_kwarg = None
    view.args = ()
    view.kwargs = {}
    # Set the context for the serializer
    view.get_serializer_context = lambda: {"request_user": request.user}
    try:
        response = view.create(drf_request)
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        return [], [f"Data validation error: {e}"]
    else:
        responses = []
        errors = []

        if not hasattr(response, "status_code"):
            errors.append(getattr(response, "data", str(response)))
        else:
            http_status = HTTPStatus(response.status_code)
            response_data = getattr(response, "data", str(response))

            if http_status.is_success:
                responses.append(response)
            elif response.status_code == status.HTTP_409_CONFLICT:
                # Already exists, treat as warning
                errors.append(response_data)
            elif http_status.is_server_error:
                # Handle 500 and other server errors
                errors.append(f"Server error ({response.status_code}): {response_data}")
            elif http_status.is_client_error:
                # Handle 4xx client errors
                errors.append(f"Client error ({response.status_code}): {response_data}")
            else:
                # Handle any other status codes
                errors.append(response_data)

        return responses, errors
