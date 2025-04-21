import datetime
from typing import Any
from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models.query import QuerySet as Queryset
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView
from django.views.generic import RedirectView
from django.views.generic import UpdateView

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.users.mixins import ApprovedUserRequiredMixin
from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

from sds_gateway.api_methods.models import Capture
#from sds_gateway.api_methods.serializers import CaptureGetSerializer
# new
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer



class UserDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    slug_field = "id"
    slug_url_arg = "id"


user_detail_view = UserDetailView.as_view()


class UserUpdateView(Auth0LoginRequiredMixin, SuccessMessageMixin, UpdateView):  # pyright: ignore[reportMissingTypeArgument]
    model = User
    fields = ["name"]
    success_message = _("Information successfully updated")

    def get_success_url(self):
        # for mypy to know that the user is authenticated
        assert self.request.user.is_authenticated
        return self.request.user.get_absolute_url()

    def get_object(self, queryset=None) -> AbstractBaseUser | AnonymousUser:
        return self.request.user


user_update_view = UserUpdateView.as_view()


class UserRedirectView(Auth0LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self):
        return reverse("users:generate_api_key")


user_redirect_view = UserRedirectView.as_view()


class GenerateAPIKeyView(ApprovedUserRequiredMixin, Auth0LoginRequiredMixin, View):
    template_name = "users/user_api_key.html"

    def get(self, request, *args, **kwargs):
        # check if API key expired
        api_key = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .first()
        )
        if api_key is None:
            return render(
                request,
                template_name=self.template_name,
                context={
                    "api_key": False,
                    "expires_at": None,
                    "expired": False,
                },
            )

        return render(
            request,
            template_name=self.template_name,
            context={
                "api_key": True,  # return True if API key exists
                "expires_at": api_key.expiry_date.strftime("%Y-%m-%d %H:%M:%S")
                if api_key.expiry_date
                else "Does not expire",
                "expired": api_key.expiry_date < datetime.datetime.now(datetime.UTC)
                if api_key.expiry_date
                else False,
            },
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Regenerates an API key for the authenticated user."""
        existing_api_key = (
            UserAPIKey.objects.filter(user=request.user)
            .exclude(source=KeySources.SVIBackend)
            .first()
        )
        if existing_api_key:
            existing_api_key.delete()

        # create an API key for the user (with no expiration date for now)
        _, raw_key = UserAPIKey.objects.create_key(
            name=request.user.email,
            user=request.user,
            source=KeySources.SDSWebUI,
        )
        return render(
            request,
            template_name=self.template_name,
            context={
                "api_key": raw_key,  # key only returned when API key is created
                "expires_at": None,
                "expired": False,
            },
        )


user_generate_api_key_view = GenerateAPIKeyView.as_view()


class ListFilesView(Auth0LoginRequiredMixin, View):
    template_name = "users/file_list.html"
    items_per_page = 25

    def get(self, request, *args, **kwargs) -> HttpResponse:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        sort_by = request.GET.get('sort_by', 'created_at')
        sort_order = request.GET.get('sort_order', 'desc')
        
        # Get filter parameters
        search = request.GET.get('search', '')
        date_start = request.GET.get('date_start', '')
        date_end = request.GET.get('date_end', '')
        center_freq = request.GET.get('center_freq', '')
        bandwidth = request.GET.get('bandwidth', '')
        location = request.GET.get('location', '')

        # Base queryset
        files_qs = request.user.files.filter(is_deleted=False)

        # Apply search filter
        if search:
            files_qs = files_qs.filter(name__icontains=search)

        # Apply date range filter
        if date_start:
            files_qs = files_qs.filter(created_at__gte=date_start)
        if date_end:
            files_qs = files_qs.filter(created_at__lte=date_end)

        # Apply other filters
        if center_freq:
            files_qs = files_qs.filter(center_frequency=center_freq)
        if bandwidth:
            files_qs = files_qs.filter(bandwidth=bandwidth)
        if location:
            files_qs = files_qs.filter(location=location)

        # Handle sorting
        if sort_by:
            if sort_order == 'desc':
                files_qs = files_qs.order_by(f'-{sort_by}')
            else:
                files_qs = files_qs.order_by(sort_by)

        # Paginate the results
        paginator = Paginator(files_qs, self.items_per_page)
        try:
            files_page = paginator.page(page)
        except:
            files_page = paginator.page(1)

        return render(
            request,
            template_name=self.template_name,
            context={
                'files': files_page,
                'total_pages': paginator.num_pages,
                'current_page': page,
                'total_items': paginator.count,
                'sort_by': sort_by,
                'sort_order': sort_order
            },
        )


user_file_list_view = ListFilesView.as_view()


class FileDetailView(Auth0LoginRequiredMixin, DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = File
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    template_name = "users/file_detail.html"

    def get_queryset(self) -> Queryset[File]:
        return self.request.user.files.filter(is_deleted=False).all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target_file = cast("File", self.get_object())
        if target_file is None:
            return context
        serializer = FileGetSerializer(target_file)
        context["returning_page"] = self.request.GET.get("returning_page", default=1)
        context["file"] = serializer.data
        context["skip_fields"] = [
            "bucket_name",
            "deleted_at",
            "file",
            "is_deleted",
            "name",
        ]
        return context


user_file_detail_view = FileDetailView.as_view()

class ListCapturesView(Auth0LoginRequiredMixin, View):
    template_name = "users/file_list.html"    
    items_per_page = 25

    def get(self, request, *args, **kwargs) -> HttpResponse:
       
        page       = int(request.GET.get("page", 1))
        sort_by    = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        search     = request.GET.get("search", "")
        date_start = request.GET.get("date_start", "")
        date_end   = request.GET.get("date_end", "")
        cap_type   = request.GET.get("capture_type", "")

       
        qs = request.user.captures.filter(is_deleted=False)

        # 3) apply filters
        if search:
            qs = qs.filter(channel__icontains=search)
        if date_start:
            qs = qs.filter(created_at__gte=date_start)
        if date_end:
            qs = qs.filter(created_at__lte=date_end)
        if cap_type:
            qs = qs.filter(capture_type=cap_type)

        # 4) apply sorting
        if sort_order == "desc":
            qs = qs.order_by(f"-{sort_by}")
        else:
            qs = qs.order_by(sort_by)

     
        paginator = Paginator(qs, self.items_per_page)
        try:
            page_obj = paginator.page(page)
        except:
            page_obj = paginator.page(1)


        serializer = CaptureGetSerializer(
            page_obj, many=True, context={"request": request}
        )


        return render(
            request,
            self.template_name,
            {
                "captures":       page_obj,
                "captures_data":  serializer.data,
                "sort_by":        sort_by,
                "sort_order":     sort_order,
                "search":         search,
                "date_start":     date_start,
                "date_end":       date_end,
                "capture_type":   cap_type,
            },
        )



user_capture_list_view = ListCapturesView.as_view()

