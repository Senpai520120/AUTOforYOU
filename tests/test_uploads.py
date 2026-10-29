"""Сервис безопасной загрузки изображений core/uploads.py (задача 1.10, 13-S8)."""
import io
import re
import shutil
import tempfile

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image, ImageCms

from core.uploads import ImageUploadError, sanitize_image, validate_image_upload

UUID_NAME = re.compile(r'^[0-9a-f]{32}\.(jpg|png|webp)$')
GPS_IFD = 0x8825
ORIENTATION = 0x0112


def image_bytes(fmt='JPEG', size=(60, 40), mode='RGB', gps=False, orientation=None, **save_kw):
    img = Image.new(mode, size, color=(200, 100, 50) if mode == 'RGB' else 128)
    exif = Image.Exif()
    if gps:
        exif[0x010F] = 'PhoneMaker'
        exif.get_ifd(GPS_IFD).update({1: 'N', 2: (50.0, 27.0, 0.0), 3: 'E', 4: (30.0, 31.0, 0.0)})
    if orientation:
        exif[ORIENTATION] = orientation
    buf = io.BytesIO()
    if gps or orientation:
        save_kw['exif'] = exif.tobytes()
    img.save(buf, format=fmt, **save_kw)
    return buf.getvalue()


def upload(data, name='photo.jpg', content_type='image/jpeg'):
    return SimpleUploadedFile(name, data, content_type=content_type)


def use_temp_media(testcase):
    """MEDIA_ROOT/PRIVATE_MEDIA_ROOT во временные папки: тесты не засоряют media/."""
    media, private = tempfile.mkdtemp(), tempfile.mkdtemp()
    for d in (media, private):
        testcase.addCleanup(shutil.rmtree, d, ignore_errors=True)
    ov = override_settings(MEDIA_ROOT=media, PRIVATE_MEDIA_ROOT=private)
    ov.enable()
    testcase.addCleanup(ov.disable)
    return media


def admin_form_data(form, inline_admin_formsets=()):
    """POST-данные change-формы админки из уже отрисованной страницы (форма + inline)."""
    data = {}

    def add(bf):
        if isinstance(bf.field, forms.FileField):
            return
        value = bf.value()
        if value is None:
            return
        if isinstance(bf.field.widget, forms.MultiWidget):
            for i, part in enumerate(bf.field.widget.decompress(value)):
                if part is not None:
                    data[f'{bf.html_name}_{i}'] = part
        elif isinstance(value, bool):
            if value:
                data[bf.html_name] = 'on'
        else:
            data[bf.html_name] = value

    for bf in form:
        add(bf)
    for inline in inline_admin_formsets:
        formset = inline.formset
        for bf in formset.management_form:
            data[bf.html_name] = bf.value()
        for f in formset.forms:
            for bf in f:
                add(bf)
    return data


def reopen(content):
    return Image.open(io.BytesIO(content.read() if hasattr(content, 'read') else content))


