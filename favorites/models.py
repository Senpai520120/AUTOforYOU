from django.conf import settings
from django.db import models


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorites',
    )
    local_listing = models.ForeignKey(
        'local_listings.LocalListing',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='favorited_by',
    )
    imported_listing = models.ForeignKey(
        'listings.Listing',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='favorited_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'local_listing'],
                name='uniq_fav_user_local',
            ),
            models.UniqueConstraint(
                fields=['user', 'imported_listing'],
                name='uniq_fav_user_imported',
            ),
        ]

    def __str__(self):
        obj = self.local_listing or self.imported_listing
        return f'Favorite: {self.user_id} → {obj}'
