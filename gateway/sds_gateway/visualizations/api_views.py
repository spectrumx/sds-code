"""API views for the visualizations app."""

from enum import StrEnum
from typing import ClassVar

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from loguru import logger as log
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from pydantic import field_validator
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.models import Capture
from sds_gateway.visualizations.errors import SourceDataError

from .config import get_available_visualizations
from .models import PostProcessedData
from .models import ProcessingStatus
from .models import ProcessingType
from .post_processing import launch_visualization_processing
from .serializers import PostProcessedDataSerializer


class SpectrogramProcessingParams(BaseModel):
    MIN_FFT_SIZE: ClassVar[int] = 64
    MAX_FFT_SIZE: ClassVar[int] = 2048
    MIN_STD_DEV: ClassVar[int] = 10
    MAX_STD_DEV: ClassVar[int] = 500
    MIN_HOP_SIZE: ClassVar[int] = 100
    MAX_HOP_SIZE: ClassVar[int] = 1000
    INTEGER_ERROR_MESSAGE: ClassVar[str] = "must be an integer"
    FFT_RANGE_ERROR_MESSAGE: ClassVar[str] = "must be a power of 2 within allowed range"
    RANGE_ERROR_MESSAGE: ClassVar[str] = "out of allowed range"
    DIMENSIONS_TYPE_ERROR_MESSAGE: ClassVar[str] = "must be a dictionary"
    DIMENSION_POSITIVE_TEMPLATE: ClassVar[str] = "{dimension} must be greater than 0"
    DIMENSION_INTEGER_TEMPLATE: ClassVar[str] = "{dimension} must be an integer"

    fft_size: int
    std_dev: int
    hop_size: int
    colormap: "Colormap"
    dimensions: dict[str, int] | None = None

    @field_validator("fft_size", "std_dev", "hop_size", mode="before")
    @classmethod
    def validate_int_fields(cls, value):
        if isinstance(value, bool):
            msg = cls.INTEGER_ERROR_MESSAGE
            raise TypeError(msg)

        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            msg = cls.INTEGER_ERROR_MESSAGE
            raise ValueError(msg) from exc

    @field_validator("fft_size")
    @classmethod
    def validate_fft_size(cls, value: int) -> int:
        if (
            value < cls.MIN_FFT_SIZE
            or value > cls.MAX_FFT_SIZE
            or (value & (value - 1)) != 0
        ):
            msg = cls.FFT_RANGE_ERROR_MESSAGE
            raise ValueError(msg)
        return value

    @field_validator("std_dev")
    @classmethod
    def validate_std_dev(cls, value: int) -> int:
        if value < cls.MIN_STD_DEV or value > cls.MAX_STD_DEV:
            msg = cls.RANGE_ERROR_MESSAGE
            raise ValueError(msg)
        return value

    @field_validator("hop_size")
    @classmethod
    def validate_hop_size(cls, value: int) -> int:
        if value < cls.MIN_HOP_SIZE or value > cls.MAX_HOP_SIZE:
            msg = cls.RANGE_ERROR_MESSAGE
            raise ValueError(msg)
        return value

    @field_validator("dimensions", mode="before")
    @classmethod
    def validate_dimensions(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            msg = cls.DIMENSIONS_TYPE_ERROR_MESSAGE
            raise TypeError(msg)

        validated_dimensions: dict[str, int] = {}
        for key in ("width", "height"):
            if key not in value:
                continue
            key_value = value[key]
            if isinstance(key_value, bool):
                msg = cls.DIMENSION_INTEGER_TEMPLATE.format(dimension=key)
                raise TypeError(msg)
            try:
                dimension = int(key_value)
            except (TypeError, ValueError) as exc:
                msg = cls.DIMENSION_INTEGER_TEMPLATE.format(dimension=key)
                raise ValueError(msg) from exc
            if dimension <= 0:
                msg = cls.DIMENSION_POSITIVE_TEMPLATE.format(dimension=key)
                raise ValueError(msg)
            validated_dimensions[key] = dimension

        return validated_dimensions

    def to_dict(self) -> dict[str, int | str | dict[str, int]]:
        processing_params: dict[str, int | str | dict[str, int]] = {
            "fft_size": self.fft_size,
            "std_dev": self.std_dev,
            "hop_size": self.hop_size,
            "colormap": self.colormap.value,
        }
        if self.dimensions is not None:
            processing_params["dimensions"] = self.dimensions
        return processing_params


class Colormap(StrEnum):
    MAGMA = "magma"
    VIRIDIS = "viridis"
    PLASMA = "plasma"
    INFERNO = "inferno"
    CIVIDIS = "cividis"
    TURBO = "turbo"
    JET = "jet"
    HOT = "hot"
    COOL = "cool"
    RAINBOW = "rainbow"


class VisualizationViewSet(ViewSet):
    """
    ViewSet for generating visualizations from captures.
    """

    authentication_classes = [SessionAuthentication, APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @staticmethod
    def extract_first_if_list(value):
        """
        Extract the first element if value is a list, otherwise return the value itself.
        """
        return value[0] if isinstance(value, list) else value

    @staticmethod
    def get_request_param(
        request: Request, param_name: str, default=None, *, from_query=False
    ):
        """
        Extract a parameter from request data or query params with list handling.

        Args:
            request: The HTTP request object
            param_name: Name of the parameter to extract
            default: Default value if parameter is not found
            from_query: If True, get from query_params, otherwise from data

        Returns:
            The parameter value (first element if it's a list, otherwise the value
            itself)
        """
        if from_query:
            value = request.query_params.get(param_name, default)
        else:
            value = request.data.get(param_name, default)

        return VisualizationViewSet.extract_first_if_list(value)

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
    def create_spectrogram(self, request: Request, pk: str | None = None) -> Response:
        """
        Create a spectrogram visualization for a capture.

        Args:
            request: The HTTP request
            pk: UUID of the capture
        Returns:
            Response with processing job details
        """
        # Get the capture
        capture = get_object_or_404(
            Capture, uuid=pk, owner=request.user, is_deleted=False
        )

        # Extract and validate request parameters
        fft_size = self.get_request_param(request, "fft_size", 1024)
        std_dev = self.get_request_param(request, "std_dev", 100)
        hop_size = self.get_request_param(request, "hop_size", 500)
        colormap = self.get_request_param(request, "colormap", "magma")
        dimensions = self.get_request_param(request, "dimensions", None)

        try:
            spectrogram_params = self._validate_spectrogram_params(
                fft_size=fft_size,
                std_dev=std_dev,
                hop_size=hop_size,
                colormap=colormap,
                dimensions=dimensions,
            )
        except ValidationError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        processing_params = spectrogram_params.to_dict()

        existing_spectrogram = PostProcessedData.objects.filter(
            capture=capture,
            processing_type=ProcessingType.Spectrogram.value,
            processing_parameters=processing_params,
        ).first()

        if existing_spectrogram:
            log.info(
                f"Existing spectrogram found for capture {capture.uuid}: "
                f"{existing_spectrogram.uuid} "
                f"with parameters: {existing_spectrogram.processing_parameters}"
            )
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

        log.info(
            f"No existing spectrogram found for capture {capture.uuid} "
            f"with these parameters. Starting spectrogram processing."
        )

        try:
            # Start spectrogram processing
            # This will use the cog pipeline to generate the spectrogram
            processing_config = {"spectrogram": processing_params}

            result = launch_visualization_processing(
                str(capture.uuid), processing_config
            )
            log.info(f"Started spectrogram processing for capture {capture.uuid}")

            response_data = {
                "status": "success",
                "message": "Spectrogram processing started",
                "uuid": result["processing_config"]["spectrogram"]["processed_data_id"],
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except SourceDataError as e:
            log.warning(
                f"Source data issue while launching spectrogram processing: {e}"
            )
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:  # noqa: BLE001
            log.error(f"Unexpected error creating spectrogram: {e}")
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
    def get_spectrogram_status(
        self, request: Request, pk: str | None = None
    ) -> Response:
        """
        Get the status of a spectrogram generation job.
        """
        job_id = self.get_request_param(request, "job_id", from_query=True)
        if not job_id:
            return Response(
                {"error": "job_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the post processed data record
        post_processed_data = get_object_or_404(
            PostProcessedData,
            uuid=job_id,
            capture__uuid=pk,
            processing_type=ProcessingType.Spectrogram.value,
        )

        try:
            serializer = PostProcessedDataSerializer(post_processed_data)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except ValidationError as e:
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
        self, request: Request, pk: str | None = None
    ) -> Response | FileResponse:
        """
        Download the generated spectrogram image.
        """
        job_id = self.get_request_param(request, "job_id", from_query=True)
        if not job_id:
            return Response(
                {"error": "job_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the post processed data record
        post_processed_data = get_object_or_404(
            PostProcessedData,
            uuid=job_id,
            capture__uuid=pk,
            processing_type=ProcessingType.Spectrogram.value,
        )

        if post_processed_data.processing_status != ProcessingStatus.Completed.value:
            return Response(
                {"error": "Spectrogram processing not completed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not post_processed_data.data_file:
            return Response(
                {"error": "No spectrogram file found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Return the file
        file_response = FileResponse(
            post_processed_data.data_file, content_type="image/png"
        )
        file_response["Content-Disposition"] = (
            f'attachment; filename="spectrogram_{pk}.png"'
        )
        return file_response

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
            capture_type = self.get_request_param(
                request, "capture_type", from_query=True
            )
            if not capture_type:
                return Response(
                    {"error": "capture_type parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            available_visualizations = get_available_visualizations(capture_type)

            return Response(
                {
                    "capture_type": capture_type,
                    "available_visualizations": available_visualizations,
                },
                status=status.HTTP_200_OK,
            )

        except SourceDataError as e:
            log.warning(
                f"Source data issue while getting visualization compatibility: {e}"
            )
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:  # noqa: BLE001
            log.error(f"Unexpected error getting visualization compatibility: {e}")
            return Response(
                {"error": "Failed to get visualization compatibility"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _validate_spectrogram_params(
        self,
        fft_size,
        std_dev,
        hop_size,
        colormap,
        dimensions=None,
    ) -> SpectrogramProcessingParams:
        """
        Validate spectrogram parameters.

        Raises:
            ValidationError: If any parameter is invalid.
        """
        try:
            return SpectrogramProcessingParams(
                fft_size=fft_size,
                std_dev=std_dev,
                hop_size=hop_size,
                colormap=colormap,
                dimensions=dimensions,
            )
        except PydanticValidationError as exc:
            raise ValidationError(self._format_validation_error_message(exc)) from exc

    @staticmethod
    def _format_validation_error_message(error: PydanticValidationError) -> str:
        error_details = "; ".join(
            f"{'.'.join(str(item) for item in validation_error['loc'])}: "
            f"{validation_error['msg']}"
            for validation_error in error.errors()
        )
        return f"Invalid spectrogram parameters: {error_details}"

    @extend_schema(
        summary="Create waterfall visualization",
        description="Generate a waterfall visualization from a capture",
        parameters=[
            OpenApiParameter(
                name="capture_uuid",
                type=str,
                location=OpenApiParameter.PATH,
                description="UUID of the capture to generate waterfall from",
            )
        ],
        responses={
            200: OpenApiResponse(
                description="Waterfall generation started successfully",
                response=PostProcessedDataSerializer,
            ),
            400: OpenApiResponse(description="Invalid request parameters"),
            404: OpenApiResponse(description="Capture not found"),
            500: OpenApiResponse(description="Internal server error"),
        },
    )
    @action(detail=True, methods=["post"], url_path="create_waterfall")
    def create_waterfall(self, request: Request, pk: str | None = None) -> Response:
        """
        Create a waterfall visualization for a capture.

        Args:
            request: The HTTP request
            pk: UUID of the capture
        Returns:
            Response with processing job details
        """
        # Get the capture
        capture = get_object_or_404(
            Capture, uuid=pk, owner=request.user, is_deleted=False
        )

        try:
            # Check if waterfall already exists
            existing_waterfall = PostProcessedData.objects.filter(
                capture=capture,
                processing_type=ProcessingType.Waterfall.value,
            ).first()

            if existing_waterfall:
                log.info(
                    f"Existing waterfall found for capture {capture.uuid}: "
                    f"{existing_waterfall.uuid}"
                )
                if (
                    existing_waterfall.processing_status
                    == ProcessingStatus.Completed.value
                ):
                    # Return existing completed waterfall
                    serializer = PostProcessedDataSerializer(existing_waterfall)
                    return Response(serializer.data, status=status.HTTP_200_OK)
                if (
                    existing_waterfall.processing_status
                    == ProcessingStatus.Processing.value
                ):
                    # Return processing status
                    serializer = PostProcessedDataSerializer(existing_waterfall)
                    return Response(serializer.data, status=status.HTTP_200_OK)

            log.info(
                f"No existing waterfall found for capture {capture.uuid}."
                " Starting waterfall processing."
            )

            # Start waterfall processing
            # This will use the cog pipeline to generate the waterfall
            processing_config = {"waterfall": {}}

            result = launch_visualization_processing(
                str(capture.uuid), processing_config
            )
            log.info(f"Started waterfall processing for capture {capture.uuid}")

            response_data = {
                "status": "success",
                "message": "Waterfall processing started",
                "uuid": result["processing_config"]["waterfall"]["processed_data_id"],
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except SourceDataError as e:
            log.warning(f"Source data issue while launching waterfall processing: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:  # noqa: BLE001
            log.error(f"Unexpected error creating waterfall: {e}")
            return Response(
                {"error": "Failed to create waterfall"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Get waterfall status",
        description="Get the status of a waterfall generation job",
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
    @action(detail=True, methods=["get"], url_path="waterfall_status")
    def get_waterfall_status(self, request: Request, pk: str | None = None) -> Response:
        """
        Get the status of a waterfall generation job.
        """
        job_id = self.get_request_param(request, "job_id", from_query=True)
        if not job_id:
            return Response(
                {"error": "job_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the processing job
        processing_job = get_object_or_404(
            PostProcessedData,
            uuid=job_id,
            capture__uuid=pk,
            processing_type=ProcessingType.Waterfall.value,
        )

        try:
            serializer = PostProcessedDataSerializer(processing_job)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:  # noqa: BLE001
            log.error(f"Error getting waterfall status: {e}")
            return Response(
                {"error": "Failed to get waterfall status"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Download waterfall result",
        description="Download the generated waterfall data",
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
            200: OpenApiResponse(description="Waterfall data file"),
            404: OpenApiResponse(description="Result not found"),
            400: OpenApiResponse(description="Processing not completed"),
        },
    )
    @action(detail=True, methods=["get"], url_path="download_waterfall")
    def download_waterfall(
        self, request: Request, pk: str | None = None
    ) -> Response | FileResponse:
        """
        Download the generated waterfall data.
        """
        job_id = self.get_request_param(request, "job_id", from_query=True)
        if not job_id:
            return Response(
                {"error": "job_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the processing job
        processing_job = get_object_or_404(
            PostProcessedData,
            uuid=job_id,
            capture__uuid=pk,
            processing_type=ProcessingType.Waterfall.value,
        )

        try:
            if processing_job.processing_status != ProcessingStatus.Completed.value:
                return Response(
                    {"error": "Waterfall processing not completed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not processing_job.data_file:
                return Response(
                    {"error": "No waterfall file found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Return the file
            file_response = FileResponse(
                processing_job.data_file, content_type="application/json"
            )
            file_response["Content-Disposition"] = (
                f'attachment; filename="waterfall_{pk}.json"'
            )
            return file_response  # noqa: TRY300

        except Exception as e:  # noqa: BLE001
            log.error(f"Error downloading waterfall: {e}")
            return Response(
                {"error": "Failed to download waterfall"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
