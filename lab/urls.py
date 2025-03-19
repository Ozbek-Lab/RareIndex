from .views import IndividualView

app_name = "lab"

urlpatterns = []

urlpatterns += IndividualView.get_urls()
