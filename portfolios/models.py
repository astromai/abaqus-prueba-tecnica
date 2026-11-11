from django.db import models


class Asset(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Portfolio(models.Model):
    code = models.PositiveSmallIntegerField(unique=True)
    inception_date = models.DateField()
    initial_value = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(initial_value__gt=0), name="portfolio_positive_value"),
        ]

    def __str__(self):
        return f"Portafolio {self.code}"


class Price(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    date = models.DateField()
    value = models.DecimalField(max_digits=15, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["date", "asset"], name="price_unique_date_asset"),
            models.CheckConstraint(condition=models.Q(value__gt=0), name="price_positive_value"),
        ]


class Position(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    initial_weight = models.DecimalField(max_digits=13, decimal_places=12)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["portfolio", "asset"], name="position_unique_portfolio_asset"),
            models.CheckConstraint(
                condition=models.Q(initial_weight__gte=0, initial_weight__lte=1),
                name="position_weight_in_range",
            ),
        ]
