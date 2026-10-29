"""Перенос згод уже створених заявок у журнал (1.14). Версія документів тоді не фіксувалась -> порожня."""
from django.db import migrations


def backfill(apps, schema_editor):
    Lead = apps.get_model('leads', 'Lead')
    ConsentRecord = apps.get_model('users', 'ConsentRecord')
    batch = []
    for lead in Lead.objects.filter(consent_records__isnull=True).iterator():
        batch.append(ConsentRecord(
            user_id=lead.user_id, lead_id=lead.pk, lead_public_id=lead.public_id, document='lead_processing', doc_version='',
            given_at=lead.consent_at, method='lead_form',
        ))
        if lead.partner_consent_at:
            batch.append(ConsentRecord(
                user_id=lead.user_id, lead_id=lead.pk, lead_public_id=lead.public_id, document='partner_transfer', doc_version='',
                partner_name=lead.partner_name, given_at=lead.partner_consent_at, method='lead_form',
            ))
        if len(batch) >= 500:
            ConsentRecord.objects.bulk_create(batch)
            batch = []
    if batch:
        ConsentRecord.objects.bulk_create(batch)


class Migration(migrations.Migration):
    dependencies = [('users', '0013_consentrecord')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
