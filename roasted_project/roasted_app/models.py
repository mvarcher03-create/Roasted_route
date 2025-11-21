from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
from django.utils import timezone  # ADD THIS IMPORT

class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ('chicken', 'Chicken'),
        ('pork', 'Pork'),
        ('burger', 'Burger'),
        ('fries', 'Fries'),
        ('drinks', 'Drinks'),
    ]
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    available = models.BooleanField(default=True)
    image = models.ImageField(upload_to='menu_images/', blank=True, null=True)
    stock = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    is_featured = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['category', 'name']

    @property
    def review_count(self):
        """Return review count for the item"""
        return 0  # Placeholder - implement when you have reviews

    def get_absolute_url(self):
        """Return URL for the menu item"""
        from django.urls import reverse
        return reverse('edit_menu_item', args=[str(self.id)])

class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())
    
    @property
    def subtotal(self):
        """Calculate subtotal without delivery fee"""
        return sum(item.total_price for item in self.items.all())
    
    @property
    def total_price(self):
        """Total price in cart is just subtotal (no delivery fee)"""
        return self.subtotal
    
    def update_total(self):
        """Recalculate cart totals.

        Totals are currently computed dynamically via properties, so this
        method mainly exists for compatibility with views that expect it.
        We still save the cart to bump `updated_at` so any listeners or
        admin views that rely on it stay accurate.
        """
        # Touch the cart so `updated_at` is refreshed
        self.save(update_fields=["updated_at"])
    
    def __str__(self):
        return f"Cart #{self.id} - {self.user.username}"
    
class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey('MenuItem', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    customization = models.JSONField(blank=True, null=True)
    added_at = models.DateTimeField(default=timezone.now)  # CHANGED: removed auto_now_add=True, added default=timezone.now

    @property
    def base_total(self):
        """Base total without add-ons (unit price × quantity)."""
        return self.unit_price * self.quantity

    @property
    def addons_unit_price(self):
        """Total add-on price per unit based on customization JSON."""
        customization = self.customization or {}
        addons = customization.get('addons') or customization.get('addOns') or []
        total = Decimal('0.00')
        for addon in addons:
            price = addon.get('price') or 0
            try:
                total += Decimal(str(price))
            except Exception:
                # If price cannot be parsed, skip that add-on
                continue
        return total

    @property
    def addons_total(self):
        """Total add-on amount for this cart line (per unit add-ons × quantity)."""
        return self.addons_unit_price * self.quantity

    @property
    def total_price(self):
        """Full line total including base price and add-ons."""
        return self.base_total + self.addons_total

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.name}"

    def save(self, *args, **kwargs):
        """Override save to set unit_price from menu_item if not set"""
        if not self.unit_price:
            self.unit_price = self.menu_item.price
        super().save(*args, **kwargs)
        
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Pickup'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    DELIVERY_CHOICES = [
        ('delivery', 'Delivery'),
        ('pickup', 'Pick-up'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('credit_card', 'Credit Card'),
        ('gcash', 'GCash'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash on Delivery'),
        ('over_counter', 'Over the Counter'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('waiting_payment', 'Waiting for Payment'),
        ('for_verification', 'For Verification'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ]
    
    customer = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='orders', 
        null=True, 
        blank=True
    )
    customer_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=20, default='not Provided')
    
    # Order amounts
    subtotal = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2, default=30.00)  # Delivery fee only in order
    total_amount = models.DecimalField(max_digits=8, decimal_places=2)  
    
    # Delivery information
    delivery_type = models.CharField(
        max_length=20, 
        choices=DELIVERY_CHOICES, 
        default='delivery'
    )
    address = models.TextField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    
    # Payment information
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES, 
        default='cash'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid'
    )
    payment_proof = models.ImageField(upload_to='payment_proofs/', blank=True, null=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    review = models.TextField(blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

    @property
    def order_number(self):
        """Simple order number using ID"""
        return f"ORD-{self.id:06d}"

    @property
    def items_subtotal(self):
        """Recomputed subtotal from order items, including add-ons.

        This uses OrderItem.total_price so that any add-ons stored in the
        customization JSON are included, even if the stored subtotal field
        is out of date.
        """
        return sum((item.total_price for item in self.items.all()), Decimal('0.00'))

    @property
    def computed_total(self):
        """Recomputed total amount: items_subtotal + delivery_fee.

        Used by customer-facing UIs as the source of truth for the amount
        to pay, instead of trusting the stored total_amount field.
        """
        fee = self.delivery_fee or Decimal('0.00')
        return self.items_subtotal + fee

    @property
    def is_active(self):
        return self.status not in ['delivered', 'completed', 'cancelled']

    def get_status_display_with_icon(self):
        """Get status display with appropriate icons"""
        status_icons = {
            'pending': '📧 Pending',
            'preparing': '🍳 Preparing',
            'ready': '📦 Ready for Pickup',
            'out_for_delivery': '🚚 Out for Delivery',
            'delivered': '✅ Delivered',
            'completed': '✅ Completed',
            'cancelled': '❌ Cancelled'
        }
        return status_icons.get(self.status, self.get_status_display())

    def update_status(self, new_status):
        """Update order status with proper validation and notifications"""
        old_status = self.status
        
        # Validate status transition
        if new_status in self.get_available_status_updates():
            self.status = new_status
            self.save()
            
            # Trigger notifications based on status change
            self._send_status_notification(old_status, new_status)
            
            # Auto-complete delivery orders when marked as delivered
            if self.delivery_type == 'delivery' and new_status == 'delivered':
                # Add a small delay to ensure the delivered status is processed first
                from django.db import transaction
                with transaction.atomic():
                    self.status = 'completed'
                    self.save()
                    completion_message = "🎉 Your order has been marked as completed! Thank you for your order."
                    self._notify_customer(completion_message)
            
            return True
        return False

    def get_available_status_updates(self):
        """Get available next status options based on current status and delivery type"""
        if self.delivery_type == 'delivery':
                transitions = {
                'pending': ['preparing', 'cancelled'],
                'preparing': ['out_for_delivery', 'cancelled'],
                'out_for_delivery': ['delivered', 'cancelled'],
                'delivered': [],  # Final state
                'completed': [],  # Not used for delivery
                'cancelled': []   # Final state
            }
        else:  # pickup
            # Pickup workflow: Pending → Preparing → Ready for Pickup → Completed
            transitions = {
                'pending': ['preparing', 'cancelled'],
                'preparing': ['ready', 'cancelled'],
                'ready': ['completed', 'cancelled'],
                'completed': [],  # Final state
                'delivered': [],  # Not used for pickup
                'cancelled': []   # Final state
            }
        # For statuses not in transitions, return empty list
        return transitions.get(self.status, [])

    def _send_status_notification(self, old_status, new_status):
        """Send notifications to customer based on status change"""
        messages = {
            'preparing': "🍳 Your order is now being prepared! We'll notify you when it's ready.",
            'ready': "📦 Your order is ready for pickup! Please come to our store and pay at the counter.",
            'out_for_delivery': "🚚 Your order is out for delivery! Our rider is on the way to your location.",
            'delivered': "✅ Your order has been delivered! Thank you for your purchase.",
            'completed': "✅ Your order has been completed! Thank you for choosing Roasted Route.",
        }
        
        message = messages.get(new_status)
        if message:
            self._notify_customer(message)

    def _notify_customer(self, message):
        """Send notification to customer (email, SMS, etc.)"""
        notification_message = f"Order {self.order_number} Update: {message}"
        print(f"Notification to {self.customer_name} ({self.contact_number}): {notification_message}")
        if self.customer:
            try:
                Notification.objects.create(
                    user=self.customer,
                    message=notification_message,
                    type='order'
                )
            except Exception:
                pass

    def get_status_badge_class(self):
        """Get CSS class for status badge"""
        status_classes = {
            'pending': 'badge-warning',
            'preparing': 'badge-info',
            'ready': 'badge-success',
            'out_for_delivery': 'badge-primary',
            'delivered': 'badge-success',
            'completed': 'badge-success',
            'cancelled': 'badge-danger',
        }
        return status_classes.get(self.status, 'badge-secondary')

    class Meta:
        ordering = ['-created_at']


# Signal to handle status changes
@receiver(post_save, sender=Order)
def order_status_change_handler(sender, instance, **kwargs):
    """
    Handle order status changes and trigger appropriate actions
    """
    if kwargs.get('created', False):
        # New order created - send confirmation notification
        instance._notify_customer("📧 Thank you for your order! We've received your order and will start preparing it soon.")

class OrderItem(models.Model):  # Added to handle order items
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=6, decimal_places=2)
    customization = models.JSONField(default=dict, blank=True)

    @property
    def base_total(self):
        """Base total without add-ons (unit price × quantity)."""
        return self.unit_price * self.quantity

    @property
    def addons_unit_price(self):
        """Total add-on price per unit based on customization JSON."""
        customization = self.customization or {}
        addons = customization.get('addons') or customization.get('addOns') or []
        total = Decimal('0.00')
        for addon in addons:
            price = addon.get('price') or 0
            try:
                total += Decimal(str(price))
            except Exception:
                # If price cannot be parsed, skip that add-on
                continue
        return total

    @property
    def addons_total(self):
        """Total add-on amount for this order line (per unit add-ons × quantity)."""
        return self.addons_unit_price * self.quantity

    @property
    def total_price(self):
        """Full line total including base price and add-ons."""
        return self.base_total + self.addons_total

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name}"

