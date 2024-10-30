import tempfile
from pathlib import Path

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from sds_gateway.api_methods.helpers.extract_drf_metadata import (
    validate_metadata_by_channel,
)
from sds_gateway.api_methods.helpers.index_handling import index_capture_metadata
from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.helpers.reconstruct_file_tree import destroy_tree
from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.capture_serializers import (
    CapturePostSerializer,
)
from sds_gateway.api_methods.views.auth_endpoints import APIKeyAuthentication


class CaptureViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CapturePostSerializer,
        responses={
            201: CapturePostSerializer,
            400: "Bad Request",
        },
        description="Create a capture object, connect files to the capture, and index its metadata.",  # noqa: E501
        summary="Create Capture",
    )
    def create(self, request):
        # channel whose data/metadata to capture
        channel = request.data.get("channel", None)
        # path to directory that contains the channel dirs
        top_level_dir = request.data.get("top_level_dir", "")

        # Ensure the top_level_dir is not a relative path
        if ".." in top_level_dir:
            msg = "Relative paths are not allowed."
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve the top_level_dir to an absolute path
        resolved_top_level_dir = Path(top_level_dir).resolve(strict=False)

        # Ensure the resolved path is within the user's files directory
        user_files_dir = Path(f"/files/{request.user.email}").resolve(strict=False)
        if not str(resolved_top_level_dir).startswith(str(user_files_dir)):
            msg = f"The top_level_dir must be in the user's files directory: /files/{request.user.email}"  # noqa: E501
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        request.data["owner"] = request.user.id
        serializer = CapturePostSerializer(
            data=request.data,
        )
        if serializer.is_valid():
            serializer.save()
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # get capture object from serializer
        capture_data = dict(serializer.data)
        capture = Capture.objects.get(
            uuid=capture_data["uuid"],
            owner=request.user,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_dir_path, files_to_connect = reconstruct_tree(
                temp_dir,
                top_level_dir,
                request.user,
            )

            for file in files_to_connect:
                file.capture = capture
                file.save()

            validated_metadata = validate_metadata_by_channel(tmp_dir_path, channel)
            index_capture_metadata(capture, validated_metadata)
            destroy_tree(temp_dir)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={
            200: {"capture": CaptureGetSerializer, "metadata": dict},
            404: "Not Found",
        },
        description="Retrieve a capture object and its indexed metadata.",
        summary="Retrieve Capture",
    )
    def retrieve(self, request, pk=None):
        capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=request.user,
        )
        serializer = CaptureGetSerializer(capture, many=False)
        metadata = retrieve_indexed_metadata(capture)
        return Response({"capture": serializer.data, "metadata": metadata})
