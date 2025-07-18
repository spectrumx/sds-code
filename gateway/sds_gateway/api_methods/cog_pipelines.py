"""Django-cog pipeline configurations for post-processing."""

from typing import Any

from django_cog import Pipeline
from django_cog import Step
from loguru import logger

from .models import Capture
from .models import PostProcessedData
from .models import ProcessingType
from .tasks import cleanup_temp_files
from .tasks import download_capture_files
from .tasks import process_spectrogram_data
from .tasks import process_waterfall_data
from .tasks import store_processed_data


class CapturePostProcessingPipeline(Pipeline):
    """Pipeline for post-processing DigitalRF captures."""

    def __init__(self, capture_uuid: str, processing_types: list[str] = None):
        """Initialize the pipeline.

        Args:
            capture_uuid: UUID of the capture to process
            processing_types: List of processing types to run (waterfall, spectrogram, etc.)
        """
        super().__init__()
        self.capture_uuid = capture_uuid
        self.processing_types = processing_types or [ProcessingType.Waterfall.value]
        self.temp_files = []

    def get_steps(self) -> list[Step]:
        """Define the pipeline steps."""
        steps = []

        # Step 1: Download capture files
        steps.append(
            Step(
                name="download_files",
                task=download_capture_files,
                args=[self.capture_uuid],
                description="Download DigitalRF files from storage",
            )
        )

        # Step 2: Process each requested type
        for processing_type in self.processing_types:
            if processing_type == ProcessingType.Waterfall.value:
                steps.append(
                    Step(
                        name=f"process_{processing_type}",
                        task=process_waterfall_data,
                        args=[self.capture_uuid],
                        description=f"Process {processing_type} data",
                        depends_on=["download_files"],
                    )
                )
            elif processing_type == ProcessingType.Spectrogram.value:
                steps.append(
                    Step(
                        name=f"process_{processing_type}",
                        task=process_spectrogram_data,
                        args=[self.capture_uuid],
                        description=f"Process {processing_type} data",
                        depends_on=["download_files"],
                    )
                )

            # Step 3: Store processed data
            steps.append(
                Step(
                    name=f"store_{processing_type}",
                    task=store_processed_data,
                    args=[self.capture_uuid, processing_type],
                    description=f"Store {processing_type} data",
                    depends_on=[f"process_{processing_type}"],
                )
            )

        # Step 4: Cleanup temporary files
        steps.append(
            Step(
                name="cleanup",
                task=cleanup_temp_files,
                args=[self.capture_uuid],
                description="Clean up temporary files",
                depends_on=[f"store_{pt}" for pt in self.processing_types],
            )
        )

        return steps

    def on_step_start(self, step: Step, context: dict[str, Any]) -> None:
        """Called when a step starts."""
        logger.info(f"Starting step: {step.name} for capture {self.capture_uuid}")

        # Update processing status
        if step.name.startswith("process_"):
            processing_type = step.name.replace("process_", "")
            self._update_processing_status(processing_type, "processing", step.name)

    def on_step_complete(
        self, step: Step, context: dict[str, Any], result: Any
    ) -> None:
        """Called when a step completes successfully."""
        logger.info(f"Completed step: {step.name} for capture {self.capture_uuid}")

        # Update processing status
        if step.name.startswith("process_"):
            processing_type = step.name.replace("process_", "")
            self._update_processing_status(processing_type, "completed")
        elif step.name.startswith("store_"):
            processing_type = step.name.replace("store_", "")
            self._update_processing_status(processing_type, "completed")

    def on_step_error(
        self, step: Step, context: dict[str, Any], error: Exception
    ) -> None:
        """Called when a step fails."""
        logger.error(
            f"Step {step.name} failed for capture {self.capture_uuid}: {error}"
        )

        # Update processing status
        if step.name.startswith("process_"):
            processing_type = step.name.replace("process_", "")
            self._update_processing_status(processing_type, "failed", error=str(error))

    def _update_processing_status(
        self, processing_type: str, status: str, step: str = None
    ) -> None:
        """Update the processing status for a specific processing type."""
        try:
            capture = Capture.objects.get(uuid=self.capture_uuid)
            processed_data = PostProcessedData.objects.filter(
                capture=capture,
                processing_type=processing_type,
            ).first()

            if processed_data:
                if status == "processing":
                    processed_data.mark_processing_started(
                        pipeline_id=self.pipeline_id, step=step or "processing"
                    )
                elif status == "completed":
                    processed_data.mark_processing_completed()
                elif status == "failed":
                    processed_data.mark_processing_failed(
                        f"Pipeline step failed: {step}"
                    )

        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")


class WaterfallProcessingPipeline(Pipeline):
    """Specialized pipeline for waterfall processing only."""

    def __init__(self, capture_uuid: str):
        """Initialize the waterfall processing pipeline."""
        super().__init__()
        self.capture_uuid = capture_uuid

    def get_steps(self) -> list[Step]:
        """Define the waterfall processing steps."""
        return [
            Step(
                name="download_files",
                task=download_capture_files,
                args=[self.capture_uuid],
                description="Download DigitalRF files from storage",
            ),
            Step(
                name="process_waterfall",
                task=process_waterfall_data,
                args=[self.capture_uuid],
                description="Process waterfall data",
                depends_on=["download_files"],
            ),
            Step(
                name="store_waterfall",
                task=store_processed_data,
                args=[self.capture_uuid, ProcessingType.Waterfall.value],
                description="Store waterfall data",
                depends_on=["process_waterfall"],
            ),
            Step(
                name="cleanup",
                task=cleanup_temp_files,
                args=[self.capture_uuid],
                description="Clean up temporary files",
                depends_on=["store_waterfall"],
            ),
        ]


class SpectrogramProcessingPipeline(Pipeline):
    """Specialized pipeline for spectrogram processing only."""

    def __init__(self, capture_uuid: str):
        """Initialize the spectrogram processing pipeline."""
        super().__init__()
        self.capture_uuid = capture_uuid

    def get_steps(self) -> list[Step]:
        """Define the spectrogram processing steps."""
        return [
            Step(
                name="download_files",
                task=download_capture_files,
                args=[self.capture_uuid],
                description="Download DigitalRF files from storage",
            ),
            Step(
                name="process_spectrogram",
                task=process_spectrogram_data,
                args=[self.capture_uuid],
                description="Process spectrogram data",
                depends_on=["download_files"],
            ),
            Step(
                name="store_spectrogram",
                task=store_processed_data,
                args=[self.capture_uuid, ProcessingType.Spectrogram.value],
                description="Store spectrogram data",
                depends_on=["process_spectrogram"],
            ),
            Step(
                name="cleanup",
                task=cleanup_temp_files,
                args=[self.capture_uuid],
                description="Clean up temporary files",
                depends_on=["store_spectrogram"],
            ),
        ]


# Pipeline registry for easy access
PIPELINE_REGISTRY = {
    "capture_post_processing": CapturePostProcessingPipeline,
    "waterfall": WaterfallProcessingPipeline,
    "spectrogram": SpectrogramProcessingPipeline,
}


def get_pipeline(pipeline_type: str, **kwargs) -> Pipeline:
    """Get a pipeline instance by type.

    Args:
        pipeline_type: Type of pipeline to create
        **kwargs: Arguments to pass to the pipeline constructor

    Returns:
        Pipeline instance
    """
    pipeline_class = PIPELINE_REGISTRY.get(pipeline_type)
    if not pipeline_class:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}")

    return pipeline_class(**kwargs)
