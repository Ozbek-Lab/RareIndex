from lab import views
from django.urls import path

app_name = "lab"

urlpatterns = [path("", views.index, name="index")]

urlpatterns += views.IndividualView.get_urls()
urlpatterns += views.SampleView.get_urls()
