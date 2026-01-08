"""Utility functions for handling FK and M2M relationships during migration.

This module provides centralized functions for querying files and captures
through both ForeignKey (FK) and ManyToMany (M2M) relationships during the
expand-contract migration pattern.

During expansion: Functions return union of M2M + FK relationships
During contraction: Update these functions to only return M2M relationships
"""

from django.db.models import QuerySet

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File


def union_to_queryset(
    queryset: QuerySet[File | Capture | Dataset],
    model: type[File | Capture | Dataset],
) -> QuerySet[File | Capture | Dataset]:
    """
    Convert a union queryset to a regular queryset.
    """
    asset_ids = list(queryset.values_list('uuid', flat=True))
    if not asset_ids:
        return model.objects.none()
    return model.objects.filter(uuid__in=asset_ids)

def get_capture_files(capture: Capture, *, include_deleted: bool = False) -> QuerySet[File]:
    """
    Get all files associated with a capture via both M2M and FK relationships.

    Args:
        capture: The capture to get files for
        include_deleted: If True, include deleted files. If False (default), exclude deleted files.

    Returns:
        QuerySet of files associated with the capture
    """
    # Get files via M2M relationship
    files_m2m = capture.files.all()
    if not include_deleted:
        files_m2m = files_m2m.filter(is_deleted=False)

    # Get files via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    files_fk = File.objects.filter(capture=capture)
    if not include_deleted:
        files_fk = files_fk.filter(is_deleted=False)

    # Combine both querysets
    files_union = files_m2m.union(files_fk)

    # get list of file ids
    return union_to_queryset(files_union, File)


def get_dataset_artifact_files(dataset: Dataset, *, include_deleted: bool = False) -> QuerySet[File]:
    """
    Get artifact files directly associated with a dataset via both M2M and FK relationships.

    Note: This does NOT include files from captures associated with the dataset.
    Use get_dataset_files_including_captures() for that.

    Args:
        dataset: The dataset to get files for
        include_deleted: If True, include deleted files. If False (default), exclude deleted files.

    Returns:
        QuerySet of files directly associated with the dataset
    """
    # Get files via M2M relationship
    files_m2m = dataset.files.all()
    if not include_deleted:
        files_m2m = files_m2m.filter(is_deleted=False)

    # Get files via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    files_fk = dataset.files_deprecated.all()
    if not include_deleted:
        files_fk = files_fk.filter(is_deleted=False)

    # Combine both querysets
    files_union = files_m2m.union(files_fk)
    
    # get list of file ids
    return union_to_queryset(files_union, File)


def get_dataset_captures(dataset: Dataset, *, include_deleted: bool = False) -> QuerySet[Capture]:
    """
    Get all captures associated with a dataset via both M2M and FK relationships.

    Args:
        dataset: The dataset to get captures for
        include_deleted: If True, include deleted captures. If False (default), exclude deleted captures.

    Returns:
        QuerySet of captures associated with the dataset
    """
    # Get captures via M2M relationship
    captures_m2m = dataset.captures.all()
    if not include_deleted:
        captures_m2m = captures_m2m.filter(is_deleted=False)

    # Get captures via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    captures_fk = dataset.captures_deprecated.all()
    if not include_deleted:
        captures_fk = captures_fk.filter(is_deleted=False)

    # Combine both querysets
    captures_union = captures_m2m.union(captures_fk)
    return union_to_queryset(captures_union, Capture)


def get_dataset_files_including_captures(
    dataset: Dataset, *, include_deleted: bool = False
) -> QuerySet[File]:
    """
    Get all files associated with a dataset, including files from linked captures.

    This includes:
    1. Files directly associated with the dataset (M2M + FK)
    2. Files from captures associated with the dataset (via M2M + FK on both relationships)

    Args:
        dataset: The dataset to get files for
        include_deleted: If True, include deleted files. If False (default), exclude deleted files.

    Returns:
        QuerySet of all files associated with the dataset
    """
    # Get files directly associated with the dataset
    dataset_files = get_dataset_artifact_files(dataset, include_deleted=include_deleted)

    # Get all captures associated with the dataset
    dataset_captures = get_dataset_captures(dataset, include_deleted=include_deleted)

    # Union querysets can't be used directly in __in lookups, so evaluate to list of IDs
    capture_ids = list(dataset_captures.values_list('uuid', flat=True))

    if not capture_ids:
        # No captures, return just the dataset files
        return dataset_files

    # Get files from those captures (support both M2M and FK on files)
    # M2M relationship: files.captures
    capture_files_m2m = File.objects.filter(captures__uuid__in=capture_ids)
    if not include_deleted:
        capture_files_m2m = capture_files_m2m.filter(is_deleted=False)

    # FK relationship: files.capture (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    capture_files_fk = File.objects.filter(capture__uuid__in=capture_ids)
    if not include_deleted:
        capture_files_fk = capture_files_fk.filter(is_deleted=False)

    capture_files = capture_files_m2m.union(capture_files_fk)

    # Combine all file querysets
    files_union = dataset_files.union(capture_files)
    return union_to_queryset(files_union, File)


