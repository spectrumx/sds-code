"""Management command to set up django-cog pipelines."""

import datetime
import json

from django.core.management.base import BaseCommand
from django_cog.models import CeleryQueue
from django_cog.models import Cog
from django_cog.models import Pipeline
from django_cog.models import Stage
from django_cog.models import Task

from sds_gateway.api_methods.cog_pipelines import PIPELINE_CONFIGS


class Command(BaseCommand):
    """Set up django-cog pipelines for post-processing."""

    help = "Set up django-cog pipelines for post-processing"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--pipeline-type",
            type=str,
            choices=["waterfall", "all"],
            default="all",
            help="Type of pipeline to set up",
        )
        parser.add_argument(
            "--strategy",
            type=str,
            choices=["interactive", "skip-if-exists", "force", "smart-recreate"],
            default="interactive",
            help="Strategy for handling existing pipelines: interactive (warn and exit), skip-if-exists (silent skip), force (delete and recreate), smart-recreate (intelligent updates)",
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
        from sds_gateway.api_methods.models import get_latest_pipeline_by_base_name

        existing_pipeline = get_latest_pipeline_by_base_name(config["pipeline_name"])
        if existing_pipeline:
            pipeline = existing_pipeline
        else:
            # No existing pipeline found, create new one with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{config['pipeline_name']} (v{timestamp})"
            pipeline = Pipeline.objects.create(name=new_name)

        if existing_pipeline:
            if strategy == "skip-if-exists":
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Pipeline '{config['pipeline_name']}' already exists, skipping."
                    )
                )
                return
            if strategy == "interactive":
                self.stdout.write(
                    self.style.WARNING(
                        f"Pipeline '{config['pipeline_name']}' already exists. Use --strategy force to recreate or --strategy smart-recreate for intelligent handling."
                    )
                )
                return
            if strategy == "force":
                # Delete existing pipeline and recreate (loses history)
                pipeline.delete()
                pipeline = Pipeline.objects.create(
                    name=config["pipeline_name"],
                )
                self.stdout.write(
                    f"Recreated pipeline '{config['pipeline_name']}' (history lost)"
                )
            elif strategy == "smart-recreate":
                # Smart recreate: check if latest pipeline has runs
                runs_count = pipeline.runs.count()

                if runs_count == 0:
                    # No runs, delete the latest pipeline and create new one with timestamp
                    old_name = pipeline.name
                    pipeline.delete()
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_name = f"{config['pipeline_name']} (v{timestamp})"

                    pipeline = Pipeline.objects.create(
                        name=new_name,
                    )
                    self.stdout.write(
                        f"Created new pipeline '{new_name}' (replaced unused pipeline '{old_name}')"
                    )
                else:
                    # Has runs, create new pipeline with timestamp and preserve old one
                    old_name = pipeline.name
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_name = f"{config['pipeline_name']} (v{timestamp})"

                    # Disable the old pipeline to prevent conflicts
                    pipeline.enabled = False
                    pipeline.save()

                    pipeline = Pipeline.objects.create(
                        name=new_name,
                    )
                    self.stdout.write(
                        f"Created new pipeline '{new_name}' and disabled old pipeline '{old_name}' (preserved with {runs_count} runs)"
                    )

        # Create stages and tasks
        stage_objects = {}
        for stage_config in config["stages"]:
            stage = Stage.objects.create(
                pipeline=pipeline,
                name=stage_config["name"],
            )
            stage_objects[stage_config["name"]] = stage

            # Create tasks for this stage
            for task_config in stage_config["tasks"]:
                # Get or create the Cog for this task
                cog, _ = Cog.objects.get_or_create(name=task_config["cog"])

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

        # Set up dependencies
        for stage_config in config["stages"]:
            if "depends_on" in stage_config:
                stage = stage_objects[stage_config["name"]]
                for dep_name in stage_config["depends_on"]:
                    if dep_name in stage_objects:
                        stage.launch_after_stage.add(stage_objects[dep_name])

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully set up {pipeline_type} pipeline: {config['pipeline_name']}"
            )
        )
