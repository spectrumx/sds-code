# Post-Processing Architecture with Django-Cog

This document describes the implementation of a generalized post-processing system for DigitalRF captures using django-cog pipelines.

## Overview

The post-processing system automatically converts DigitalRF captures into various visualization formats (waterfall, spectrogram, etc.) using django-cog pipelines. The system is designed to be extensible, allowing new processing types to be easily added.

## Architecture

### Core Components

1. **PostProcessedData Model** (`sds_gateway/api_methods/models.py`)
   - Generalized model to store any type of post-processed data
   - Tracks processing status, metadata, and pipeline information
   - Supports multiple processing types per capture

2. **Django-Cog Pipelines** (`sds_gateway/api_methods/cog_pipelines.py`)
   - `CapturePostProcessingPipeline`: Multi-type processing pipeline
   - `WaterfallProcessingPipeline`: Specialized waterfall processing
   - `SpectrogramProcessingPipeline`: Specialized spectrogram processing
   - Pipeline registry for easy access

3. **Celery Tasks** (`sds_gateway/api_methods/tasks.py`)
   - `start_capture_post_processing`: Main entry point
   - `download_capture_files`: Download DigitalRF files
   - `process_waterfall_data`: Convert to waterfall format
   - `process_spectrogram_data`: Convert to spectrogram format
   - `store_processed_data`: Store results back to SDS
   - `cleanup_temp_files`: Clean up temporary files

4. **API Endpoints** (`sds_gateway/api_methods/views/capture_endpoints.py`)
   - `POST /captures/{id}/trigger_post_processing/`: Start processing
   - `GET /captures/{id}/post_processing_status/`: Check status
   - `POST /captures/{id}/trigger_waterfall_processing/`: Legacy endpoint

## Data Model

### PostProcessedData

```python
class PostProcessedData(BaseModel):
    capture = models.ForeignKey(Capture, ...)
    processing_type = models.CharField(choices=ProcessingType)
    processing_parameters = models.JSONField()  # FFT size, window type, etc.
    data_file = models.FileField()  # Processed data file
    metadata = models.JSONField()  # Frequencies, timestamps, etc.
    processing_status = models.CharField(choices=ProcessingStatus)
    processing_error = models.TextField()
    processed_at = models.DateTimeField()
    pipeline_id = models.CharField()  # Cog pipeline tracking
    pipeline_step = models.CharField()  # Current step
```

### Processing Types

- `waterfall`: Waterfall visualization data
- `spectrogram`: Spectrogram visualization data
- (Future: `iq_data`, `demodulated_data`, etc.)

### Processing Status

- `pending`: Waiting to be processed
- `processing`: Currently being processed
- `completed`: Processing finished successfully
- `failed`: Processing failed with error

## Pipeline Flow

### 1. Capture Creation
When a new DigitalRF capture is created, a Django signal automatically triggers the post-processing pipeline.

### 2. Pipeline Execution
```python
# Create PostProcessedData records
for processing_type in processing_types:
    _create_or_reset_processed_data(capture, processing_type)

# Create and run pipeline
pipeline = get_pipeline("capture_post_processing", 
                      capture_uuid=capture_uuid, 
                      processing_types=processing_types)
pipeline.run()
```

### 3. Pipeline Steps
1. **Download Files**: Download DigitalRF files from SDS storage
2. **Process Data**: Convert DigitalRF to requested format(s)
3. **Store Results**: Save processed data back to SDS
4. **Cleanup**: Remove temporary files

### 4. Status Updates
The pipeline automatically updates processing status at each step:
- `processing`: When processing starts
- `completed`: When processing finishes
- `failed`: If any step fails

## Usage Examples

### Starting Post-Processing

```python
# Start waterfall processing only
POST /api/captures/{uuid}/trigger_post_processing/
{
    "processing_types": ["waterfall"]
}

# Start multiple processing types
POST /api/captures/{uuid}/trigger_post_processing/
{
    "processing_types": ["waterfall", "spectrogram"]
}
```

### Checking Status

```python
GET /api/captures/{uuid}/post_processing_status/
```

Response:
```json
{
    "capture_uuid": "123e4567-e89b-12d3-a456-426614174000",
    "post_processed_data": [
        {
            "id": 1,
            "processing_type": "waterfall",
            "processing_status": "completed",
            "processing_parameters": {
                "fft_size": 1024,
                "samples_per_slice": 1024
            },
            "metadata": {
                "center_frequency": 1000000000.0,
                "sample_rate": 2000000.0,
                "total_slices": 1000
            },
            "data_file": "/media/post_processed_data/waterfall_123.h5",
            "processed_at": "2024-01-01T12:00:00Z",
            "is_ready": true
        }
    ]
}
```

### Accessing Processed Data

```python
# Get all post-processed data for a capture
capture = Capture.objects.get(uuid=capture_uuid)
processed_data = capture.post_processed_data.all()

# Get specific processing type
waterfall_data = capture.post_processed_data.filter(
    processing_type=ProcessingType.Waterfall.value
).first()

# Check if data is ready
if waterfall_data.is_ready:
    # Use the processed data
    data_file = waterfall_data.data_file
    metadata = waterfall_data.metadata
```

