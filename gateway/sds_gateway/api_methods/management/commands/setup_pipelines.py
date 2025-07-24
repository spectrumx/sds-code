"""Management command to set up django-cog pipelines."""

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
            "--force",
            action="store_true",
            help="Force recreation of existing pipelines",
        )
        parser.add_argument(
            "--skip-if-exists",
            action="store_true",
            help="Skip setup if pipelines already exist (useful for startup)",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        pipeline_type = options["pipeline_type"]
        force = options["force"]
        skip_if_exists = options["skip_if_exists"]

        if pipeline_type == "all":
            pipeline_types = list(PIPELINE_CONFIGS.keys())
        else:
            pipeline_types = [pipeline_type]

        for ptype in pipeline_types:
            self.setup_pipeline(ptype, force, skip_if_exists)

    def setup_pipeline(
        self, pipeline_type: str, force: bool = False, skip_if_exists: bool = False
    ):
        """Set up a specific pipeline."""
        self.stdout.write(f"Setting up {pipeline_type} pipeline...")

        # Get configuration
        config_func = PIPELINE_CONFIGS[pipeline_type]
        config = config_func()

        # Check if pipeline already exists
        pipeline, created = Pipeline.objects.get_or_create(
            name=config["pipeline_name"],
        )

        if not created and not force:
            if skip_if_exists:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Pipeline '{config['pipeline_name']}' already exists, skipping."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Pipeline '{config['pipeline_name']}' already exists. Use --force to recreate."
                    )
                )
            return

        if not created and force:
            # Delete existing pipeline and recreate
            pipeline.delete()
            pipeline = Pipeline.objects.create(
                name=config["pipeline_name"],
            )
            self.stdout.write(f"Recreated pipeline '{config['pipeline_name']}'")
        elif not created:
            # Pipeline exists but we're not forcing recreation
            # Clear existing stages and tasks to recreate them
            pipeline.stages.all().delete()

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
