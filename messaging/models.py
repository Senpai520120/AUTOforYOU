from django.conf import settings
from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    """
    Один діалог на пару (initiator, listing).
    Для місцевих оголошень: покупець ↔ автор.
    Для імпортних: покупець ↔ адмін (всі адміни бачать через queryset).
    Унікальність пари забезпечена UniqueConstraint; NULL != NULL в SQL,
    тому (user, NULL) може повторюватись для різних типів оголошень.
    """
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='initiated_conversations',
    )
    local_listing = models.ForeignKey(
        'local_listings.LocalListing',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversations',
    )
    imported_listing = models.ForeignKey(
        'listings.Listing',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='conversations',
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='conversations',
    )
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_message_at']
        constraints = [
            models.UniqueConstraint(
                fields=['initiator', 'local_listing'],
                name='unique_initiator_local_listing',
            ),
            models.UniqueConstraint(
                fields=['initiator', 'imported_listing'],
                name='unique_initiator_imported_listing',
            ),
        ]

    def __str__(self):
        subject = self.local_listing or self.imported_listing
        return f'Conversation #{self.pk} — {subject}'


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages',
    )
    text = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Message #{self.pk} by {self.sender_id} in conv #{self.conversation_id}'
