from django.core.management.base import BaseCommand
from django.db import transaction

from sds_gateway.api_methods.models import Dataset, UserSharePermission


class Command(BaseCommand):
    help = 'Update dataset authors field based on current UserSharePermission records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
        
        datasets_updated = 0
        
        with transaction.atomic():
            # Get all datasets that have share permissions
            datasets_with_permissions = Dataset.objects.filter(
                is_deleted=False,
                captures__isnull=False  # Only datasets with captures
            ).distinct()
            
            for dataset in datasets_with_permissions:
                # Get current authors based on permissions
                authors_data = UserSharePermission.get_dataset_authors(dataset.uuid)
                author_names = [author["name"] for author in authors_data]
                
                # Get current authors field
                current_authors = dataset.get_authors_display()
                
                if set(author_names) != set(current_authors):
                    if dry_run:
                        self.stdout.write(
                            f'Would update dataset {dataset.uuid} ({dataset.name}): '
                            f'Current authors: {current_authors} -> New authors: {author_names}'
                        )
                    else:
                        dataset.authors = author_names
                        dataset.save(update_fields=['authors'])
                        self.stdout.write(
                            f'Updated dataset {dataset.uuid} ({dataset.name}): '
                            f'Authors: {author_names}'
                        )
                    datasets_updated += 1
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'DRY RUN: Would update {datasets_updated} datasets')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully updated {datasets_updated} datasets')
            ) 