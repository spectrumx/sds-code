"""API views for the visualizations app."""

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample
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
from sds_gateway.api_methods.models import Capture

from .models import PostProcessedData
from .models import ProcessingStatus
from .models import ProcessingType
from .serializers import PostProcessedDataSerializer


class VisualizationViewSet(ViewSet):
    """
    ViewSet for generating visualizations from captures.
    """

    # Constants for validation
    MIN_FFT_SIZE = 64
    MAX_FFT_SIZE = 65536
    MIN_STD_DEV = 10
    MAX_STD_DEV = 500
    MIN_HOP_SIZE = 100
    MAX_HOP_SIZE = 1000

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create spectrogram visualization",
        description="Generate a spectrogram visualization from a capture",
        parameters=[
            OpenApiParameter(
                name="capture_uuid",
                type=str,
                location=OpenApiParameter.PATH,
                description="UUID of the capture to generate spectrogram from",
            )
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "fft_size": {
                        "type": "integer",
                        "description": "FFT size for spectrogram",
                    },
                    "std_dev": {
                        "type": "integer",
                        "description": "Window standard deviation",
                    },
                    "hop_size": {
                        "type": "integer",
                        "description": "Hop size between windows",
                    },
                    "colormap": {
                        "type": "string",
                        "description": "Color map for visualization",
                    },
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="Spectrogram generation started successfully",
                response=PostProcessedDataSerializer,
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            404: OpenApiResponse(description="Capture not found"),
            500: OpenApiResponse(description="Internal server error"),
        },
    )
    @action(detail=True, methods=["post"], url_path="create_spectrogram")
    def create_spectrogram(self, request: Request, capture_uuid: str) -> Response:
        """
        Create a spectrogram visualization for a capture.

        Args:
            request: The HTTP request
            capture_uuid: UUID of the capture

        Returns:
            Response with processing job details
        """
        try:
            # Get the capture
            capture = get_object_or_404(
                Capture, uuid=capture_uuid, owner=request.user, is_deleted=False
            )

            # Validate request data
            fft_size = request.data.get("fft_size", 1024)
            std_dev = request.data.get("std_dev", 100)
            hop_size = request.data.get("hop_size", 500)
            colormap = request.data.get("colormap", "magma")

            # Validate parameters
            if not self._validate_spectrogram_params(
                fft_size, std_dev, hop_size, colormap
            ):
                return Response(
                    {"error": "Invalid spectrogram parameters"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if spectrogram already exists with same parameters
            existing_spectrogram = PostProcessedData.objects.filter(
                capture=capture,
                processing_type=ProcessingType.Spectrogram.value,
                processing_parameters={
                    "fft_size": fft_size,
                    "std_dev": std_dev,
                    "hop_size": hop_size,
                    "colormap": colormap,
                },
            ).first()

            if existing_spectrogram:
                if (
                    existing_spectrogram.processing_status
                    == ProcessingStatus.Completed.value
                ):
                    # Return existing completed spectrogram
                    serializer = PostProcessedDataSerializer(existing_spectrogram)
                    return Response(serializer.data, status=status.HTTP_200_OK)
                if (
                    existing_spectrogram.processing_status
                    == ProcessingStatus.Processing.value
                ):
                    # Return processing status
                    serializer = PostProcessedDataSerializer(existing_spectrogram)
                    return Response(serializer.data, status=status.HTTP_200_OK)

            # Create new spectrogram processing record
            processing_params = {
                "fft_size": fft_size,
                "std_dev": std_dev,
                "hop_size": hop_size,
                "colormap": colormap,
            }

            spectrogram_data = PostProcessedData.objects.create(
                capture=capture,
                processing_type=ProcessingType.Spectrogram.value,
                processing_parameters=processing_params,
                processing_status=ProcessingStatus.Pending.value,
                metadata={
                    "requested_by": str(request.user.uuid),
                    "requested_at": request.data.get("timestamp"),
                    "image_dimensions": request.data.get("dimensions", {}),
                },
            )

            # Start spectrogram processing
            # This will use the cog pipeline to generate the spectrogram
            self._start_spectrogram_processing(spectrogram_data)

            serializer = PostProcessedDataSerializer(spectrogram_data)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:  # noqa: BLE001
            log.error(f"Error creating spectrogram: {e}")
            return Response(
                {"error": "Failed to create spectrogram"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Get spectrogram status",
        description="Get the status of a spectrogram generation job",
        parameters=[
            OpenApiParameter(
                name="capture_uuid",
                type=str,
                location=OpenApiParameter.PATH,
                description="UUID of the capture",
            ),
            OpenApiParameter(
                name="job_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="UUID of the processing job",
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Processing job status",
                response=PostProcessedDataSerializer,
            ),
            404: OpenApiResponse(description="Job not found"),
        },
    )
    @action(detail=True, methods=["get"], url_path="spectrogram_status")
    def get_spectrogram_status(self, request: Request, capture_uuid: str) -> Response:
        """
        Get the status of a spectrogram generation job.
        """
        try:
            job_id = request.query_params.get("job_id")
            if not job_id:
                return Response(
                    {"error": "job_id parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the processing job
            processing_job = get_object_or_404(
                PostProcessedData,
                uuid=job_id,
                capture__uuid=capture_uuid,
                processing_type=ProcessingType.Spectrogram.value,
            )

            serializer = PostProcessedDataSerializer(processing_job)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:  # noqa: BLE001
            log.error(f"Error getting spectrogram status: {e}")
            return Response(
                {"error": "Failed to get spectrogram status"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Download spectrogram result",
        description="Download the generated spectrogram image",
        parameters=[
            OpenApiParameter(
                name="capture_uuid",
                type=str,
                location=OpenApiParameter.PATH,
                description="UUID of the capture",
            ),
            OpenApiParameter(
                name="job_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="UUID of the processing job",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Spectrogram image file"),
            404: OpenApiResponse(description="Result not found"),
            400: OpenApiResponse(description="Processing not completed"),
        },
    )
    @action(detail=True, methods=["get"], url_path="download_spectrogram")
    def download_spectrogram(
        self, request: Request, capture_uuid: str
    ) -> Response | FileResponse:
        """
        Download the generated spectrogram image.
        """
        try:
            job_id = request.query_params.get("job_id")
            if not job_id:
                return Response(
                    {"error": "job_id parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the processing job
            processing_job = get_object_or_404(
                PostProcessedData,
                uuid=job_id,
                capture__uuid=capture_uuid,
                processing_type=ProcessingType.Spectrogram.value,
            )

            if processing_job.processing_status != ProcessingStatus.Completed.value:
                return Response(
                    {"error": "Spectrogram processing not completed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not processing_job.data_file:
                return Response(
                    {"error": "No spectrogram file found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Return the file
            file_response = FileResponse(
                processing_job.data_file, content_type="image/png"
            )
            file_response["Content-Disposition"] = (
                f'attachment; filename="spectrogram_{capture_uuid}.png"'
            )
            return file_response  # noqa: TRY300

        except Exception as e:  # noqa: BLE001
            log.error(f"Error downloading spectrogram: {e}")
            return Response(
                {"error": "Failed to download spectrogram"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="capture_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Type of capture (e.g., 'drf', 'sigmf', 'rh')",
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Visualization compatibility information",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "capture_type": "drf",
                            "available_visualizations": {
                                "waterfall": {
                                    "type": "waterfall",
                                    "supported_capture_types": ["drf", "rh"],
                                    "description": (
                                        "View signal data as a scrolling waterfall "
                                        "display with periodogram"
                                    ),
                                    "icon": "bi-water",
                                    "color": "primary",
                                    "url_pattern": (
                                        "/visualizations/waterfall/{capture_uuid}/"
                                    ),
                                },
                                "spectrogram": {
                                    "type": "spectrogram",
                                    "supported_capture_types": ["drf", "sigmf"],
                                    "description": (
                                        "Visualize signal strength across "
                                        "frequency and time"
                                    ),
                                    "icon": "bi-graph-up",
                                    "color": "success",
                                    "url_pattern": (
                                        "/visualizations/spectrogram/{capture_uuid}/"
                                    ),
                                },
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="Invalid capture type"),
        },
        summary="Get visualization compatibility",
        description="Get available visualizations for a specific capture type",
    )
    @action(detail=False, methods=["get"], url_path="compatibility")
    def get_visualization_compatibility(self, request: Request) -> Response:
        """
        Get available visualizations for a specific capture type.
        """
        try:
            capture_type = request.query_params.get("capture_type")
            if not capture_type:
                return Response(
                    {"error": "capture_type parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Import the compatibility function
            from .config import get_available_visualizations

            available_visualizations = get_available_visualizations(capture_type)

            return Response(
                {
                    "capture_type": capture_type,
                    "available_visualizations": available_visualizations,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:  # noqa: BLE001
            log.error(f"Error getting visualization compatibility: {e}")
            return Response(
                {"error": "Failed to get visualization compatibility"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _validate_spectrogram_params(
        self, fft_size: int, std_dev: int, hop_size: int, colormap: str
    ) -> bool:
        """
        Validate spectrogram parameters.
        """
        # Validate FFT size (must be power of 2)
        if (
            fft_size < self.MIN_FFT_SIZE
            or fft_size > self.MAX_FFT_SIZE
            or (fft_size & (fft_size - 1)) != 0
        ):
            return False

        # Validate standard deviation
        if std_dev < self.MIN_STD_DEV or std_dev > self.MAX_STD_DEV:
            return False

        # Validate hop size
        if hop_size < self.MIN_HOP_SIZE or hop_size > self.MAX_HOP_SIZE:
            return False

        # Validate colormap
        valid_colormaps = [
            "magma",
            "viridis",
            "plasma",
            "inferno",
            "cividis",
            "turbo",
            "jet",
            "hot",
            "cool",
            "rainbow",
        ]
        return colormap in valid_colormaps

    def _start_spectrogram_processing(
        self, spectrogram_data: PostProcessedData
    ) -> None:
        """
        Start spectrogram processing using the cog pipeline.
        """
        try:
            # Mark as processing
            spectrogram_data.processing_status = ProcessingStatus.Processing.value
            spectrogram_data.save()

            # Launch spectrogram processing as a Celery task
            try:
                from sds_gateway.api_methods.tasks import start_capture_post_processing

                # Launch the spectrogram processing task
                result = start_capture_post_processing.delay(
                    str(spectrogram_data.capture.uuid), ["spectrogram"]
                )

                log.info(
                    f"Launched spectrogram processing task for "
                    f"{spectrogram_data.uuid}, task_id: {result.id}"
                )

            except Exception as e:  # noqa: BLE001
                log.error(f"Could not launch spectrogram processing task: {e}")
                # Mark as failed
                spectrogram_data.processing_status = ProcessingStatus.Failed.value
                spectrogram_data.processing_error = f"Failed to launch task: {e}"
                spectrogram_data.save()

        except Exception as e:  # noqa: BLE001
            log.error(f"Error starting spectrogram processing: {e}")
            spectrogram_data.processing_status = ProcessingStatus.Failed.value
            spectrogram_data.processing_error = str(e)
            spectrogram_data.save()
