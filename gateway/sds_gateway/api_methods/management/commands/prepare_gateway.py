"""Run gateway startup preparation in a single Django process."""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from sds_gateway.visualizations.management.commands.setup_pipelines import (
    PIPELINE_STRATEGIES,
)


class Command(BaseCommand):
    """Prepare the gateway before the ASGI server starts."""

    help = (
        "Prepare the gateway for serving: migrate, init search indices, "
        "SVI token, and visualization pipelines."
    )

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--collectstatic",
            action="store_true",
            help="Collect static files before other steps (production).",
        )
        parser.add_argument(
            "--pipeline-strategy",
            default="skip-if-exists",
            choices=PIPELINE_STRATEGIES,
            help="Strategy passed to setup_pipelines.",
        )

    def handle(self, *args, **options) -> None:
        """Execute the command."""
        if options["collectstatic"]:
            self.stdout.write("Collecting static files...")
            call_command("collectstatic", "--noinput")

        pipeline_strategy = options["pipeline_strategy"]
        steps: list[tuple[str, str, dict[str, object]]] = [
            ("Applying database migrations...", "migrate", {"no_input": True}),
            ("Initializing OpenSearch indices...", "init_indices", {}),
            ("Initializing SVI server token...", "init_svi_token", {}),
            (
                "Setting up django-cog pipelines...",
                "setup_pipelines",
                {"strategy": pipeline_strategy},
            ),
        ]

        for label, command_name, kwargs in steps:
            self.stdout.write(label)
            call_command(command_name, **kwargs)
