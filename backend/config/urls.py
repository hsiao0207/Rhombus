"""
Root URL configuration.

`/admin/` is the Django admin and `/api/` is the JSON API (see `datasets/urls.py`).
Everything else, including the built React app, is served by WhiteNoise.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("datasets.urls")),
]
