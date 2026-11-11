from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile

from django.db import transaction
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import Asset, Portfolio, Position, Price


INITIAL_VALUE = Decimal("1000000000.00")
WEIGHT_PRECISION = Decimal("0.000000000001")
PRICE_PRECISION = Decimal("0.00000001")
PORTFOLIO_COLUMNS = ("portafolio 1", "portafolio 2")


class ImportDataError(ValueError):
    """El archivo no cumple el contrato de importación."""


def _date(value, source):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ImportDataError(f"{source}: se esperaba una fecha de Excel.")


def _number(value, precision, source):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ImportDataError(f"{source}: se esperaba un número.")
    try:
        number = Decimal(str(value))
        if number.is_finite():
            return number.quantize(precision)
    except InvalidOperation:
        pass
    raise ImportDataError(f"{source}: número inválido.")


def _asset_name(value, source):
    if isinstance(value, str) and 0 < len(value.strip()) <= 100:
        return value.strip()
    raise ImportDataError(f"{source}: nombre de activo inválido.")


def _read_weights(sheet):
    rows = sheet.values
    headers = next(rows, ())
    if tuple(headers[:4]) != ("Fecha", "activos", *PORTFOLIO_COLUMNS):
        raise ImportDataError("weights: encabezados inesperados.")

    inception_date = None
    weights = {}
    for index, row in enumerate(rows, start=2):
        if all(value is None for value in row):
            continue
        source = f"weights, fila {index}"
        raw_date, raw_asset, *raw_weights = row[:4]
        row_date = _date(raw_date, source)
        inception_date = inception_date or row_date
        asset = _asset_name(raw_asset, source)
        if row_date != inception_date or asset in weights:
            raise ImportDataError(f"{source}: fecha inicial distinta o activo duplicado.")
        values = tuple(_number(value, WEIGHT_PRECISION, source) for value in raw_weights)
        if any(not 0 <= weight <= 1 for weight in values):
            raise ImportDataError(f"{source}: los pesos deben estar entre 0 y 1.")
        weights[asset] = values

    if not weights or any(sum(column) != 1 for column in zip(*weights.values())):
        raise ImportDataError("weights: los pesos de cada portafolio deben sumar 1.")
    return inception_date, weights


def _read_prices(sheet, expected_assets):
    rows = sheet.values
    headers = next(rows, ())
    if not headers or headers[0] != "Dates":
        raise ImportDataError("Precios: falta el encabezado Dates.")
    assets = [_asset_name(value, "Precios, encabezado") for value in headers[1:]]
    if len(assets) != len(set(assets)) or set(assets) != expected_assets:
        raise ImportDataError("Precios: las columnas deben coincidir con los activos de weights.")

    prices = {}
    for index, row in enumerate(rows, start=2):
        if all(value is None for value in row):
            continue
        source = f"Precios, fila {index}"
        row_date = _date(row[0], source)
        if row_date in prices:
            raise ImportDataError(f"{source}: fecha duplicada.")
        daily_prices = {}
        for asset, value in zip(assets, row[1:], strict=True):
            price = _number(value, PRICE_PRECISION, f"{source}, {asset}")
            if not 0 < price < 10_000_000:
                raise ImportDataError(f"{source}, {asset}: precio fuera del rango permitido.")
            daily_prices[asset] = price
        prices[row_date] = daily_prices
    return prices


def import_workbook(path):
    """Lee y valida el Excel antes de escribir la carga completa en una transacción."""
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (OSError, BadZipFile, InvalidFileException) as error:
        raise ImportDataError(f"No se pudo abrir el Excel: {error}") from error

    try:
        if not {"weights", "Precios"} <= set(workbook.sheetnames):
            raise ImportDataError("Se requieren las hojas weights y Precios.")
        inception_date, weights = _read_weights(workbook["weights"])
        prices = _read_prices(workbook["Precios"], set(weights))
    finally:
        workbook.close()
    if inception_date not in prices:
        raise ImportDataError("Precios: falta la fecha inicial indicada en weights.")

    with transaction.atomic():
        assets = {name: Asset.objects.get_or_create(name=name)[0] for name in weights}
        for index, _column in enumerate(PORTFOLIO_COLUMNS):
            portfolio, _ = Portfolio.objects.update_or_create(
                code=index + 1,
                defaults={"inception_date": inception_date, "initial_value": INITIAL_VALUE},
            )
            for name, values in weights.items():
                Position.objects.update_or_create(
                    portfolio=portfolio,
                    asset=assets[name],
                    defaults={"initial_weight": values[index]},
                )
            Position.objects.filter(portfolio=portfolio).exclude(asset__in=assets.values()).delete()

        price_rows = [
            Price(asset=assets[name], date=day, value=value)
            for day, daily_prices in prices.items()
            for name, value in daily_prices.items()
        ]
        Price.objects.bulk_create(
            price_rows,
            update_conflicts=True,
            update_fields=["value"],
            unique_fields=["date", "asset"],
        )
    return len(assets), len(PORTFOLIO_COLUMNS), len(price_rows)