def get_files_for_captures(
    captures: QuerySet[Capture], *, is_deleted: bool = False
) -> QuerySet[File]:
    """
    Get all files associated with a queryset of captures via both M2M and FK relationships.

    Args:
        captures: QuerySet of captures to get files for
        is_deleted: If True, include deleted files. If False (default), exclude deleted files.

    Returns:
        QuerySet of files associated with the captures
    """
    # Get files via M2M relationship
    files_m2m = File.objects.filter(captures__in=captures)
    if not is_deleted:
        files_m2m = files_m2m.filter(is_deleted=False)

    # Get files via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    files_fk = File.objects.filter(capture__in=captures)
    if not is_deleted:
        files_fk = files_fk.filter(is_deleted=False)

    # Combine both querysets
    files_union = files_m2m.union(files_fk)
    return union_to_queryset(files_union, File)


def get_file_captures(file: File, *, include_deleted: bool = False) -> QuerySet[Capture]:
    """
    Get all captures associated with a file via both M2M and FK relationships.

    Args:
        file: The file to get captures for
        include_deleted: If True, include deleted captures. If False (default), exclude deleted captures.

    Returns:
        QuerySet of captures associated with the file
    """
    # Get captures via M2M relationship
    captures_m2m = file.captures.all()
    if not include_deleted:
        captures_m2m = captures_m2m.filter(is_deleted=False)

    # Get captures via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    captures_fk = Capture.objects.none()
    if file.capture is not None:
        captures_fk = Capture.objects.filter(uuid=file.capture.uuid)
        if not include_deleted:
            captures_fk = captures_fk.filter(is_deleted=False)

    # Combine both querysets
    captures_union = captures_m2m.union(captures_fk)
    return union_to_queryset(captures_union, Capture)


def get_file_datasets(file: File, *, include_deleted: bool = False) -> QuerySet[Dataset]:
    """
    Get all datasets associated with a file via both M2M and FK relationships.

    Args:
        file: The file to get datasets for
        include_deleted: If True, include deleted datasets. If False (default), exclude deleted datasets.

    Returns:
        QuerySet of datasets associated with the file
    """
    # Get datasets via M2M relationship
    datasets_m2m = file.datasets.all()
    if not include_deleted:
        datasets_m2m = datasets_m2m.filter(is_deleted=False)

    # Get datasets via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    datasets_fk = Dataset.objects.none()
    if file.dataset is not None:
        datasets_fk = Dataset.objects.filter(uuid=file.dataset.uuid)
        if not include_deleted:
            datasets_fk = datasets_fk.filter(is_deleted=False)

    # Combine both querysets
    datasets_union = datasets_m2m.union(datasets_fk)
    return union_to_queryset(datasets_union, Dataset)


def get_capture_datasets(capture: Capture, *, include_deleted: bool = False) -> QuerySet[Dataset]:
    """
    Get all datasets associated with a capture via both M2M and FK relationships.

    Args:
        capture: The capture to get datasets for
        include_deleted: If True, include deleted datasets. If False (default), exclude deleted datasets.

    Returns:
        QuerySet of datasets associated with the capture
    """
    # Get datasets via M2M relationship
    datasets_m2m = capture.datasets.all()
    if not include_deleted:
        datasets_m2m = datasets_m2m.filter(is_deleted=False)

    # Get datasets via FK relationship (deprecated, for backward compatibility)
    # TODO: remove this after migration (expand -> contract)
    datasets_fk = Dataset.objects.none()
    if capture.dataset is not None:
        datasets_fk = Dataset.objects.filter(uuid=capture.dataset.uuid)
        if not include_deleted:
            datasets_fk = datasets_fk.filter(is_deleted=False)

    # Combine both querysets
    datasets_union = datasets_m2m.union(datasets_fk)
    return union_to_queryset(datasets_union, Dataset)

