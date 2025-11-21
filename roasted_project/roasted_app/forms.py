# roasted_app/forms.py
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import MenuItem, Order, Customer, CartItem
from django.core.exceptions import ValidationError
import re

class CustomUserCreationForm(UserCreationForm):
    """Custom user registration form with additional fields"""
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
    )
    phone = forms.CharField(
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+63 XXX XXX XXXX'
        })
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username'
            }),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            # Normalize phone number
            normalized_phone = re.sub(r'[+\s\-]', '', phone)
            
            # Validate Philippine format
            if not normalized_phone.startswith('63'):
                raise ValidationError('Phone number must be in Philippine format: +63 XXX XXX XXXX')
            
            if len(normalized_phone) != 12:
                raise ValidationError('Phone number must be 10 digits after +63')
            
            # Check if phone already exists
            existing_customers = Customer.objects.filter(
                phone__regex=r'[+\s\-]*63[+\s\-]*' + normalized_phone[2:]
            )
            if existing_customers.exists():
                raise ValidationError('Phone number already registered!')
        
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise ValidationError('Email already registered!')
        return email

class MenuItemForm(forms.ModelForm):
    """Form for creating and editing menu items"""
    class Meta:
        model = MenuItem
        fields = ['name', 'description', 'price', 'category', 'available', 'image', 'stock', 'is_featured']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter menu item name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter description',
                'rows': 3
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'category': forms.Select(attrs={
                'class': 'form-control'
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'min': '0'
            }),
            'image': forms.FileInput(attrs={  # ADDED: image widget
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'available': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_featured': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set category choices
        self.fields['category'].choices = MenuItem.CATEGORY_CHOICES

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price and price <= 0:
            raise ValidationError('Price must be greater than 0.')
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock and stock < 0:
            raise ValidationError('Stock cannot be negative.')
        return stock
    
class OrderStatusForm(forms.ModelForm):
    """Form for updating order status"""
    class Meta:
        model = Order
        fields = ['status']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

class OrderNoteForm(forms.ModelForm):
    """Form for adding admin notes to orders"""
    class Meta:
        model = Order
        fields = ['note']
        widgets = {
            'note': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Add order notes...',
                'rows': 3
            }),
        }

class CheckoutForm(forms.ModelForm):
    """Form for checkout process"""
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

    delivery_type = forms.ChoiceField(
        choices=DELIVERY_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'delivery-option'
        })
    )
    
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'payment-option'
        })
    )

    # Delivery fields
    customer_name = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name'
        })
    )
    
    customer_contact = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your phone number'
        })
    )
    
    delivery_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your complete delivery address',
            'rows': 3
        })
    )
    
    rider_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Any special instructions for the rider',
            'rows': 2
        })
    )

    # Pickup fields
    pickup_name = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name'
        })
    )
    
    pickup_contact = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your phone number'
        })
    )
    
    pickup_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Any special requests for your order',
            'rows': 2
        })
    )

    class Meta:
        model = Order
        fields = ['delivery_type', 'payment_method', 'customer_name', 'contact_number', 'address', 'note']

    def clean(self):
        cleaned_data = super().clean()
        delivery_type = cleaned_data.get('delivery_type')
        
        if delivery_type == 'delivery':
            # Validate delivery fields
            if not cleaned_data.get('customer_name'):
                self.add_error('customer_name', 'Name is required for delivery.')
            if not cleaned_data.get('customer_contact'):
                self.add_error('customer_contact', 'Contact number is required for delivery.')
            if not cleaned_data.get('delivery_address'):
                self.add_error('delivery_address', 'Delivery address is required.')
                
            # Set the main fields from delivery-specific fields
            cleaned_data['customer_name'] = cleaned_data.get('customer_name')
            cleaned_data['contact_number'] = cleaned_data.get('customer_contact')
            cleaned_data['address'] = cleaned_data.get('delivery_address')
            cleaned_data['note'] = cleaned_data.get('rider_note', '')
            
        elif delivery_type == 'pickup':
            # Validate pickup fields
            if not cleaned_data.get('pickup_name'):
                self.add_error('pickup_name', 'Name is required for pickup.')
            if not cleaned_data.get('pickup_contact'):
                self.add_error('pickup_contact', 'Contact number is required for pickup.')
                
            # Set the main fields from pickup-specific fields
            cleaned_data['customer_name'] = cleaned_data.get('pickup_name')
            cleaned_data['contact_number'] = cleaned_data.get('pickup_contact')
            cleaned_data['address'] = 'Roasted Route Main Branch - Villa Cornejo, Kawayan, Biliran'
            cleaned_data['note'] = cleaned_data.get('pickup_note', '')

        return cleaned_data

class CartItemForm(forms.ModelForm):
    """Form for cart item customization"""
    customization = forms.JSONField(
        required=False,
        widget=forms.HiddenInput()
    )

    class Meta:
        model = CartItem
        fields = ['quantity', 'customization']
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '10'
            }),
        }

class CustomerProfileForm(forms.ModelForm):
    """Form for customer profile updates"""
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = Customer
        fields = ['phone', 'address']
        widgets = {
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+63 XXX XXX XXXX'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your address',
                'rows': 3
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email

    def save(self, commit=True):
        customer = super().save(commit=False)
        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.email = self.cleaned_data['email']
            self.user.save()
        
        if commit:
            customer.save()
        return customer

# Search and Filter Forms
class MenuSearchForm(forms.Form):
    """Form for searching menu items"""
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search menu items...'
        })
    )
    
    category = forms.ChoiceField(
        required=False,
        choices=[('', 'All Categories')] + MenuItem.CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )

class OrderFilterForm(forms.Form):
    """Form for filtering orders in admin view"""
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('pending', 'Pending'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Pickup'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    delivery_type = forms.ChoiceField(
        choices=[('', 'All Types')] + Order.DELIVERY_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )