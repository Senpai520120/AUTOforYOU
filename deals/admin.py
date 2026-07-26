from django.contrib import admin

from .models import Deal, Review


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    readonly_fields = ['author', 'target', 'rating', 'text', 'created_at']
    can_delete = False


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ['id', 'listing', 'seller', 'buyer', 'status', 'created_at', 'confirmed_at']
    list_filter = ['status']
    search_fields = ['seller__email', 'buyer__email', 'listing__make']
    raw_id_fields = ['listing', 'seller', 'buyer']
    readonly_fields = ['created_at', 'confirmed_at']
    inlines = [ReviewInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'author', 'target', 'rating', 'created_at']
    list_filter = ['rating']
    search_fields = ['author__email', 'target__email']
    raw_id_fields = ['deal', 'author', 'target']
    readonly_fields = ['created_at']
