import datetime

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import User


@shared_task()
def get_users_count():
    """A pointless Celery task to demonstrate usage."""
    return User.objects.count()


@shared_task()
def send_dataset_error_email(
    user_email: str, dataset_name: str, error_message: str
) -> str:
    """
    Send an error email to the user when dataset download fails.

    Args:
        user_email: The user's email address
        dataset_name: The name of the dataset that failed
        error_message: The error message to include

    Returns:
        str: Status message
    """
    try:
        subject = f"Dataset download failed: {dataset_name}"

        # Create email context
        context = {
            "dataset_name": dataset_name,
            "error_message": error_message,
            "requested_at": datetime.datetime.now(datetime.UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
        }

        # Render email template
        html_message = render_to_string("emails/dataset_download_error.html", context)
        plain_message = render_to_string("emails/dataset_download_error.txt", context)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
        )

    except (OSError, ValueError) as e:
        return f"Failed to send error email: {e!s}"
    else:
        return f"Error email sent to {user_email}"
