"""
LiqPay API client — Python 3.12+.

Реализует протокол LiqPay v3:
  data      = base64(json(params))
  signature = base64(sha1(private_key + data + private_key))

Официальный SDK (liqpay/sdk-python) — Python 2 only, поэтому реализуем
протокол напрямую. Логика идентична SDK (~20 строк).

Ключи из env: LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY.
Sandbox: установить sandbox=1 в параметрах или LIQPAY_SANDBOX=true в env.
"""
import base64
import hashlib
import json
import os


LIQPAY_CHECKOUT_URL = 'https://www.liqpay.com/api/3/checkout'
LIQPAY_API_URL = 'https://www.liqpay.com/api/3/request'


class LiqPaySignatureError(Exception):
    pass


class LiqPayClient:
    def __init__(self, public_key: str, private_key: str, sandbox: bool = False):
        self.public_key = public_key
        self.private_key = private_key
        self.sandbox = sandbox

    @classmethod
    def from_settings(cls) -> 'LiqPayClient':
        return cls(
            public_key=os.environ.get('LIQPAY_PUBLIC_KEY', ''),
            private_key=os.environ.get('LIQPAY_PRIVATE_KEY', ''),
            sandbox=os.environ.get('LIQPAY_SANDBOX', 'false').lower() == 'true',
        )

    # ── Подпись ───────────────────────────────────────────────────────────────

    def _sign(self, data: str) -> str:
        raw = self.private_key + data + self.private_key
        return base64.b64encode(hashlib.sha1(raw.encode('utf-8')).digest()).decode('utf-8')

    def _encode_params(self, params: dict) -> str:
        return base64.b64encode(json.dumps(params, ensure_ascii=False).encode('utf-8')).decode('utf-8')

    # ── Создание чекаута ──────────────────────────────────────────────────────

    def create_checkout(
        self,
        order_id: str,
        amount: str,
        currency: str,
        description: str,
        result_url: str = '',
        server_url: str = '',
    ) -> dict:
        """
        Возвращает dict с полями:
          checkout_url  — ссылка для редиректа покупателя
          form_data     — {data, signature} для HTML-формы
        """
        params = {
            'version': 3,
            'public_key': self.public_key,
            'action': 'pay',
            'amount': str(amount),
            'currency': currency,
            'description': description,
            'order_id': order_id,
            'sandbox': 1 if self.sandbox else 0,
        }
        if result_url:
            params['result_url'] = result_url
        if server_url:
            params['server_url'] = server_url

        data = self._encode_params(params)
        signature = self._sign(data)

        return {
            'checkout_url': f'{LIQPAY_CHECKOUT_URL}?data={data}&signature={signature}',
            'form_data': {'data': data, 'signature': signature},
            'sandbox': self.sandbox,
        }

    # ── Декодирование колбэка ─────────────────────────────────────────────────

    def decode_callback(self, data: str, signature: str) -> dict:
        """
        Проверяет подпись колбэка LiqPay и возвращает распакованные данные.
        Поднимает LiqPaySignatureError при несовпадении подписи.
        """
        expected = self._sign(data)
        if expected != signature:
            raise LiqPaySignatureError(
                'Неверная подпись LiqPay — возможна подделка колбэка.'
            )
        return json.loads(base64.b64decode(data).decode('utf-8'))

    # ── Маппинг статусов LiqPay → внутренний ─────────────────────────────────

    @staticmethod
    def map_status(liqpay_status: str) -> str:
        _MAP = {
            'success': 'completed',
            'sandbox': 'completed',
            'wait_accept': 'pending',
            'processing': 'pending',
            'failure': 'failed',
            'error': 'failed',
            'reversed': 'reversed',
            'subscribed': 'completed',
        }
        return _MAP.get(liqpay_status, 'pending')
