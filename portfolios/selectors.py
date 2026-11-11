from decimal import Decimal, localcontext

from django.db.models import Max, Min, Prefetch

from .models import Portfolio, Position, Price


class IncompletePriceSeries(ValueError):
    """Faltan precios necesarios para valorar un portafolio."""


def price_date_range():
    bounds = Price.objects.aggregate(start=Min("date"), end=Max("date"))
    return bounds["start"], bounds["end"]


def portfolio_positions():
    portfolios = list(Portfolio.objects.order_by("code").prefetch_related(
        Prefetch("position_set", queryset=Position.objects.select_related("asset").order_by("asset__name"))
    ))
    initial_prices = {
        (day, asset_id): value
        for day, asset_id, value in Price.objects.filter(
            date__in={portfolio.inception_date for portfolio in portfolios}
        ).values_list("date", "asset_id", "value")
    }
    results = []
    with localcontext() as context:
        context.prec = 40
        for portfolio in portfolios:
            positions = []
            for position in portfolio.position_set.all():
                price = initial_prices.get((portfolio.inception_date, position.asset_id))
                if price is None:
                    raise IncompletePriceSeries(
                        f"Falta el precio inicial de {position.asset.name} al {portfolio.inception_date}."
                    )
                amount = position.initial_weight * portfolio.initial_value
                positions.append({
                    "activo": position.asset.name,
                    "activo_id": position.asset_id,
                    "peso_inicial": position.initial_weight,
                    "precio_inicial": price,
                    "monto_inicial": amount,
                    "cantidad": amount / price,
                })
            results.append({
                "id": portfolio.code,
                "fecha_inicial": portfolio.inception_date,
                "valor_inicial": portfolio.initial_value,
                "posiciones": positions,
            })
    return results


def portfolio_evolution(*, start, end):
    portfolios = portfolio_positions()
    prices_by_day = {}
    for day, asset_id, price in Price.objects.filter(date__range=(start, end)).order_by("date").values_list(
        "date", "asset_id", "value"
    ):
        prices_by_day.setdefault(day, {})[asset_id] = price

    results = []
    with localcontext() as context:
        context.prec = 40
        for portfolio in portfolios:
            series = []
            positions = portfolio["posiciones"]
            for day, prices in prices_by_day.items():
                if day < portfolio["fecha_inicial"]:
                    continue
                amounts = {}
                for position in positions:
                    price = prices.get(position["activo_id"])
                    if price is None:
                        raise IncompletePriceSeries(f'Falta el precio de {position["activo"]} al {day}.')
                    amounts[position["activo"]] = position["cantidad"] * price
                total = sum(amounts.values(), Decimal(0))
                if total <= 0:
                    raise IncompletePriceSeries(f'El portafolio {portfolio["id"]} no tiene valor positivo al {day}.')
                series.append({
                    "fecha": day,
                    "valor_total": total,
                    "pesos": {asset: amount / total for asset, amount in amounts.items()},
                })
            results.append({"id": portfolio["id"], "serie": series})
    return results
