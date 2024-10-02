from django.contrib import admin

from sds_gateway.api_methods import models

# Register your models here.
admin.site.register(models.Capture)
admin.site.register(models.Dataset)
admin.site.register(models.File)
