# Import cogs for django-cog automatic discovery
from .cog_pipelines import process_waterfall_data_cog
from .cog_pipelines import setup_post_processing_cog

__all__ = ["process_waterfall_data_cog", "setup_post_processing_cog"]
