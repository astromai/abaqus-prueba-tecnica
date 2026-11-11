from django.urls import include, path


urlpatterns = [path("", include("portfolios.urls"))]
