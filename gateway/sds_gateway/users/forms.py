from pathlib import Path

from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django import forms
from django.conf import settings
from django.contrib.auth import forms as admin_forms
from django.core.exceptions import ValidationError
from django.forms import EmailField
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from sds_gateway.api_methods.models import File

from .models import User

# Constants for validation
MIN_DATASET_NAME_LENGTH = 0
MIN_AUTHOR_NAME_LENGTH = 0

# Error messages
DATASET_NAME_LENGTH_ERROR = "Dataset name is required."
AUTHOR_NAME_LENGTH_ERROR = "Author name is required."


class UserAdminChangeForm(admin_forms.UserChangeForm):  # pyright: ignore[reportMissingTypeArgument]
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore[name-defined]
        model = User
        field_classes = {"email": EmailField}


class UserAdminCreationForm(admin_forms.UserCreationForm):  # pyright: ignore[reportMissingTypeArgument]
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):  # type: ignore[name-defined]
        model = User
        fields = ("email",)
        field_classes = {"email": EmailField}
        error_messages = {
            "email": {"unique": _("This email has already been taken.")},
        }


class UserSignupForm(SignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    See ACCOUNT_FORMS in settings.
    """

    def save(self, request: HttpRequest) -> User:
        user = super().save(request)
        user.is_approved = settings.SDS_NEW_USERS_APPROVED_ON_CREATION
        user.save()
        return user


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically. See UserSignupForm otherwise.
    See SOCIALACCOUNT_FORMS in settings.
    """

    def save(self, request: HttpRequest) -> User:
        user = super().save(request)
        user.is_approved = settings.SDS_NEW_USERS_APPROVED_ON_CREATION
        user.save()
        return user


class DatasetInfoForm(forms.Form):
    name = forms.CharField(
        label="Name",
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        label="Description",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5}),
    )
    author = forms.CharField(
        label="Author",
        required=True,
        disabled=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields["author"].initial = user.name

    def clean_name(self):
        """Validate the dataset name."""
        name = self.cleaned_data["name"]
        if len(name.strip()) < MIN_DATASET_NAME_LENGTH:
            raise ValidationError(DATASET_NAME_LENGTH_ERROR)

        return name.strip()

    def clean_author(self):
        """Validate the author name."""
        author = self.cleaned_data["author"]
        if len(author.strip()) < MIN_AUTHOR_NAME_LENGTH:
            raise ValidationError(AUTHOR_NAME_LENGTH_ERROR)
        return author.strip()

    def clean_description(self):
        """Clean and validate the description."""
        return self.cleaned_data.get("description", "").strip()


class CaptureSearchForm(forms.Form):
    directory = forms.CharField(
        label="Top Level Directory",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "search_directory_captures",
                "placeholder": "Search by directory",
            }
        ),
    )
    capture_type = forms.ChoiceField(
        label="Capture Type",
        required=False,
        choices=[("", "All Types"), ("drf", "DigitalRF"), ("rh", "RadioHound")],
        widget=forms.Select(
            attrs={"class": "form-select", "id": "search_capture_type"}
        ),
    )
    scan_group = forms.CharField(
        label="Scan Group",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "search_scan_group",
                "placeholder": "Search by scan group",
            }
        ),
    )
    channel = forms.CharField(
        label="Channel",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "search_channel",
                "placeholder": "Search by channel",
            }
        ),
    )


class FileSearchForm(forms.Form):
    file_name = forms.CharField(
        label="File Name",
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "id": "file-search",
                "placeholder": "Enter file name...",
            }
        ),
    )
    directory = forms.CharField(
        label="Directory",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "directory"}),
    )
    file_extension = forms.ChoiceField(
        label="File Extension",
        required=False,
        choices=[("", "All Extensions")],  # Default empty choice
        widget=forms.Select(attrs={"class": "form-select", "id": "file-extension"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            # Get distinct file extensions from user's files
            extensions = (
                File.objects.filter(owner=user, is_deleted=False)
                .exclude(name="")
                .values_list("name", flat=True)
                .distinct()
            )

            # Extract unique extensions
            unique_extensions = {
                Path(name).suffix.lower()
                for name in extensions
                if Path(name).suffix.lower()
            }

            # Sort extensions and create choices list
            extension_choices = [("", "All Extensions")] + [
                (ext, ext) for ext in sorted(unique_extensions)
            ]

            self.fields["file_extension"].choices = extension_choices
