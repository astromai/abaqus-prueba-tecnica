from django.urls import path

from .apis import evolution_api, positions_api
from .views import dashboard


app_name = "portfolios"
urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("api/portafolios/posiciones/", positions_api, name="positions"),
    path("api/portafolios/evolucion/", evolution_api, name="evolution"),
]
