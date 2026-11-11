from django.shortcuts import render
from django.views.decorators.http import require_GET

from .selectors import price_date_range


@require_GET
def dashboard(request):
    start, end = price_date_range()
    return render(request, "portfolios/dashboard.html", {
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
    })
