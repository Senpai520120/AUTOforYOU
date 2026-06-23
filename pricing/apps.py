from django.apps import AppConfig


class PricingConfig(AppConfig):
    name = 'pricing'

    def ready(self):
        import pricing.signals  # noqa: F401