class SanitizeImageTests(SimpleTestCase):
    def test_gps_exif_removed(self):
        src = image_bytes(gps=True)
        self.assertIn(GPS_IFD, Image.open(io.BytesIO(src)).getexif())  # исходник с GPS
        out = reopen(sanitize_image(upload(src)))
        self.assertEqual(dict(out.getexif()), {})
        self.assertNotIn(GPS_IFD, out.getexif())
        self.assertNotIn('exif', out.info)

    def test_png_icc_and_metadata_not_carried(self):
        # PNG-плагин Pillow сам переносит icc_profile из исходника: новый кадр — только пиксели.
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        src = image_bytes('PNG', icc_profile=icc)
        self.assertIn('icc_profile', Image.open(io.BytesIO(src)).info)
        out = reopen(sanitize_image(upload(src, 'x.png')))
        self.assertNotIn('icc_profile', out.info)

    def test_orientation_applied(self):
        # Orientation=6: повернуть на 90°, ширина и высота меняются местами.
        out = reopen(sanitize_image(upload(image_bytes(size=(60, 40), orientation=6))))
        self.assertEqual(out.size, (40, 60))

    def test_png_stays_png(self):
        content = sanitize_image(upload(image_bytes('PNG'), 'x.png'))
        self.assertEqual(reopen(content).format, 'PNG')
        self.assertTrue(content.name.endswith('.png'))

    def test_webp_stays_webp(self):
        content = sanitize_image(upload(image_bytes('WEBP'), 'x.webp'))
        self.assertEqual(reopen(content).format, 'WEBP')
        self.assertTrue(content.name.endswith('.webp'))

    def test_name_is_uuid_with_real_extension(self):
        # PNG под именем .jpg: расширение — по реальному формату, исходное имя не сохраняется.
        content = sanitize_image(upload(image_bytes('PNG'), 'my-home-address.jpg'))
        self.assertRegex(content.name, UUID_NAME)
        self.assertTrue(content.name.endswith('.png'))
        self.assertNotIn('my-home', content.name)

    def test_subdir_prefix(self):
        content = sanitize_image(upload(image_bytes()), subdir='local_listings')
        self.assertRegex(content.name, r'^local_listings/[0-9a-f]{32}\.jpg$')

    def test_gif_rejected(self):
        with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'):
            sanitize_image(upload(image_bytes('GIF', mode='L'), 'a.gif', 'image/gif'))

    def test_svg_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'):
            sanitize_image(upload(svg, 'a.svg', 'image/svg+xml'))

    def test_html_with_jpg_extension_rejected(self):
        with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'):
            sanitize_image(upload(b'<html><script>alert(1)</script></html>', 'x.jpg'))

    def test_text_with_image_content_type_rejected(self):
        with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'):
            sanitize_image(upload(b'just some text', 'x.txt', 'image/jpeg'))

    def test_truncated_jpeg_rejected(self):
        data = image_bytes(size=(300, 300))
        with self.assertRaisesMessage(ImageUploadError, 'пошкоджений'):
            sanitize_image(upload(data[: len(data) // 2]))

    def test_disallowed_format_by_setting(self):
        with override_settings(UPLOAD_IMAGE_ALLOWED_FORMATS=['JPEG']):
            with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'):
                sanitize_image(upload(image_bytes('PNG'), 'x.png'))

    @override_settings(UPLOAD_IMAGE_MAX_SIZE_MB=1)
    def test_file_over_size_limit_rejected(self):
        big = upload(b'\xff\xd8' + b'0' * (1024 * 1024))
        with self.assertRaisesMessage(ImageUploadError, 'завеликий'):
            sanitize_image(big)

    def test_explicit_max_bytes(self):
        data = image_bytes()
        with self.assertRaisesMessage(ImageUploadError, 'завеликий'):
            sanitize_image(upload(data), max_bytes=len(data) - 1)
        self.assertRegex(sanitize_image(upload(data), max_bytes=len(data)).name, UUID_NAME)

    @override_settings(UPLOAD_IMAGE_MAX_PIXELS=1000)
    def test_too_many_pixels_rejected(self):
        with self.assertRaisesMessage(ImageUploadError, 'роздільністю'):
            sanitize_image(upload(image_bytes(size=(40, 30))))  # 1200 > 1000

    def _pillow_limit(self, value):
        # Глобальный предохранитель Pillow задаётся при импорте core.uploads — восстанавливаем.
        self.addCleanup(setattr, Image, 'MAX_IMAGE_PIXELS', Image.MAX_IMAGE_PIXELS)
        Image.MAX_IMAGE_PIXELS = value

    def test_decompression_bomb_rejected(self):
        # > 2 × MAX_IMAGE_PIXELS: Pillow падает уже на open(), до проверки настройки.
        self._pillow_limit(1000)
        with self.assertRaisesMessage(ImageUploadError, 'роздільністю'):
            sanitize_image(upload(image_bytes(size=(100, 100))))

    def test_pillow_warning_zone_rejected(self):
        # Между MAX и 2×MAX Pillow только предупреждает — у нас это отказ.
        self._pillow_limit(1000)
        with self.assertRaisesMessage(ImageUploadError, 'роздільністю'):
            sanitize_image(upload(image_bytes(size=(40, 30))))

    def test_pillow_limit_set_on_import(self):
        from django.conf import settings

        self.assertEqual(Image.MAX_IMAGE_PIXELS, settings.UPLOAD_IMAGE_MAX_PIXELS)

    # ─── Метаданные и хвосты не выживают ──────────────────────────────────────

    def test_png_text_chunks_removed(self):
        from PIL import PngImagePlugin

        meta = PngImagePlugin.PngInfo()
        meta.add_text('Comment', '<script>alert(1)</script>')
        meta.add_itxt('Location', 'Kyiv, home address', zip=True)
        buf = io.BytesIO()
        Image.new('RGB', (20, 20), (1, 2, 3)).save(buf, format='PNG', pnginfo=meta)
        self.assertIn('Comment', Image.open(io.BytesIO(buf.getvalue())).info)
        content = sanitize_image(upload(buf.getvalue(), 'x.png'))
        raw = content.read()
        out = Image.open(io.BytesIO(raw))
        self.assertNotIn('Comment', out.info)
        self.assertNotIn('Location', out.info)
        for marker in (b'tEXt', b'iTXt', b'zTXt', b'<script'):
            self.assertNotIn(marker, raw)

    def test_xmp_removed_jpeg_and_webp(self):
        xmp = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><GPSLatitude>50.45</GPSLatitude></x:xmpmeta>'
        for fmt in ('JPEG', 'WEBP'):
            with self.subTest(fmt=fmt):
                src = image_bytes(fmt, xmp=xmp)
                self.assertIn('xmp', Image.open(io.BytesIO(src)).info)
                raw = sanitize_image(upload(src, f'x.{fmt.lower()}')).read()
                self.assertNotIn('xmp', Image.open(io.BytesIO(raw)).info)
                self.assertNotIn(b'GPSLatitude', raw)
                self.assertNotIn(b'xmpmeta', raw)

    def test_polyglot_jpeg_with_html_tail_cleaned(self):
        tail = b'<html><script>alert(document.cookie)</script></html>'
        src = image_bytes() + tail
        raw = sanitize_image(upload(src)).read()
        self.assertNotIn(b'<script', raw)
        self.assertNotIn(b'<html', raw)
        self.assertEqual(Image.open(io.BytesIO(raw)).format, 'JPEG')

    def test_jpeg_comment_removed(self):
        src = image_bytes(comment=b'<script>alert(1)</script>')
        self.assertIn(b'<script', src)
        self.assertNotIn(b'<script', sanitize_image(upload(src)).read())

    def test_empty_file_rejected(self):
        with self.assertRaisesMessage(ImageUploadError, 'порожній'):
            sanitize_image(upload(b''))

    def test_animated_webp_rejected(self):
        frames = [Image.new('RGB', (10, 10), c) for c in ((255, 0, 0), (0, 255, 0))]
        buf = io.BytesIO()
        frames[0].save(buf, format='WEBP', save_all=True, append_images=frames[1:])
        with self.assertRaisesMessage(ImageUploadError, 'Анімовані'):
            sanitize_image(upload(buf.getvalue(), 'a.webp'))


class ValidateImageUploadTests(SimpleTestCase):
    def test_invalid_raises_validation_error(self):
        with self.assertRaisesMessage(ValidationError, 'не є зображенням'):
            validate_image_upload(upload(b'<html></html>'))

    def test_valid_passes_and_rewinds(self):
        f = upload(image_bytes())
        validate_image_upload(f)
        self.assertEqual(f.tell(), 0)


class PrivateStorageTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_private_storage_follows_setting(self):
        from core.uploads import PrivateMediaStorage

        with override_settings(PRIVATE_MEDIA_ROOT=self.tmp):
            storage = PrivateMediaStorage()
            name = storage.save('tracking_photos/a.jpg', io.BytesIO(b'x'))
            self.assertTrue(storage.path(name).startswith(self.tmp))
            # URL — internal-location nginx, не /media/.
            self.assertTrue(storage.url(name).startswith('/protected-media/'))
