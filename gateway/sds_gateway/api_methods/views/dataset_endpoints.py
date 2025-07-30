"""Dataset operations endpoints for the SDS Gateway API."""

import tempfile
import zipfile
from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from loguru import logger as log
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.download_file import download_file
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user


class DatasetViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_dataset_files(self, dataset: Dataset) -> list[File]:
        """Get all files associated with a dataset."""
        # get the files directly connected to the dataset
        artifact_files = list(
            dataset.files.filter(
                is_deleted=False,
            )
        )

        # get the files connected to the captures associated with the dataset
        dataset_captures = dataset.captures.filter(
            is_deleted=False,
        )
        capture_files = []
        for capture in dataset_captures:
            capture_files.extend(
                list(
                    capture.files.filter(
                        is_deleted=False,
                    )
                )
            )

        # Combine and remove duplicates
        all_files = artifact_files + capture_files
        return list(set(all_files))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="Dataset UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: OpenApiResponse(description="HTTP File Response"),
            404: OpenApiResponse(description="Not Found"),
            500: OpenApiResponse(
                description="Internal Server Error - Dataset download failed"
            ),
        },
        description=(
            "Download a dataset as a ZIP file containing all associated files. "
            "Returns the dataset content as an HTTP response with appropriate headers."
        ),
        summary="Download Dataset",
    )
    @action(detail=True, methods=["get"], url_path="download", url_name="download")
    def download_dataset(self, request: Request, pk: str | None = None) -> HttpResponse:
        """Downloads a dataset as a ZIP file containing all associated files."""
        if pk is None:
            return Response(
                {"detail": "Dataset UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_dataset = get_object_or_404(
            Dataset,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        # Get all files associated with this dataset as a list
        dataset_files = self._get_dataset_files(target_dataset)

        if len(dataset_files) == 0:
            return Response(
                {"detail": "No files found in dataset."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            # Create a temporary ZIP file
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_zip:
                temp_zip_path = temp_zip.name

            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_obj in dataset_files:
                    try:
                        # Download the file content
                        file_content = download_file(file_obj)

                        user_relative_path = sanitize_path_rel_to_user(
                            unsafe_path="/",
                            request=request,
                        )

                        # remove the user_relative_path part from the file_obj.directory
                        local_directory = file_obj.directory.replace(
                            user_relative_path, ""
                        )

                        # Create the file path within the ZIP
                        # Use the file's directory and name to maintain structure
                        zip_path = f"{local_directory}{file_obj.name}"

                        # Add the file to the ZIP
                        zip_file.writestr(zip_path, file_content)

                        log.info(f"Added file to dataset ZIP: {zip_path}")

                    except (OSError, ValueError) as e:
                        log.error(
                            f"Failed to download file {file_obj.name} for dataset ZIP: {e}"
                        )
                        # Continue with other files even if one fails
                        continue
                    except Exception as e:
                        log.error(
                            f"Unexpected error adding file {file_obj.name} to dataset ZIP: {e}"
                        )
                        # Continue with other files even if one fails
                        continue

            # Read the ZIP file content
            with open(temp_zip_path, "rb") as zip_file:
                zip_content = zip_file.read()

            # Create HTTP response with the ZIP content
            http_response = HttpResponse(
                zip_content,
                content_type="application/zip",
            )
            http_response["Content-Disposition"] = (
                f'attachment; filename="{target_dataset.name}.zip"'
            )

            log.info(f"Successfully created dataset ZIP for: {target_dataset.name}")

        except OSError as e:
            log.exception(
                f"File system error creating dataset ZIP for {target_dataset.name}: {e}"
            )
            return Response(
                {
                    "detail": "Failed to create dataset ZIP file due to file system error"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except zipfile.BadZipFile as e:
            log.exception(
                f"ZIP file creation error for dataset {target_dataset.name}: {e}"
            )
            return Response(
                {"detail": "Failed to create dataset ZIP file due to ZIP format error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            # Clean up temporary ZIP file
            try:
                if "temp_zip_path" in locals():
                    Path(temp_zip_path).unlink()
            except OSError:
                log.warning(f"Could not delete temporary ZIP file: {temp_zip_path}")

        return http_response
