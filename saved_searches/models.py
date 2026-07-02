from django.conf import settings
from django.db import models


class SavedSearch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_searches',
    )
    name = models.CharField(max_length=100)
    filters = models.JSONField(help_text='LocalListing filter params (dict)')
    notify = models.BooleanField(default=True, help_text='Надсилати алерти про нові авто')
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'SavedSearch #{self.pk}: {self.name} ({self.user_id})'
