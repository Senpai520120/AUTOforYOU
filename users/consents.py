"""Журнал згод (1.14): запис згод з поточною версією документів із SiteSettings."""
import logging

from site_settings.models import SiteSettings

from .models import ConsentDocument, ConsentRecord

logger = logging.getLogger(__name__)


def record_consents(user, documents, method, lead=None, partner_name=''):
    """Пише по запису на кожен документ. user=None для гостя. Викликати всередині
    transaction.atomic створення сутності, щоб відкат не лишав «висячих» записів.
    Контактні дані й IP у запис не потрапляють."""
    if user is not None and not getattr(user, 'is_authenticated', False):
        user = None
    version = SiteSettings.load().legal_docs_version
    if not version:
        logger.warning('consent.version_empty method=%s', method)
    records = []
    for doc in documents:
        ConsentDocument(doc)  # невідомий документ -> ValueError
        records.append(ConsentRecord(
            user=user, lead=lead, lead_public_id=lead.public_id if lead else '', document=doc, doc_version=version,
            partner_name=partner_name if doc == ConsentDocument.PARTNER_TRANSFER else '',
            method=method,
        ))
    return ConsentRecord.objects.bulk_create(records)
