"""local_listings/permissions.py: is_staff_or_admin без атрибута is_admin_role (scripts/mutation.sh posting)."""
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from local_listings.permissions import PhoneVerifiedForPosting, is_staff_or_admin


class IsStaffOrAdminTests(SimpleTestCase):
    def test_user_without_admin_role_attribute_is_not_admin(self):
        user = SimpleNamespace(is_authenticated=True, is_staff=False)
        self.assertIs(is_staff_or_admin(user), False)

    def test_staff_or_admin_role(self):
        self.assertIs(is_staff_or_admin(SimpleNamespace(is_authenticated=True, is_staff=True)), True)
        admin = SimpleNamespace(is_authenticated=True, is_staff=False, is_admin_role=True)
        self.assertIs(is_staff_or_admin(admin), True)
        anon = SimpleNamespace(is_authenticated=False, is_staff=True, is_admin_role=True)
        self.assertIs(is_staff_or_admin(anon), False)


@override_settings(PHONE_VERIFICATION_REQUIRED=True)
class PhoneVerifiedForPostingUnitTests(SimpleTestCase):
    def _allowed(self, user, method='POST'):
        return PhoneVerifiedForPosting().has_permission(SimpleNamespace(method=method, user=user), None)

    def test_anonymous_is_refused_even_with_verified_phone_attr(self):
        anon = SimpleNamespace(is_authenticated=False, is_admin_role=True, phone_verified_at='2026-01-01')
        self.assertIs(self._allowed(anon), False)
        self.assertIs(self._allowed(None), False)

    def test_user_without_admin_role_attr_needs_phone(self):
        self.assertIs(self._allowed(SimpleNamespace(is_authenticated=True, phone_verified_at=None)), False)
        self.assertIs(self._allowed(SimpleNamespace(is_authenticated=True, phone_verified_at='2026-01-01')), True)

    def test_safe_methods_always_allowed(self):
        self.assertIs(self._allowed(None, method='GET'), True)