class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    phone = models.CharField(max_length=15, unique=True)
    address = models.TextField(blank=True)  # Added address field
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.user.email}"

@receiver(post_save, sender=User)
def create_customer_profile(sender, instance, created, **kwargs):
    if created:
        Customer.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_customer_profile(sender, instance, **kwargs):
    if hasattr(instance, 'customer_profile'):
        instance.customer_profile.save()


class Notification(models.Model):
    TYPE_CHOICES = [
        ('order', 'Order'),
        ('stock', 'Stock'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='order')
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username}: {self.message[:40]}"

    def get_target_url(self):
        from django.urls import reverse
        if self.type == 'stock':
            return reverse('order_now')
        return reverse('order_history')


class ActivityLog(models.Model):
    CATEGORY_CHOICES = [
        ('account', 'Account'),
        ('order', 'Order'),
        ('menu', 'Menu'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    user_role = models.CharField(max_length=50, blank=True)
    action = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    order_number = models.CharField(max_length=50, blank=True)
    item_name = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} - {self.action}"


class GCashSettings(models.Model):
    """Site-wide settings for manual GCash payments (number, QR, instructions)."""

    gcash_number = models.CharField(max_length=50)
    account_name = models.CharField(max_length=100, blank=True)
    qr_code = models.ImageField(upload_to='gcash_qr/', blank=True, null=True)
    instructions = models.TextField(blank=True)

    class Meta:
        verbose_name = 'GCash Settings'
        verbose_name_plural = 'GCash Settings'

    def __str__(self):
        return 'GCash Settings'
