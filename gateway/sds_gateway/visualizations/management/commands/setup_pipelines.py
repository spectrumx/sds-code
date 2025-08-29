"""Management command to set up django-cog visualization pipelines."""

import datetime
import json

from django.core.management.base import BaseCommand
from django_cog.models import CeleryQueue
from django_cog.models import Cog
from django_cog.models import Pipeline
from django_cog.models import Stage
from django_cog.models import Task

from sds_gateway.visualizations.cog_pipelines import PIPELINE_CONFIGS


class Command(BaseCommand):
    """Set up django-cog pipelines for visualization processing."""

    help = "Set up django-cog pipelines for visualization processing"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--pipeline-type",
            type=str,
            choices=["visualization", "all"],
            default="all",
            help="Type of pipeline to set up",
        )
        parser.add_argument(
            "--strategy",
            type=str,
            choices=["interactive", "skip-if-exists", "force", "smart-recreate"],
            default="interactive",
            help=(
                "Strategy for handling existing pipelines: interactive (warn and "
                "exit), skip-if-exists (silent skip), force (delete and recreate), "
                "smart-recreate (intelligent updates)"
            ),
        )

    def handle(self, *args, **options):
        """Handle the command."""
        pipeline_type = options["pipeline_type"]
        strategy = options["strategy"]

        if pipeline_type == "all":
            pipeline_types = list(PIPELINE_CONFIGS.keys())
        else:
            pipeline_types = [pipeline_type]

        for ptype in pipeline_types:
            self.setup_pipeline(ptype, strategy)

    def _create_new_pipeline(self, config: dict) -> Pipeline:
        """Create a new pipeline with timestamp."""
        timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        new_name = f"{config['pipeline_name']}_{timestamp}"
        return Pipeline.objects.create(
            name=new_name,
            prevent_overlapping_runs=config.get("prevent_overlapping_runs", False),
        )

    def _handle_existing_pipeline_strategy(
        self, pipeline: Pipeline, config: dict, strategy: str
    ) -> Pipeline | None:
        """Handle existing pipeline based on strategy."""
        if strategy == "skip-if-exists":
            self.stdout.write(
                self.style.SUCCESS(
                    f"Pipeline '{config['pipeline_name']}' already exists, skipping."
                )
            )
            return None
        if strategy == "interactive":
            self.stdout.write(
                self.style.WARNING(
                    f"Pipeline '{config['pipeline_name']}' already exists. "
                    "Use --strategy force to recreate or --strategy "
                    "smart-recreate for intelligent handling."
                )
            )
            return None
        if strategy == "force":
            # Delete existing pipeline and recreate (loses history)
            pipeline.delete()
            return Pipeline.objects.create(
                name=config["pipeline_name"],
                prevent_overlapping_runs=config.get("prevent_overlapping_runs", False),
            )
        if strategy == "smart-recreate":
            return self._handle_smart_recreate(pipeline, config)
        return pipeline

    def _handle_smart_recreate(self, pipeline: Pipeline, config: dict) -> Pipeline:
        """Handle smart recreate strategy."""
        runs_count = pipeline.runs.count()

        if runs_count == 0:
            # No runs, delete the latest pipeline and create new one with timestamp
            old_name = pipeline.name
            pipeline.delete()
            new_pipeline = self._create_new_pipeline(config)
            self.stdout.write(
                f"Created new pipeline '{new_pipeline.name}' (replaced unused "
                f"pipeline '{old_name}')"
            )
            return new_pipeline
        # Has runs, create new pipeline with timestamp and preserve old one
        old_name = pipeline.name
        new_pipeline = self._create_new_pipeline(config)

        # Disable the old pipeline to prevent conflicts
        pipeline.enabled = False
        pipeline.save()

        self.stdout.write(
            f"Created new pipeline '{new_pipeline.name}' and disabled old pipeline "
            f"'{old_name}' (preserved with {runs_count} runs)"
        )
        return new_pipeline

    def _create_stages_and_tasks(self, pipeline: Pipeline, config: dict) -> dict:
        """Create stages and tasks for the pipeline."""
        stage_objects = {}
        for stage_config in config["stages"]:
            stage = Stage.objects.create(
                pipeline=pipeline,
                name=stage_config["name"],
            )
            stage_objects[stage_config["name"]] = stage

            # Create tasks for this stage
            for task_config in stage_config["tasks"]:
                # Get or create the Cog for this task (handle duplicates)
                cog = Cog.objects.filter(name=task_config["cog"]).first()
                if not cog:
                    cog = Cog.objects.create(name=task_config["cog"])

                # Get or create default CeleryQueue
                default_queue, _ = CeleryQueue.objects.get_or_create(
                    queue_name="celery"
                )

                Task.objects.create(
                    stage=stage,
                    name=task_config["name"],
                    cog=cog,
                    arguments_as_json=json.dumps(task_config["args"]),
                    queue=default_queue,
                )

        return stage_objects

    def _setup_dependencies(self, config: dict, stage_objects: dict) -> None:
        """Set up dependencies between stages."""
        for stage_config in config["stages"]:
            if "depends_on" in stage_config:
                stage = stage_objects[stage_config["name"]]
                for dep_name in stage_config["depends_on"]:
                    if dep_name in stage_objects:
                        stage.launch_after_stage.add(stage_objects[dep_name])

    def setup_pipeline(
        self,
        pipeline_type: str,
        strategy: str = "interactive",
    ):
        """Set up a specific pipeline."""
        self.stdout.write(f"Setting up {pipeline_type} pipeline...")

        # Get configuration
        config_func = PIPELINE_CONFIGS[pipeline_type]
        config = config_func()

        # Check if pipeline already exists (including versioned pipelines)
        from sds_gateway.visualizations.models import get_latest_pipeline_by_base_name

        existing_pipeline = get_latest_pipeline_by_base_name(config["pipeline_name"])
        if existing_pipeline:
            pipeline = existing_pipeline
            result = self._handle_existing_pipeline_strategy(pipeline, config, strategy)
            if result is None:
                return
            pipeline = result
        else:
            # No existing pipeline found, create new one with timestamp
            pipeline = self._create_new_pipeline(config)

        # Create stages and tasks
        stage_objects = self._create_stages_and_tasks(pipeline, config)

        # Set up dependencies
        self._setup_dependencies(config, stage_objects)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully set up {pipeline_type} pipeline: "
                f"{config['pipeline_name']}"
            )
        )
