"""Migration to convert dataset authors from string format to object format."""

import json
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def convert_authors_to_object_format(apps, schema_editor):
    """Convert dataset authors from string format to object format."""
    Dataset = apps.get_model("api_methods", "Dataset")
    
    # Get all datasets with authors
    datasets = Dataset.objects.filter(authors__isnull=False).exclude(authors="")
    total_count = datasets.count()
    
    if total_count == 0:
        logger.info("No datasets with authors found to convert")
        return
    
    logger.info("Converting %d datasets with authors to new format", total_count)
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for dataset in datasets:
        try:
            # Parse current authors
            if isinstance(dataset.authors, str):
                try:
                    current_authors = json.loads(dataset.authors)
                except (json.JSONDecodeError, TypeError):
                    # Skip datasets with invalid JSON
                    logger.warning("Dataset %s has invalid authors JSON, skipping", dataset.uuid)
                    skipped_count += 1
                    continue
            else:
                current_authors = dataset.authors
            
            if not current_authors:
                skipped_count += 1
                continue
                
            # Check if already in new format (has dict with 'name' key)
            if isinstance(current_authors, list) and current_authors:
                if isinstance(current_authors[0], dict) and "name" in current_authors[0]:
                    logger.debug("Dataset %s already in new format, skipping", dataset.uuid)
                    skipped_count += 1
                    continue
                
                # Convert string authors to object format
                if isinstance(current_authors[0], str):
                    new_authors = []
                    for author in current_authors:
                        if isinstance(author, str):
                            new_authors.append({"name": author, "orcid_id": ""})
                        else:
                            # Handle unexpected format
                            logger.warning(
                                "Dataset %s has unexpected author format: %s", 
                                dataset.uuid, author
                            )
                            new_authors.append({"name": str(author), "orcid_id": ""})
                    
                    # Update the dataset
                    dataset.authors = json.dumps(new_authors)
                    dataset.save(update_fields=["authors"])
                    updated_count += 1
                    logger.debug("Converted dataset %s authors", dataset.uuid)
                else:
                    # Authors are already objects, skip
                    skipped_count += 1
            else:
                # Empty or invalid authors list
                skipped_count += 1
                
        except Exception as e:
            error_count += 1
            logger.error("Error converting dataset %s: %s", dataset.uuid, e)
    
    logger.info(
        "Author conversion complete: %d updated, %d skipped, %d errors", 
        updated_count, skipped_count, error_count
    )


def reverse_authors_to_string_format(apps, schema_editor):
    """Reverse migration: convert authors back to string format."""
    Dataset = apps.get_model("api_methods", "Dataset")
    
    # Get all datasets with authors
    datasets = Dataset.objects.filter(authors__isnull=False).exclude(authors="")
    total_count = datasets.count()
    
    if total_count == 0:
        logger.info("No datasets with authors found to reverse")
        return
    
    logger.info("Reversing %d datasets with authors to string format", total_count)
    
    updated_count = 0
    skipped_count = 0
    error_count = 0
    
    for dataset in datasets:
        try:
            # Parse current authors
            if isinstance(dataset.authors, str):
                try:
                    current_authors = json.loads(dataset.authors)
                except (json.JSONDecodeError, TypeError):
                    skipped_count += 1
                    continue
            else:
                current_authors = dataset.authors
            
            if not current_authors:
                skipped_count += 1
                continue
                
            # Check if in object format (has dict with 'name' key)
            if isinstance(current_authors, list) and current_authors:
                if isinstance(current_authors[0], dict) and "name" in current_authors[0]:
                    # Convert object authors back to string format
                    string_authors = [author["name"] for author in current_authors]
                    
                    # Update the dataset
                    dataset.authors = json.dumps(string_authors)
                    dataset.save(update_fields=["authors"])
                    updated_count += 1
                    logger.debug("Reversed dataset %s authors", dataset.uuid)
                else:
                    # Already in string format, skip
                    skipped_count += 1
            else:
                # Empty or invalid authors list
                skipped_count += 1
                
        except Exception as e:
            error_count += 1
            logger.error("Error reversing dataset %s: %s", dataset.uuid, e)
    
    logger.info(
        "Author reversal complete: %d updated, %d skipped, %d errors", 
        updated_count, skipped_count, error_count
    )


class Migration(migrations.Migration):
    """Migration to convert dataset authors to object format."""

    dependencies = [
        ("api_methods", "0015_rename_postprocesseddata_deprecatedpostprocesseddata_and_more"),
    ]

    operations = [
        migrations.RunPython(
            convert_authors_to_object_format,
            reverse_authors_to_string_format,
            hints={"target_db": "default"},
        ),
    ]
