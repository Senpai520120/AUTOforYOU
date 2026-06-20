from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'amount', 'currency', 'purpose', 'status', 'liqpay_status', 'created_at')
    list_filter = ('status', 'purpose', 'currency')
    search_fields = ('order_id', 'user__email', 'liqpay_payment_id')
    readonly_fields = ('order_id', 'liqpay_payment_id', 'liqpay_status', 'liqpay_raw', 'created_at', 'updated_at')
    raw_id_fields = ('user', 'listing')
