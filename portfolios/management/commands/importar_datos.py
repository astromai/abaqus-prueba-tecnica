from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from portfolios.services import ImportDataError, import_workbook


class Command(BaseCommand):
    help = "Importa los pesos iniciales y los precios históricos desde un archivo Excel."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=Path, nargs="?", default=settings.BASE_DIR / "datos.xlsx")

    def handle(self, *args, **options):
        try:
            assets, portfolios, prices = import_workbook(options["archivo"])
        except ImportDataError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(self.style.SUCCESS(
            f"Carga completada: {assets} activos, {portfolios} portafolios y {prices} precios."
        ))