## Adding New Processing Types

### 1. Add Processing Type

```python
# In models.py
class ProcessingType(StrEnum):
    Waterfall = "waterfall"
    Spectrogram = "spectrogram"
    NewType = "new_type"  # Add new type
```

### 2. Create Processing Task

```python
# In tasks.py
@shared_task
def process_new_type_data(capture_uuid: str) -> dict:
    """Process DigitalRF data into new format."""
    # Implementation here
    pass
```

### 3. Add to Pipeline

```python
# In cog_pipelines.py
def get_steps(self) -> List[Step]:
    steps = []
    # ... existing steps ...
    
    for processing_type in self.processing_types:
        if processing_type == ProcessingType.NewType.value:
            steps.append(
                Step(
                    name=f"process_{processing_type}",
                    task=process_new_type_data,
                    args=[self.capture_uuid],
                    description=f"Process {processing_type} data",
                    depends_on=["download_files"],
                )
            )
```

### 4. Add Serializer (Optional)

```python
# In serializers.py
class NewTypeDataSerializer(PostProcessedDataSerializer):
    """Serializer for new type data."""
    
    class Meta(PostProcessedDataSerializer.Meta):
        fields = PostProcessedDataSerializer.Meta.fields + [
            "new_field_1",
            "new_field_2",
        ]
```

## Configuration

### Django Settings

```python
# settings.py
INSTALLED_APPS = [
    # ... existing apps ...
    'django_cog',
]

# Celery configuration
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
```

### Default Processing Parameters

```python
# In tasks.py
default_params = {
    ProcessingType.Waterfall.value: {
        "fft_size": 1024,
        "samples_per_slice": 1024,
    },
    ProcessingType.Spectrogram.value: {
        "fft_size": 1024,
        "window_type": "hann",
        "overlap": 0.5,
    },
}
```

## Monitoring and Debugging

### Pipeline Status

```python
# Check pipeline status
processed_data = PostProcessedData.objects.filter(
    capture=capture,
    processing_type=ProcessingType.Waterfall.value
).first()

print(f"Status: {processed_data.processing_status}")
print(f"Pipeline ID: {processed_data.pipeline_id}")
print(f"Current Step: {processed_data.pipeline_step}")
```

### Error Handling

```python
# Check for errors
failed_data = PostProcessedData.objects.filter(
    processing_status=ProcessingStatus.Failed.value
)

for data in failed_data:
    print(f"Error: {data.processing_error}")
```

### Logging

The system uses structured logging with loguru:

```python
logger.info(f"Starting post-processing pipeline for capture {capture_uuid}")
logger.error(f"Step {step.name} failed: {error}")
```

## Performance Considerations

### Parallel Processing

Multiple processing types can run in parallel within the same pipeline:

```python
# Process waterfall and spectrogram simultaneously
pipeline = get_pipeline("capture_post_processing", 
                      capture_uuid=capture_uuid, 
                      processing_types=["waterfall", "spectrogram"])
```

### Resource Management

- Temporary files are automatically cleaned up
- Large files are processed in chunks
- Memory usage is monitored and optimized

### Caching

- Processed data is cached in SDS storage
- Metadata is stored in the database for quick access
- Pipeline results are cached to avoid reprocessing

## Security

### Access Control

- Only capture owners can trigger post-processing
- Processed data inherits capture permissions
- API endpoints require authentication

### Data Validation

- Processing parameters are validated
- File paths are sanitized
- Input data is verified before processing

## Future Enhancements

### Planned Features

1. **Real-time Processing**: Stream processing for live captures
2. **Custom Parameters**: User-configurable processing parameters
3. **Batch Processing**: Process multiple captures simultaneously
4. **Advanced Visualizations**: 3D plots, time-frequency analysis
5. **Export Formats**: Support for various output formats

### Integration Points

1. **SVI Integration**: Direct integration with visualization platform
2. **External APIs**: Support for external processing services
3. **Plugin System**: Extensible processing pipeline system
4. **WebSocket Updates**: Real-time status updates

## Troubleshooting

### Common Issues

1. **Pipeline Stuck**: Check Celery worker status and Redis connectivity
2. **Memory Errors**: Reduce FFT size or process smaller chunks
3. **File Not Found**: Verify DigitalRF file structure and permissions
4. **Processing Slow**: Check system resources and optimize parameters

### Debug Commands

```bash
# Check Celery status
celery -A sds_gateway status

# Monitor Celery tasks
celery -A sds_gateway monitor

# Check Redis connectivity
redis-cli ping

# View pipeline logs
tail -f logs/celery.log
```

## Conclusion

The django-cog based post-processing system provides a robust, extensible foundation for converting DigitalRF captures into various visualization formats. The system is designed to scale with the growing needs of the SDS platform while maintaining backward compatibility and providing clear upgrade paths for future enhancements. 