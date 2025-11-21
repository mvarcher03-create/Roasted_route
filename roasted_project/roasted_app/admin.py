from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.utils.html import mark_safe
from .models import MenuItem, Cart, CartItem, Order, OrderItem, Customer, GCashSettings

# Register your models here.

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'category', 'available', 'stock', 'is_featured', 'created_at', 'image_tag']
    list_filter = ['category', 'available', 'is_featured', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['price', 'available', 'stock', 'is_featured']
    list_per_page = 20
    readonly_fields = ['image_preview']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'price', 'category')
        }),
        ('Inventory & Availability', {
            'fields': ('available', 'stock', 'is_featured')
        }),
        ('Media', {
            'fields': ('image', 'image_preview'),
            'classes': ('collapse',)
        })
    )

    def image_tag(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" style="height: 50px;" />')
        return 'No Image'
    image_tag.short_description = 'Image'

    def image_preview(self, obj):
        if obj and obj.image:
            return mark_safe(f'<img src="{obj.image.url}" style="max-height: 200px;" />')
        return 'No Image'
    image_preview.short_description = 'Image preview'

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'total_items', 'subtotal', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    
    def total_items(self, obj):
        return obj.total_items
    total_items.short_description = 'Total Items'
    
    def subtotal(self, obj):
        return f"₱{obj.subtotal}"
    subtotal.short_description = 'Subtotal'

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'cart', 'menu_item', 'quantity', 'unit_price', 'total_price', 'added_at']
    list_filter = ['added_at']
    search_fields = ['cart__user__username', 'menu_item__name']
    readonly_fields = ['added_at']
    
    def total_price(self, obj):
        return f"₱{obj.total_price}"
    total_price.short_description = 'Total Price'

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['unit_price', 'total_price']
    
    def total_price(self, obj):
        return f"₱{obj.unit_price * obj.quantity}"
    total_price.short_description = 'Total Price'

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer_name', 'contact_number', 'delivery_type', 
        'status', 'payment_status', 'total_amount', 'payment_method', 'created_at'
    ]
    list_filter = ['status', 'payment_status', 'delivery_type', 'payment_method', 'created_at']
    search_fields = ['customer_name', 'contact_number', 'id']
    readonly_fields = ['created_at', 'updated_at', 'order_number']
    list_editable = ['status']
    inlines = [OrderItemInline]
    list_per_page = 20
    
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'customer', 'customer_name', 'contact_number', 'status')
        }),
        ('Delivery Information', {
            'fields': ('delivery_type', 'address', 'note')
        }),
        ('Payment Information', {
            'fields': ('payment_method', 'payment_status', 'payment_proof', 'subtotal', 'delivery_fee', 'total_amount')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def order_number(self, obj):
        return obj.order_number
    order_number.short_description = 'Order Number'

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'menu_item', 'quantity', 'unit_price', 'total_price']
    list_filter = ['order__status']
    search_fields = ['order__id', 'menu_item__name']
    
    def total_price(self, obj):
        return f"₱{obj.unit_price * obj.quantity}"
    total_price.short_description = 'Total Price'

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'user__email', 'phone']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'phone')
        }),
        ('Additional Information', {
            'fields': ('address',)
        })
    )

@admin.register(GCashSettings)
class GCashSettingsAdmin(admin.ModelAdmin):
    list_display = ['gcash_number', 'account_name']
    search_fields = ['gcash_number', 'account_name']

# Unregister the default User admin and register a custom one to include customer info
admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('date_joined', 'is_active')
    list_filter = UserAdmin.list_filter + ('date_joined',)
    
    def get_inline_instances(self, request, obj=None):
        # Add customer profile as inline for users
        if obj:
            return [CustomerInline(self.model, self.admin_site)] + list(super().get_inline_instances(request, obj))
        return list(super().get_inline_instances(request, obj))

class CustomerInline(admin.StackedInline):
    model = Customer
    can_delete = False
    verbose_name_plural = 'Customer Profile'
    fk_name = 'user'

# Optional: Customize admin site header and title
admin.site.site_header = "Restaurant Administration"
admin.site.site_title = "Restaurant Admin Portal"
admin.site.index_title = "Welcome to Restaurant Management System"