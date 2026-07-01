from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.storage import staticfiles_storage
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("", include("lab.urls")),
    path('inbox/notifications/', include('notifications.urls', namespace='notifications')),
    path(
        "favicon.ico",
        RedirectView.as_view(
            url=staticfiles_storage.url("img/favicon.ico"),
            permanent=True,
        ),
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

