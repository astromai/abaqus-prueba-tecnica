from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from xml.etree import ElementTree
from zipfile import ZipFile

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Asset, Portfolio, Position, Price
from .services import ImportDataError, import_workbook


class PortfolioIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workbook = settings.BASE_DIR / "datos.xlsx"
        call_command("importar_datos", stdout=StringIO())

    def evolution(self, start="2022-02-15", end="2023-02-16"):
        return self.client.get(reverse("portfolios:evolution"), {"fecha_inicio": start, "fecha_fin": end})

    def test_reload_is_idempotent(self):
        self.assertEqual(import_workbook(self.workbook), (17, 2, 6239))
        self.assertEqual(Asset.objects.count(), 17)
        self.assertEqual(Portfolio.objects.count(), 2)
        self.assertEqual(Position.objects.count(), 34)
        self.assertEqual(Price.objects.count(), 6239)

    def test_reload_updates_existing_prices(self):
        Price.objects.filter(asset__name="EEUU", date="2022-02-15").update(value=1)
        import_workbook(self.workbook)
        price = Price.objects.get(asset__name="EEUU", date="2022-02-15")
        self.assertEqual(price.value, Decimal("9383.57"))
        self.assertEqual(Price.objects.count(), 6239)

    def test_rejects_invalid_workbook_without_mutating_data(self):
        invalid_workbook = BytesIO()
        with ZipFile(self.workbook) as original, ZipFile(invalid_workbook, "w") as modified:
            for member in original.namelist():
                content = original.read(member)
                if member == "xl/worksheets/sheet1.xml":
                    sheet = ElementTree.fromstring(content)
                    sheet.find(".//{*}c[@r='C2']/{*}v").text = "0.25"
                    content = ElementTree.tostring(sheet)
                modified.writestr(member, content)
        with self.assertRaisesMessage(ImportDataError, "deben sumar 1"):
            import_workbook(invalid_workbook)
        self.assertEqual(Price.objects.get(asset__name="EEUU", date="2022-02-15").value, Decimal("9383.57"))
        self.assertEqual(Position.objects.get(portfolio__code=1, asset__name="EEUU").initial_weight, Decimal("0.28"))

    def test_initial_positions_and_zero_weights(self):
        response = self.client.get(reverse("portfolios:positions"))
        self.assertEqual(response.status_code, 200)
        first, second = response.json()["portafolios"]
        for portfolio in (first, second):
            positions = {row["activo"]: row for row in portfolio["posiciones"]}
            self.assertEqual(len(positions), 17)
            self.assertEqual(sum(Decimal(row["monto_inicial"]) for row in positions.values()), 1_000_000_000)
            self.assertEqual(positions["EEUU"]["cantidad"], "29839.389486091115")
        self.assertEqual(positions["High Yield"]["cantidad"], "0.000000000000")

    def test_full_evolution_reconciles_initial_and_final_values(self):
        with self.assertNumQueries(4):
            response = self.evolution()
        self.assertEqual(response.status_code, 200)
        for portfolio, final_value in zip(
            response.json()["portafolios"], ("929055490.74", "923548704.77"), strict=True
        ):
            series = portfolio["serie"]
            self.assertEqual(len(series), 367)
            self.assertEqual(series[0]["fecha"], "2022-02-15")
            self.assertEqual(series[0]["valor_total"], "1000000000.00")
            self.assertEqual(series[-1]["fecha"], "2023-02-16")
            self.assertEqual(series[-1]["valor_total"], final_value)
            for point in series:
                self.assertEqual(len(point["pesos"]), 17)
                total = sum(Decimal(weight) for weight in point["pesos"].values())
                self.assertAlmostEqual(total, Decimal(1), places=10)

    def test_range_is_inclusive_and_quantities_stay_fixed(self):
        response = self.evolution("2022-02-16", "2022-02-16")
        for portfolio in response.json()["portafolios"]:
            (point,) = portfolio["serie"]
            self.assertEqual(point["fecha"], "2022-02-16")
            amount = Decimal("280000000") * Decimal("9393.09") / Decimal("9383.57")
            estimated_amount = Decimal(point["pesos"]["EEUU"]) * Decimal(point["valor_total"])
            self.assertLess(abs(amount - estimated_amount), Decimal(".01"))

    def test_invalid_range_returns_400_and_empty_range_returns_200(self):
        self.assertEqual(self.client.get(reverse("portfolios:evolution")).status_code, 400)
        for start, end in (("20220215", "2022-02-16"), ("2022-02-30", "2022-03-01"), ("2022-02-16", "2022-02-15")):
            with self.subTest(start=start, end=end):
                self.assertEqual(self.evolution(start, end).status_code, 400)
        response = self.evolution("2024-01-01", "2024-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["portafolios"], [{"id": 1, "serie": []}, {"id": 2, "serie": []}])

    def test_missing_price_prevents_partial_valuation(self):
        Price.objects.filter(date=date(2022, 2, 16), asset__name="EEUU").delete()
        response = self.evolution("2022-02-16", "2022-02-16")
        self.assertEqual(response.status_code, 409)
        self.assertIn("EEUU", response.json()["error"])

    def test_dashboard_uses_api_urls_and_loaded_date_bounds(self):
        response = self.client.get(reverse("portfolios:dashboard"))
        self.assertContains(response, reverse("portfolios:evolution"))
        self.assertContains(response, reverse("portfolios:positions"))
        self.assertContains(response, 'min="2022-02-15" max="2023-02-16"')
