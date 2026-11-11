import re
from datetime import date

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .selectors import IncompletePriceSeries, portfolio_evolution, portfolio_positions


def _parse_date(query, key):
    values = query.getlist(key)
    if len(values) == 1 and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", values[0]):
        try:
            return date.fromisoformat(values[0])
        except ValueError:
            pass
    raise ValueError(f"{key} debe indicar una fecha válida en formato YYYY-MM-DD.")


@require_GET
def positions_api(request):
    try:
        portfolios = portfolio_positions()
    except IncompletePriceSeries as error:
        return JsonResponse({"error": str(error)}, status=409)

    for portfolio in portfolios:
        portfolio["valor_inicial"] = format(portfolio["valor_inicial"], ".2f")
        portfolio["posiciones"] = [{
            "activo": position["activo"],
            "peso_inicial": format(position["peso_inicial"], ".12f"),
            "precio_inicial": format(position["precio_inicial"], ".8f"),
            "monto_inicial": format(position["monto_inicial"], ".2f"),
            "cantidad": format(position["cantidad"], ".12f"),
        } for position in portfolio["posiciones"]]
    return JsonResponse({"portafolios": portfolios})


@require_GET
def evolution_api(request):
    try:
        start = _parse_date(request.GET, "fecha_inicio")
        end = _parse_date(request.GET, "fecha_fin")
        if start > end:
            raise ValueError("fecha_inicio debe ser anterior o igual a fecha_fin.")
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)

    try:
        portfolios = portfolio_evolution(start=start, end=end)
    except IncompletePriceSeries as error:
        return JsonResponse({"error": str(error)}, status=409)
    for portfolio in portfolios:
        for point in portfolio["serie"]:
            point["valor_total"] = format(point["valor_total"], ".2f")
            point["pesos"] = {asset: format(weight, ".12f") for asset, weight in point["pesos"].items()}
    return JsonResponse({"fecha_inicio": start, "fecha_fin": end, "portafolios": portfolios})
