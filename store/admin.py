from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Order, OrderItem, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("image_preview", "name", "category", "price", "stock", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    list_editable = ("price", "stock", "is_active")
    readonly_fields = ("image_preview",)

    @admin.display(description="Product image")
    def image_preview(self, product):
        if not product.image_url:
            return "No image URL"
        return format_html(
            '<img src="{}" alt="" style="max-width: 100px; max-height: 90px; object-fit: contain;">',
            product.image_url,
        )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "quantity", "price_at_purchase")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "created_at",
        "total",
        "payment_method",
        "payment_status",
        "status",
    )
    list_filter = ("payment_method", "payment_status", "status", "created_at")
    inlines = [OrderItemInline]
    readonly_fields = ("payment_gateway_order_id", "payment_id")
