# roasted_app/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Sum, Q, F, Count
from django.utils import timezone
from datetime import date, timedelta
from .models import MenuItem, Order, Customer, Cart, CartItem, OrderItem, Notification, ActivityLog, GCashSettings
from django.db import IntegrityError
from .models import Customer
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
import re
from decimal import Decimal
import json
from django.views.decorators.csrf import csrf_exempt
from .forms import MenuItemForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


def get_user_role_label(user):
    if not user:
        return ''
    if user.is_superuser:
        return 'Owner'
    if user.is_staff:
        return 'Admin'
    return 'Customer'


def log_activity(user, category, action, description='', order=None, menu_item=None):
    if category not in ['account', 'order', 'menu']:
        return
    try:
        ActivityLog.objects.create(
            user=user,
            user_role=get_user_role_label(user),
            category=category,
            action=action,
            description=description or '',
            order=order,
            menu_item=menu_item,
            order_number=getattr(order, 'order_number', '') if order else '',
            item_name=getattr(menu_item, 'name', '') if menu_item else '',
        )
    except Exception as e:
        print(f"ActivityLog error: {e}")

def is_staff_user(user):
    return user.is_staff or user.is_superuser

def redirect_based_on_role(user):
    """Redirect user based on their role"""
    if user.is_staff or user.is_superuser:
        return redirect('admin_dashboard')
    return redirect('customer_dashboard')

def custom_login(request):
    if request.user.is_authenticated:
        print(f"DEBUG: User already authenticated, redirecting based on role")
        return redirect_based_on_role(request.user)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        print(f"DEBUG: Login attempt for username: {username}")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            print(f"DEBUG: Login successful for {username}")
            print(f"DEBUG: User is_staff: {user.is_staff}, is_superuser: {user.is_superuser}")
            
            login(request, user)
            # Log admin/staff login
            if user.is_staff or user.is_superuser:
                log_activity(
                    user=user,
                    category='account',
                    action='Admin logged in',
                    description=f'{user.username} logged in to admin panel.'
                )
            messages.success(request, f'Welcome back, {user.username}!')
            
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                print(f"DEBUG: Redirecting to next URL: {next_url}")
                return redirect(next_url)
            
            print(f"DEBUG: Redirecting based on role")
            return redirect_based_on_role(user)
        else:
            print(f"DEBUG: Login failed for {username}")
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')

def redirect_based_on_role(user):
    """Redirect user based on their role"""
    if user.is_superuser or user.is_staff:
        return redirect('admin_dashboard')
    else:
        return redirect('customer_dashboard')

def register_view(request):
    """Handle user registration"""
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # Validation
        errors = []
        
        # Required fields validation
        required_fields = {
            'first_name': 'First name',
            'last_name': 'Last name', 
            'username': 'Username',
            'email': 'Email',
            'phone': 'Phone number',
            'password1': 'Password'
        }
        
        for field, field_name in required_fields.items():
            if not locals()[field]:
                errors.append(f'{field_name} is required.')
        
        # Password validation
        if password1 and password2 and password1 != password2:
            errors.append('Passwords do not match!')
        
        if password1 and len(password1) < 8:
            errors.append('Password must be at least 8 characters long.')
        
        # Email format validation
        if email and '@' not in email:
            errors.append('Please enter a valid email address.')

        # Phone format validation (improved)
        if phone:
            # Normalize phone number for comparison
            normalized_phone = re.sub(r'[+\s\-]', '', phone)
            if not normalized_phone.startswith('63'):
                errors.append('Phone number must be in Philippine format: +63 XXX XXX XXXX')
            elif len(normalized_phone) != 12:  # +63 + 10 digits = 12 characters
                errors.append('Phone number must be 10 digits after +63')
        
        # Only check for existing users if no validation errors
        if not errors:
            # Unique validation with normalized data
            if username and User.objects.filter(username=username).exists():
                errors.append('Username already exists!')
            
            if email and User.objects.filter(email=email).exists():
                errors.append('Email already registered!')

            if phone:
                # Normalize phone for checking existence
                normalized_phone = re.sub(r'[+\s\-]', '', phone)
                # Check if any customer has this phone (normalized)
                existing_customers = Customer.objects.filter(
                    phone__regex=r'[+\s\-]*63[+\s\-]*' + normalized_phone[2:]  # Match any format with 63
                )
                if existing_customers.exists():
                    errors.append('Phone number already registered!')

        if errors:
            return render(request, 'register.html', {
                'errors': errors,
                'first_name': first_name,
                'last_name': last_name,
                'username': username,
                'email': email,
                'phone': phone,
            })

        try:
            # Use transaction to ensure both objects are created or none
            with transaction.atomic():
                # Normalize phone number before saving
                normalized_phone = re.sub(r'[+\s\-]', '', phone)
                if normalized_phone.startswith('63') and len(normalized_phone) == 12:
                    # Format as +63 XXX XXX XXXX for consistency
                    formatted_phone = f"+63 {normalized_phone[2:5]} {normalized_phone[5:8]} {normalized_phone[8:12]}"
                else:
                    formatted_phone = phone
                
                # Create user
                user = User.objects.create_user(
                    username=username, 
                    email=email, 
                    password=password1,
                    first_name=first_name,
                    last_name=last_name
                )

                # Check if Customer already exists for this user (shouldn't happen, but just in case)
                if Customer.objects.filter(user=user).exists():
                    # Update existing customer instead of creating new one
                    customer = Customer.objects.get(user=user)
                    customer.phone = formatted_phone
                    customer.save()
                else:
                    # Create new Customer profile
                    Customer.objects.create(user=user, phone=formatted_phone)

            # SUCCESS - Redirect to login with success message
            messages.success(request, 'Registration successful! Please login with your new account.')
            return redirect('login')
            
        except IntegrityError as e:
            # Log the actual error for debugging
            print(f"IntegrityError: {e}")
            
            # Clean up: if user was created but customer failed, delete the user
            if 'username' in locals() and username:
                try:
                    user = User.objects.get(username=username)
                    user.delete()
                except User.DoesNotExist:
                    pass
            
            errors = ['Registration failed due to a database error. This might be because the username, email, or phone number is already in use. Please try different information.']
            return render(request, 'register.html', {
                'errors': errors,
                'first_name': first_name,
                'last_name': last_name,
                'username': username,
                'email': email,
                'phone': phone,
            })
        except Exception as e:
            # Log the actual error for debugging
            print(f"Exception: {e}")
            
            # Clean up: if user was created but customer failed, delete the user
            if 'username' in locals() and username:
                try:
                    user = User.objects.get(username=username)
                    user.delete()
                except User.DoesNotExist:
                    pass
            
            errors = [f'Registration failed: {str(e)}']
            return render(request, 'register.html', {
                'errors': errors,
                'first_name': first_name,
                'last_name': last_name,
                'username': username,
                'email': email,
                'phone': phone,
            })

    return render(request, 'register.html')

from django.shortcuts import redirect

def home(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('admin_dashboard')
        else:
            return redirect('customer_dashboard')
    else:
        featured_items = MenuItem.objects.filter(
            available=True,
            is_featured=True
        )[:6]
        return render(request, 'home.html', {
            'featured_items': featured_items,
        })


def custom_logout(request):
    """Handle user logout"""
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        log_activity(
            user=request.user,
            category='account',
            action='Admin logged out',
            description=f'{request.user.username} logged out from admin panel.'
        )
    # Clear any existing queued messages so only the logout message is shown
    storage = messages.get_messages(request)
    for _ in storage:
        pass

    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('login')


@staff_member_required
def admin_dashboard(request):
    """Admin dashboard with statistics"""
    # Dashboard statistics
    today = timezone.now().date()
    total_users = User.objects.count()
    total_products = MenuItem.objects.count()
    orders_today = Order.objects.count()
    new_users_today = User.objects.filter(date_joined__date=today).count()

    # Calculate total sales from completed/delivered orders only
    completed_orders = Order.objects.filter(
        status__in=['completed', 'delivered']
    )
    total_sales = sum((o.computed_total for o in completed_orders), Decimal('0.00'))

    # Pending orders count
    pending_orders = Order.objects.filter(status='pending').count()

    # Product availability and low stock items
    try:
        available_products = MenuItem.objects.filter(available=True, stock__gt=0).count()
        low_stock = MenuItem.objects.filter(stock__lt=10).count()
    except Exception:
        available_products = MenuItem.objects.filter(available=True).count()
        low_stock = 0

    # Recent data - include customer information
    recent_orders = Order.objects.select_related('customer').order_by('-created_at')[:5]
    recent_users = User.objects.all().order_by('-date_joined')[:5]

    context = {
        'total_users': total_users,
        'total_products': total_products,
        'orders_today': orders_today,
        'new_users_today': new_users_today,
        'available_products': available_products,
        'total_sales': total_sales,
        'total_revenue': total_sales,
        'pending_orders': pending_orders,
        'low_stock': low_stock,
        'recent_orders': recent_orders,
        'recent_users': recent_users,
    }

    return render(request, 'admin_dashboard.html', context)

@staff_member_required
def menu_management(request):
    """Menu management dashboard for staff"""
    # Get all menu items
    menu_items = MenuItem.objects.all().order_by('category', 'name')
    
    # Get categories for filter
    categories = [{'name': choice[1], 'value': choice[0]} for choice in MenuItem.CATEGORY_CHOICES]
    
    # Calculate statistics
    total_items = MenuItem.objects.count()
    available_items = MenuItem.objects.filter(available=True, stock__gt=0).count()
    # Items explicitly marked unavailable (regardless of stock)
    unavailable_items = MenuItem.objects.filter(available=False).count()
    # Items that are out of stock (stock == 0)
    out_of_stock_items = MenuItem.objects.filter(stock=0).count()
    
    # Calculate average price
    from django.db.models import Avg
    avg_price_result = MenuItem.objects.aggregate(avg_price=Avg('price'))
    avg_price = avg_price_result['avg_price'] or 0
    
    # Get low stock items (stock < 5)
    low_stock_items = MenuItem.objects.filter(stock__lt=5).order_by('stock')
    
    context = {
        'menu_items': menu_items,  # CHANGED: from menu_items_by_category to menu_items
        'categories': categories,  # ADDED: categories for filter
        'total_items': total_items,
        'available_items': available_items,
        'unavailable_items': unavailable_items,
        'out_of_stock_items': out_of_stock_items,
        'avg_price': avg_price,
        'low_stock_items': low_stock_items,
        'user_first_name': request.user.first_name,
        'user_last_name': request.user.last_name,
        'user_username': request.user.username,
        'user_is_staff': request.user.is_staff,
    }
    
    return render(request, 'menu_management.html', context)

@staff_member_required
def add_menu_item(request):
    """Add new menu item"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        price = request.POST.get('price')
        category = request.POST.get('category')
        available = request.POST.get('available') == 'on'
        stock = request.POST.get('stock', 0)
        is_featured = request.POST.get('is_featured') == 'on'
        image = request.FILES.get('image')

        # Validate required fields
        if not name or not price or not category:
            messages.error(request, 'Name, price, and category are required fields.')
            return render(request, 'add_menu_item.html')
        
        try:
            menu_item = MenuItem.objects.create(
                name=name,
                description=description,
                price=price,
                category=category,
                available=available,
                stock=stock,
                is_featured=is_featured,
                image=image
            )
            if request.user.is_staff or request.user.is_superuser:
                log_activity(
                    user=request.user,
                    category='menu',
                    action='Added new menu item',
                    description=f'Added menu item "{menu_item.name}" with price {menu_item.price} and stock {menu_item.stock}.',
                    menu_item=menu_item,
                )
            messages.success(request, 'Menu item added successfully!')
            return redirect('menu_management')
        except Exception as e:
            messages.error(request, f'Error adding menu item: {str(e)}')
    
    return render(request, 'add_menu_item.html')

@login_required
def edit_menu_item(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)
    
    if request.method == 'POST':
        form = MenuItemForm(request.POST, request.FILES, instance=menu_item)
        if form.is_valid():
            menu_item = form.save()
            if request.user.is_staff or request.user.is_superuser:
                log_activity(
                    user=request.user,
                    category='menu',
                    action='Updated menu item',
                    description=f'Updated menu item "{menu_item.name}".',
                    menu_item=menu_item,
                )
            messages.success(request, f'"{menu_item.name}" has been updated successfully!')
            return redirect('menu_management')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = MenuItemForm(instance=menu_item)
    
    context = {
        'form': form,
        'menu_item': menu_item,
    }
    return render(request, 'edit_menu_item.html', context)

@staff_member_required
@login_required
def delete_menu_item(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)
    
    if request.method == 'POST':
        item_name = menu_item.name
        if request.user.is_staff or request.user.is_superuser:
            log_activity(
                user=request.user,
                category='menu',
                action='Deleted menu item',
                description=f'Deleted menu item "{item_name}".',
                menu_item=menu_item,
            )
        menu_item.delete()
        messages.success(request, f'Menu item "{item_name}" has been deleted successfully!')
        return redirect('menu_management')
    
    # For GET requests, render the confirmation page
    context = {
        'menu_item': menu_item,
    }
    return render(request, 'delete_menu_item.html', context)

@login_required
def toggle_availability(request, item_id):
    menu_item = get_object_or_404(MenuItem, id=item_id)
    
    if request.method == 'POST':
        try:
            menu_item.available = not menu_item.available
            menu_item.save()
            if request.user.is_staff or request.user.is_superuser:
                status_label = 'available' if menu_item.available else 'unavailable'
                log_activity(
                    user=request.user,
                    category='menu',
                    action='Toggled menu availability',
                    description=f'Set "{menu_item.name}" as {status_label}.',
                    menu_item=menu_item,
                )
            
            return JsonResponse({
                'success': True, 
                'new_status': menu_item.available
            })
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@staff_member_required
def menu_item_sales(request, item_id):
    """Return basic sales stats for a specific menu item (for admin menu management)."""
    try:
        menu_item = get_object_or_404(MenuItem, id=item_id)

        # Use OrderItem data, excluding cancelled orders
        order_items = OrderItem.objects.filter(menu_item=menu_item).exclude(order__status='cancelled')

        stats = order_items.aggregate(
            total_quantity=Sum('quantity'),
            order_count=Count('order', distinct=True),
        )

        # Safely compute total amount in Python to avoid DB-specific expression issues
        from decimal import Decimal
        total_amount = Decimal('0.00')
        for oi in order_items:
            try:
                total_amount += (oi.unit_price or Decimal('0.00')) * oi.quantity
            except Exception:
                continue

        data = {
            'product_name': menu_item.name,
            'total_quantity': int(stats['total_quantity'] or 0),
            'order_count': int(stats['order_count'] or 0),
            'total_amount': float(total_amount or 0),
        }

        return JsonResponse({'success': True, 'data': data})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
def manage_customers(request):
    """Manage customers view"""
    # Only include real customer accounts (exclude staff/admin/superuser)
    # Annotate each customer with order count
    base_qs = (
        User.objects
        .filter(is_staff=False, is_superuser=False)
        .annotate(
            order_count=Count('orders', filter=~Q(orders__status='cancelled')),
        )
        .order_by('date_joined')
    )

    customers = list(base_qs)

    # Compute real-time total spent per customer using Order.computed_total
    if customers:
        customer_ids = [c.id for c in customers]
        spending_orders = (
            Order.objects
            .filter(
                customer_id__in=customer_ids,
                status__in=['completed', 'delivered'],
            )
            .prefetch_related('items')
        )

        totals_by_customer = {}
        for order in spending_orders:
            current_total = totals_by_customer.get(order.customer_id, Decimal('0.00'))
            totals_by_customer[order.customer_id] = current_total + order.computed_total

        for customer in customers:
            customer.total_spent = totals_by_customer.get(customer.id, Decimal('0.00'))

    return render(request, 'customers.html', {'customers': customers})

@staff_member_required
def activity_logs(request):
    """Admin activity logs with search, filters, and pagination"""
    logs = ActivityLog.objects.select_related('user', 'order', 'menu_item').all()

    query = request.GET.get('q', '').strip()
    if query:
        logs = logs.filter(
            Q(user__username__icontains=query) |
            Q(order_number__icontains=query) |
            Q(item_name__icontains=query) |
            Q(action__icontains=query) |
            Q(description__icontains=query)
        )

    user_filter = request.GET.get('user_filter', '').strip()
    if user_filter in ['Admin', 'Owner']:
        logs = logs.filter(user_role=user_filter)

    date_filter = request.GET.get('date_filter', '').strip()
    now = timezone.now()
    if date_filter == 'today':
        logs = logs.filter(timestamp__date=now.date())
    elif date_filter == '7':
        logs = logs.filter(timestamp__gte=now - timedelta(days=7))
    elif date_filter == '30':
        logs = logs.filter(timestamp__gte=now - timedelta(days=30))

    paginator = Paginator(logs, 15)
    page = request.GET.get('page')
    logs_page = paginator.get_page(page)

    context = {
        'logs_page': logs_page,
        'query': query,
        'user_filter': user_filter,
        'date_filter': date_filter,
        'user_filter_choices': ['Admin', 'Owner'],
    }

    return render(request, 'activity_logs.html', context)


@staff_member_required
def view_orders(request):
    """Admin view to see orders with summary stats over a selectable period."""
    # Base queryset with related data for efficiency
    orders_qs = Order.objects.select_related('customer').prefetch_related('items__menu_item')

    # Date range / period filter
    period = request.GET.get('period', 'today')
    search_query = request.GET.get('q', '').strip()
    today = date.today()

    if period == 'today':
        start_date = today
        period_label = 'Today'
    elif period == 'week':
        # Last 7 days including today
        start_date = today - timedelta(days=6)
        period_label = 'This Week'
    elif period == 'month':
        start_date = today.replace(day=1)
        period_label = 'This Month'
    elif period == 'year':
        start_date = today.replace(month=1, day=1)
        period_label = 'This Year'
    else:
        start_date = None
        period = 'all'
        period_label = 'All Time'

    if start_date:
        orders_qs = orders_qs.filter(created_at__date__gte=start_date)

    # Apply search filter for the orders list (stats still use the full period)
    list_orders_qs = orders_qs
    if search_query:
        # Allow searching by customer name, contact number, address, and numeric ID
        id_filter = None
        if search_query.isdigit():
            try:
                id_filter = int(search_query)
            except (TypeError, ValueError):
                id_filter = None

        search_filters = (
            Q(customer_name__icontains=search_query)
            | Q(contact_number__icontains=search_query)
            | Q(address__icontains=search_query)
        )
        if id_filter is not None:
            search_filters = search_filters | Q(id=id_filter)

        list_orders_qs = list_orders_qs.filter(search_filters)

    # Orders for list view
    orders = list_orders_qs.order_by('-created_at')

    # Stats for the selected period (exclude cancelled for cleaner metrics)
    period_orders = orders_qs.exclude(status='cancelled')

    orders_today = period_orders.count()
    completed_orders_today = period_orders.filter(
        status__in=['completed', 'delivered'],
    ).count()
    pending_orders = period_orders.filter(status='pending').count()

    # Total sales: only count delivered/completed orders.
    # For GCash, include only when payment_status is 'paid'. For other methods, keep existing behavior.
    completed_orders_qs = period_orders.filter(
        status__in=['completed', 'delivered']
    ).filter(
        Q(payment_method='gcash', payment_status='paid') |
        ~Q(payment_method='gcash')
    )
    total_sales = sum((o.computed_total for o in completed_orders_qs), Decimal('0.00'))

    # Orders where the customer explicitly confirmed delivery
    confirmed_order_ids = list(
        ActivityLog.objects.filter(
            category='order',
            action='Customer confirmed delivery',
        ).values_list('order_id', flat=True)
    )
    
    context = {
        'orders': orders,
        'orders_today': orders_today,
        'completed_orders': completed_orders_today,
        'pending_orders': pending_orders,
        'total_sales': total_sales,
        'confirmed_order_ids': confirmed_order_ids,
        'period': period,
        'period_label': period_label,
        'search_query': search_query,
    }
    
    return render(request, 'view_orders.html', context)

@staff_member_required
def order_detail(request, order_id):
    """View order details"""
    # Use prefetch_related to get order items with menu items
    order = get_object_or_404(
        Order.objects
        .select_related('customer')
        .prefetch_related('items__menu_item'),  # This is the key fix!
        id=order_id
    )
    
    # Debug information
    print(f"=== ORDER DEBUG INFO ===")
    print(f"Order ID: {order.id}")
    print(f"Customer: {order.customer_name}")
    print(f"Total Amount: ₱{order.total_amount}")
    print(f"Items count: {order.items.count()}")
    
    for item in order.items.all():
        print(f" - Item: {item.menu_item.name}, Qty: {item.quantity}, Price: ₱{item.unit_price}")
    print(f"========================")
    
    context = {
        'order': order,
    }
    
    return render(request, 'order_details.html', context)

@staff_member_required
def update_order_status(request, order_id):
    if request.method == 'POST':
        try:
            order = get_object_or_404(Order, id=order_id)
            new_status = request.POST.get('status')
            notes = request.POST.get('notes', '')
            
            # Validate status transition
            valid_transitions = {
                'delivery': {
                    'pending': ['preparing', 'cancelled'],
                    'preparing': ['out_for_delivery', 'cancelled'],
                    'out_for_delivery': ['delivered', 'cancelled'],
                    'delivered': [],
                    'cancelled': []
                },
                'pickup': {
                    'pending': ['preparing', 'cancelled'],
                    'preparing': ['ready', 'cancelled'],
                    'ready': ['completed', 'cancelled'],
                    'completed': [],
                    'cancelled': []
                }
            }
            
            # Check if the transition is valid
            current_status = order.status
            delivery_type = order.delivery_type
            allowed_next_statuses = valid_transitions.get(delivery_type, {}).get(current_status, [])
            
            if new_status not in allowed_next_statuses:
                return JsonResponse({
                    'success': False, 
                    'message': f'Invalid status transition from {current_status} to {new_status} for {delivery_type} order'
                })
            
            # Update order status using model method (includes notifications)
            if order.update_status(new_status):
                if notes:
                    order.admin_notes = notes
                    order.save()
                if request.user.is_staff or request.user.is_superuser:
                    desc_parts = [f'Changed status from {current_status} to {new_status}.']
                    if notes:
                        desc_parts.append(f'Notes: {notes}')
                    log_activity(
                        user=request.user,
                        category='order',
                        action='Updated order status',
                        description=' '.join(desc_parts),
                        order=order,
                    )
                
                return JsonResponse({
                    'success': True, 
                    'message': f'Order status updated from {current_status} to {new_status}'
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'message': f'Invalid status transition from {current_status} to {new_status} for {delivery_type} order'
                })
        
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Error updating order status: {str(e)}'
            })
    
    return JsonResponse({
        'success': False, 
        'message': 'Invalid request method. Only POST allowed.'
    })

@staff_member_required
def cancel_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        
        # Only allow cancellation if order is not completed
        if order.status not in ['completed', 'cancelled']:
            order.status = 'cancelled'
            order.save()
            
            # Restore stock for cancelled order
            for order_item in order.orderitem_set.all():
                menu_item = order_item.menu_item
                menu_item.stock += order_item.quantity
                menu_item.save()
                print(f"Stock restored: {menu_item.name} - increased by {order_item.quantity}, new stock: {menu_item.stock}")
            log_activity(
                user=request.user,
                category='order',
                action='Cancelled order',
                description=f'Cancelled order {order.order_number} and restored stock.',
                order=order,
            )
            
            return JsonResponse({'success': True, 'message': 'Order cancelled successfully and stock restored'})
        else:
            return JsonResponse({'success': False, 'message': 'Cannot cancel completed or already cancelled order'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@staff_member_required
@require_http_methods(["POST"])
def update_payment_status(request, order_id):
    """Update the payment_status field for an order (e.g., GCash verification)."""
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get('payment_status')

    valid_statuses = {choice[0] for choice in Order.PAYMENT_STATUS_CHOICES}
    if new_status not in valid_statuses:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Invalid payment status'}, status=400)
        messages.error(request, 'Invalid payment status.')
        return redirect('view_orders')

    old_status = order.payment_status
    order.payment_status = new_status
    order.save(update_fields=['payment_status'])

    # Log activity for audit trail
    try:
        log_activity(
            user=request.user,
            category='order',
            action='Updated payment status',
            description=f'Changed payment status from {old_status} to {new_status} for order {order.order_number}.',
            order=order,
        )
    except Exception:
        pass

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'payment_status': new_status,
            'payment_status_display': order.get_payment_status_display(),
        })

    messages.success(request, 'Payment status updated successfully.')
    return redirect('view_orders')

@login_required
def customer_dashboard(request):
    # Get current user's active orders (pending or processing)
    active_orders = Order.objects.filter(
        customer=request.user
    ).exclude(
        status__in=['completed', 'cancelled', 'delivered']
    ).order_by('-created_at')

    # Get recent completed orders
    recent_orders = Order.objects.filter(
        customer=request.user,
        status__in=['delivered', 'completed', 'cancelled'],
    ).order_by('-created_at')[:5]

    # Get featured menu items
    featured_items = MenuItem.objects.filter(
        available=True, 
        is_featured=True
    )[:4]

    # Get order statistics for the user
    total_orders = Order.objects.filter(customer=request.user).count()

    # Use computed_total for real-time, accurate spending across completed/delivered orders
    spending_orders = Order.objects.filter(
        customer=request.user,
        status__in=['completed', 'delivered']
    )
    total_spent = sum((o.computed_total for o in spending_orders), Decimal('0.00'))

    order_stats = {
        'total_orders': total_orders,
        'completed_orders': Order.objects.filter(
            customer=request.user,
            status='completed'
        ).count(),
        'total_spent': total_spent
    }

    # Notifications for the customer header
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    unread_notifications_count = Notification.objects.filter(user=request.user, read=False).count()

    context = {
        'active_orders': active_orders,
        'recent_orders': recent_orders,
        'featured_items': featured_items,
        'total_orders': total_orders,
        'order_stats': order_stats,
        'total_spent': total_spent,
        'notifications': notifications,
        'unread_notifications_count': unread_notifications_count,
    }
    
    return render(request, 'customer_dashboard.html', context)

@login_required
def customer_cancel_order(request, order_id):
    """Customer can cancel their own orders"""
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id, customer=request.user)
        
        # Only allow cancellation if order is not completed, delivered, or already cancelled
        if order.status == 'pending':
            order.status = 'cancelled'
            order.save()
            
            # Restore stock for cancelled order
            for order_item in order.orderitem_set.all():
                menu_item = order_item.menu_item
                menu_item.stock += order_item.quantity
                menu_item.save()
                print(f"Stock restored: {menu_item.name} - increased by {order_item.quantity}, new stock: {menu_item.stock}")
            log_activity(
                user=request.user,
                category='order',
                action='Customer cancelled order',
                description=f'Customer cancelled order {order.order_number}.',
                order=order,
            )
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Order cancelled successfully and stock restored'})
            else:
                messages.success(request, 'Order cancelled successfully!')
                return redirect('customer_dashboard')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'Only pending orders can be cancelled'})
            else:
                messages.error(request, 'Only pending orders can be cancelled.')
                return redirect('customer_dashboard')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': False, 'message': 'Invalid request method'})
    else:
        messages.error(request, 'Invalid request.')
        return redirect('customer_dashboard')


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark a single notification as read for the current user"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    if not notification.read:
        notification.read = True
        notification.save(update_fields=['read'])

    unread_count = Notification.objects.filter(user=request.user, read=False).count()
    return JsonResponse({'success': True, 'unread_count': unread_count})


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all notifications as read for the current user"""
    Notification.objects.filter(user=request.user, read=False).update(read=True)
    return JsonResponse({'success': True, 'unread_count': 0})

@login_required
def order_now(request):
    # Get all available menu items
    menu_items = MenuItem.objects.filter(available=True)
    
    # Get category choices from the model
    category_choices = MenuItem.CATEGORY_CHOICES
    
    # Notifications for the customer header
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    unread_notifications_count = Notification.objects.filter(user=request.user, read=False).count()

    return render(request, 'order_now.html', {
        'menu_items': menu_items,
        'category_choices': category_choices,
        'notifications': notifications,
        'unread_notifications_count': unread_notifications_count,
    })

@login_required
def my_orders(request):
    active_orders = Order.objects.filter(
        customer=request.user
    ).exclude(
        status__in=['delivered', 'completed', 'cancelled']
    ).prefetch_related('items__menu_item').order_by('-created_at')

    gcash_settings = GCashSettings.objects.first()

    # Notifications for the customer header
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    unread_notifications_count = Notification.objects.filter(user=request.user, read=False).count()

    context = {
        'orders': active_orders,
        'notifications': notifications,
        'unread_notifications_count': unread_notifications_count,
        'gcash_settings': gcash_settings,
    }

    return render(request, 'view_my_orders.html', context)

@login_required
def order_history(request):
    """Customer order history list with basic stats"""
    all_orders = Order.objects.filter(customer=request.user)
    history_orders = all_orders.filter(status__in=['delivered', 'completed', 'cancelled']).prefetch_related('items__menu_item')

    status_filter = request.GET.get('status', 'all')
    date_range = request.GET.get('range', 'all')
    search_query = request.GET.get('q', '').strip()

    orders = history_orders

    if status_filter == 'completed':
        orders = orders.filter(status__in=['delivered', 'completed'])
    elif status_filter == 'cancelled':
        orders = orders.filter(status='cancelled')

    if date_range in ['7', '30']:
        days = int(date_range)
        start_date = timezone.now() - timedelta(days=days)
        orders = orders.filter(created_at__gte=start_date)

    if search_query:
        orders = orders.filter(
            Q(order_number__icontains=search_query) |
            Q(items__menu_item__name__icontains=search_query)
        ).distinct()

    orders = orders.order_by('-created_at')

    stats = {
        'total': history_orders.count(),
        'active': all_orders.exclude(status__in=['completed', 'cancelled', 'delivered']).count(),
        'completed': history_orders.filter(status__in=['delivered', 'completed']).count(),
        'cancelled': history_orders.filter(status='cancelled').count(),
    }

    # Notifications for the customer header
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    unread_notifications_count = Notification.objects.filter(user=request.user, read=False).count()

    return render(request, 'view_order_history.html', {
        'orders': orders,
        'stats': stats,
        'status_filter': status_filter,
        'date_range': date_range,
        'search_query': search_query,
        'notifications': notifications,
        'unread_notifications_count': unread_notifications_count,
    })

@login_required
@require_POST
def reorder_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)

    missing_stock_items = []
    added_any = False

    for order_item in order.items.all():
        menu_item = order_item.menu_item
        quantity_to_add = order_item.quantity
        customization_data = order_item.customization or {}

        existing_item = cart.items.filter(menu_item=menu_item, customization=customization_data).first()
        existing_quantity = existing_item.quantity if existing_item else 0

        if menu_item.stock < existing_quantity + quantity_to_add:
            missing_stock_items.append(menu_item.name)
            continue

        if existing_item:
            existing_item.quantity = existing_quantity + quantity_to_add
            existing_item.save()
        else:
            CartItem.objects.create(
                cart=cart,
                menu_item=menu_item,
                quantity=quantity_to_add,
                unit_price=menu_item.price,
                customization=customization_data,
            )

        added_any = True

    cart.update_total()

    if not added_any:
        messages.error(request, 'Unable to reorder. Items from this order are currently out of stock.')
        return redirect('order_history')

    if missing_stock_items:
        messages.warning(
            request,
            'Some items could not be reordered due to low stock: ' + ', '.join(missing_stock_items)
        )

    messages.success(request, f'Items from order {order.order_number} were added to your cart.')
    return redirect('cart')

@login_required
@require_POST
def rate_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if order.status not in ['delivered', 'completed']:
        messages.error(request, 'You can only rate completed orders.')
        return redirect('order_history')

    try:
        rating_value = int(request.POST.get('rating', 0))
    except (TypeError, ValueError):
        rating_value = 0

    review_text = (request.POST.get('review') or '').strip()

    if rating_value < 1 or rating_value > 5:
        messages.error(request, 'Please choose a rating from 1 to 5 stars.')
        return redirect('order_history')

    order.rating = rating_value
    order.review = review_text
    order.save(update_fields=['rating', 'review'])

    messages.success(request, 'Thank you for rating your order!')
    return redirect('order_history')


@login_required
@require_POST
def notify_admin_order_delivered(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if order.status not in ['delivered', 'completed']:
        messages.error(request, 'You can only notify admin for delivered or completed orders.')
        return redirect('order_history')

    admins = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).distinct()

    if not admins.exists():
        messages.error(request, 'No admin users are configured to receive notifications.')
        return redirect('order_history')

    message_text = f"Customer {request.user.username} confirmed delivery for order {order.order_number}."

    for admin_user in admins:
        try:
            Notification.objects.create(
                user=admin_user,
                message=message_text,
                type='order'
            )
        except Exception:
            continue

    # Log in activity history for admin reporting
    log_activity(
        user=request.user,
        category='order',
        action='Customer confirmed delivery',
        description=message_text,
        order=order,
    )

    messages.success(request, 'Admin has been notified about this delivered order.')
    return redirect('order_history')


@login_required
@require_POST
def upload_payment_proof(request, order_id):
    """Allow customers to upload a GCash payment screenshot for their order."""
    order = get_object_or_404(Order, id=order_id, customer=request.user)

    if order.payment_method != 'gcash':
        messages.error(request, 'Payment proof is only required for GCash orders.')
        return redirect('order_confirmation', orderz_id=order.id)

    payment_file = request.FILES.get('payment_proof')
    if not payment_file:
        messages.error(request, 'Please select an image file to upload.')
        return redirect('order_confirmation', orderz_id=order.id)

    content_type = getattr(payment_file, 'content_type', '') or ''
    if not content_type.startswith('image/'):
        messages.error(request, 'Only image files (JPG/PNG) are allowed for payment proof.')
        return redirect('order_confirmation', orderz_id=order.id)

    # Save proof and move payment status to "For Verification"
    order.payment_proof = payment_file
    order.payment_status = 'for_verification'
    order.save(update_fields=['payment_proof', 'payment_status'])

    # Notify admins that a new proof is available
    admins = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).distinct()
    message_text = f"Customer {request.user.username} uploaded a GCash payment proof for order {order.order_number}."

    for admin_user in admins:
        try:
            Notification.objects.create(
                user=admin_user,
                message=message_text,
                type='order'
            )
        except Exception:
            continue

    try:
        log_activity(
            user=request.user,
            category='order',
            action='Uploaded GCash payment proof',
            description=message_text,
            order=order,
        )
    except Exception:
        pass

    messages.success(request, 'Your GCash receipt has been uploaded. We will verify your payment shortly.')
    return redirect('order_confirmation', orderz_id=order.id)

@login_required
def profile(request):
    """Customer profile page with stats and editable info"""
    # Get order stats for the user
    user_orders = Order.objects.filter(customer=request.user)
    total_orders = user_orders.count()
    active_orders = user_orders.exclude(status__in=['completed', 'cancelled']).count()
    completed_orders = user_orders.filter(status__in=['delivered', 'completed']).count()
    
    # Handle POST for profile updates
    if request.method == 'POST':
        # Update user fields
        user = request.user
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.save()
        
        # Update customer profile fields
        try:
            profile = user.customer_profile
            profile.phone = request.POST.get('phone', '').strip()
            profile.address = request.POST.get('address', '').strip()
            profile.save()
        except AttributeError:
            # Create customer profile if it doesn't exist
            from .models import Customer
            Customer.objects.create(
                user=user,
                phone=request.POST.get('phone', '').strip(),
                address=request.POST.get('address', '').strip()
            )
        
        # Add success message
        from django.contrib import messages
        messages.success(request, 'Profile updated successfully!')
    
    # Notifications for the customer header
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    unread_notifications_count = Notification.objects.filter(user=request.user, read=False).count()

    context = {
        'total_orders': total_orders,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'notifications': notifications,
        'unread_notifications_count': unread_notifications_count,
    }
    return render(request, 'customer_profile.html', context)

def cart_view(request):
    cart = get_object_or_404(Cart, user=request.user, is_active=True)
    cart_items = cart.items.all()

    # Compute delivery fee safely; default to 30.00 if not available on model
    try:
        delivery_fee = cart.delivery_fee
    except AttributeError:
        from decimal import Decimal
        delivery_fee = Decimal('30.00')

    # Some code uses cart.subtotal, others cart.total_price; support both
    subtotal = cart.subtotal

    context = {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'total_price': subtotal,
        'delivery_fee': delivery_fee,
    }

    return render(request, 'cart.html', context)

@require_POST
@login_required
def update_cart_item(request, item_id):
    """Update cart item quantity"""
    try:
        cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        action = request.POST.get('action')
        
        if action == 'increase':
            # Check if increasing quantity would exceed stock
            if cart_item.quantity >= cart_item.menu_item.stock:
                return JsonResponse({
                    'success': False,
                    'message': f'Only {cart_item.menu_item.stock} {cart_item.menu_item.name}(s) available in stock'
                })
            cart_item.quantity += 1
        elif action == 'decrease' and cart_item.quantity > 1:
            cart_item.quantity -= 1
        elif action == 'remove':
            cart_item.delete()
            return JsonResponse({'success': True})
        
        cart_item.save()
        cart_item.cart.update_total()
        
        return JsonResponse({
            'success': True,
            'quantity': cart_item.quantity,
            'item_total': cart_item.total_price,
            'cart_total': cart_item.cart.total_price
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })

from decimal import Decimal

@login_required
def checkout(request):
    """Checkout view that displays cart items and handles order placement"""
    # Get basic customer info from the logged-in account/profile
    user = request.user
    customer_profile = getattr(user, 'customer_profile', None)
    customer_name = f"{user.first_name} {user.last_name}".strip() or user.username
    customer_phone = ''
    customer_address = ''
    if customer_profile:
        customer_phone = customer_profile.phone
        customer_address = customer_profile.address or ''

    # Flag if profile is missing important checkout info
    profile_needs_update = (not user.first_name or not user.last_name or not customer_phone)

    # Load GCash settings (for manual GCash instructions / QR)
    gcash_settings = GCashSettings.objects.first()

    try:
        # Get the current user's active cart
        cart = Cart.objects.get(user=user, is_active=True)
        cart_items = CartItem.objects.filter(cart=cart).select_related('menu_item')
        
        # Calculate totals - Convert to Decimal for proper calculation
        subtotal = cart.total_price
        delivery_fee = Decimal('30.00')
        total = subtotal + delivery_fee 
        
        context = {
            'cart_items': cart_items,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'total': total,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_address': customer_address,
            'profile_needs_update': profile_needs_update,
            'gcash_settings': gcash_settings,
        }
        return render(request, 'checkout.html', context)
        
    except Cart.DoesNotExist:
        # If no active cart exists, create one and show an empty checkout
        Cart.objects.create(user=user)
        return render(request, 'checkout.html', {
            'cart_items': [],
            'subtotal': Decimal('0.00'),
            'delivery_fee': Decimal('30.00'),
            'total': Decimal('30.00'),
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_address': customer_address,
            'profile_needs_update': profile_needs_update,
            'gcash_settings': gcash_settings,
        })
    
def get_cart_data(request):
    """API endpoint to get current cart data"""
    cart = get_object_or_404(Cart, user=request.user, is_active=True)
    cart_items = cart.cartitem_set.all().select_related('menu_item')
    
    items_data = []
    for item in cart_items:
        items_data.append({
            'id': item.id,
            'name': item.menu_item.name,
            'quantity': item.quantity,
            'unit_price': float(item.unit_price),
            'total_price': float(item.total_price),
            'customization': item.customization,
        })
    
    return JsonResponse({
        'cart_total': float(cart.total_price),
        'items': items_data
    })
    
@login_required
@require_http_methods(["POST"])
def process_checkout(request):
    """Process the checkout and create order"""
    try:
        # DEBUG: Print all POST data to identify actual field names
        print("DEBUG - All POST data:", dict(request.POST))
        
        # Get user's active cart
        cart = Cart.objects.get(user=request.user, is_active=True)
        cart_items = cart.items.all()
        
        if not cart_items.exists():
            messages.error(request, 'Your cart is empty')
            return redirect('cart')
        
        # Get form data - with comprehensive field name handling
        payment_method = request.POST.get('payment_method')
        delivery_type = request.POST.get('delivery_type', 'delivery')
        delivery_fee_input = request.POST.get('delivery_fee', '30.00')  # Get delivery fee from form
        
        # DEBUG: Log delivery type and payment method
        print(f"DEBUG - Delivery type: {delivery_type}")
        print(f"DEBUG - Payment method: {payment_method}")
        print(f"DEBUG - Delivery fee from form: {delivery_fee_input}")
        
        # Get customer details from the logged-in account/profile
        user = request.user
        customer_profile = getattr(user, 'customer_profile', None)

        # Derive name from account (no manual input required)
        customer_name = f"{user.first_name} {user.last_name}".strip() or user.username

        # Derive contact number and saved address from customer profile
        customer_contact = ''
        profile_address = ''
        if customer_profile:
            customer_contact = customer_profile.phone
            profile_address = customer_profile.address or ''

        address = ''
        note = ''
        
        if delivery_type == 'delivery':
            # Allow address override from form, fallback to profile address
            address = (
                request.POST.get('delivery_address') or 
                request.POST.get('address') or 
                profile_address
            ).strip()
            
            # Note to rider is still collected from form
            note = (
                request.POST.get('riderNote') or 
                request.POST.get('note') or 
                request.POST.get('delivery_note') or
                ''
            ).strip()

            # If the user edited their address here, persist it back to the profile
            if customer_profile and address and address != profile_address:
                customer_profile.address = address
                customer_profile.save()
            
        else:  # pickup
            # Fixed store address for pickup orders
            address = "Roasted Route Main Branch - Villa Cornejo, Kawayan, Biliran"
            
            note = (
                request.POST.get('pickupNote') or 
                request.POST.get('note') or 
                request.POST.get('pickup_note') or
                ''
            ).strip()
        
        # DEBUG: Log extracted values
        print(f"DEBUG - Extracted customer_name: '{customer_name}'")
        print(f"DEBUG - Extracted customer_contact: '{customer_contact}'")
        print(f"DEBUG - Extracted address: '{address}'")
        print(f"DEBUG - Extracted note: '{note}'")
        
        # Enhanced validation with specific error messages
        validation_errors = []
        
        if not payment_method:
            validation_errors.append('Please select a payment method')
        
        if not customer_name or customer_name == '':
            validation_errors.append('Your account does not have a name set. Please update your profile.')
        
        if not customer_contact or customer_contact == '':
            validation_errors.append('Your account does not have a contact number. Please update your profile before checking out.')
        
        if delivery_type == 'delivery' and (not address or address == ''):
            validation_errors.append('Please provide a delivery address')
        
        if validation_errors:
            for error in validation_errors:
                messages.error(request, error)
            return redirect('checkout')
        
        # Use cart's calculated totals
        subtotal = cart.subtotal
        
        # Calculate delivery fee based on delivery type and form input
        try:
            if delivery_type == 'delivery':
                delivery_fee = Decimal(delivery_fee_input)
            else:
                delivery_fee = Decimal('0.00')
        except (ValueError, TypeError):
            # Fallback if delivery fee parsing fails
            delivery_fee = Decimal('30.00') if delivery_type == 'delivery' else Decimal('0.00')
        
        total_amount = subtotal + delivery_fee
        
        # DEBUG: Log calculated amounts
        print(f"DEBUG - Subtotal: {subtotal}")
        print(f"DEBUG - Delivery fee: {delivery_fee}")
        print(f"DEBUG - Total amount: {total_amount}")
        
        # Check stock availability before creating order
        insufficient_stock_items = []
        for cart_item in cart_items:
            menu_item = cart_item.menu_item
            if menu_item.stock < cart_item.quantity:
                insufficient_stock_items.append({
                    'item_name': menu_item.name,
                    'requested': cart_item.quantity,
                    'available': menu_item.stock
                })
        
        # If any items have insufficient stock, return error
        if insufficient_stock_items:
            for item in insufficient_stock_items:
                messages.error(request, f"{item['item_name']}: Only {item['available']} available, you requested {item['requested']}")
            return redirect('checkout')
        
        # Determine initial payment status based on payment method
        if payment_method == 'gcash':
            initial_payment_status = 'waiting_payment'
        else:
            initial_payment_status = 'unpaid'

        # Create order
        order = Order.objects.create(
            # Customer information
            customer=request.user,
            customer_name=customer_name,
            contact_number=customer_contact,
            
            # Order amounts
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total_amount=total_amount,
            
            # Delivery information
            delivery_type=delivery_type,
            address=address,
            note=note,
            
            # Payment information
            payment_method=payment_method,
            payment_status=initial_payment_status,

            # Status
            status='pending'
        )
        
        # Create order items and decrease stock
        for cart_item in cart_items:
            OrderItem.objects.create(
                order=order,
                menu_item=cart_item.menu_item,
                quantity=cart_item.quantity,
                unit_price=cart_item.unit_price,
                customization=cart_item.customization
            )
            
            # Decrease stock for the menu item
            menu_item = cart_item.menu_item
            menu_item.stock -= cart_item.quantity
            menu_item.save()
            
            print(f"Stock updated: {menu_item.name} - decreased by {cart_item.quantity}, new stock: {menu_item.stock}")
        
        # Deactivate cart and clear its items
        cart.is_active = False
        cart.save()
        
        # DEBUG: Log successful order creation
        print(f"DEBUG - Order created successfully: {order.id}")
        print(f"DEBUG - Order delivery type: {order.delivery_type}")
        print(f"DEBUG - Order delivery fee: {order.delivery_fee}")
        print(f"DEBUG - Order total amount: {order.total_amount}")
        
        # SUCCESS: Redirect to order confirmation page
        messages.success(request, 'Order placed successfully!')
        return redirect('order_confirmation', orderz_id=order.id)
        
    except Cart.DoesNotExist:
        messages.error(request, 'No active cart found')
        return redirect('cart')
    except Exception as e:
        # Log the full error for debugging
        print(f"ERROR in process_checkout: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        messages.error(request, f'Error processing order: {str(e)}')
        return redirect('checkout')

@login_required
def add_to_cart(request):
    if request.method == 'POST':
        try:
            menu_item_id = request.POST.get('menu_item_id')
            quantity = int(request.POST.get('quantity', 1))
            customization = request.POST.get('customization', '{}')
            
            # Parse customization JSON
            customization_data = json.loads(customization)
            
            # Get menu item
            menu_item = MenuItem.objects.get(id=menu_item_id)
            
            # Check stock availability
            if menu_item.stock < quantity:
                error_msg = f'Only {menu_item.stock} {menu_item.name}(s) available in stock'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg})
                else:
                    messages.error(request, error_msg)
                    return redirect('order_now')
            
            # Get or create cart for user
            cart, created = Cart.objects.get_or_create(
                user=request.user,
                is_active=True
            )
            
            # Calculate base price from menu item
            base_price = menu_item.price
            
            # Check if similar item already exists in cart (same item + same customization)
            existing_item = None
            for item in cart.items.all():
                if (item.menu_item == menu_item and 
                    item.customization == customization_data):
                    existing_item = item
                    break
            
            if existing_item:
                # Check if adding quantity would exceed stock
                new_quantity = existing_item.quantity + quantity
                if menu_item.stock < new_quantity:
                    error_msg = f'Only {menu_item.stock} {menu_item.name}(s) available in stock. You already have {existing_item.quantity} in your cart.'
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': error_msg})
                    else:
                        messages.error(request, error_msg)
                        return redirect('order_now')
                
                # Update existing item
                existing_item.quantity = new_quantity
                existing_item.save()
                cart_item = existing_item
            else:
                # Create new cart item
                cart_item = CartItem.objects.create(
                    cart=cart,
                    menu_item=menu_item,
                    quantity=quantity,
                    unit_price=base_price,  # Store the current price
                    customization=customization_data
                )
            
            # Update cart total
            cart.update_total()
            
            # Get updated cart count
            cart_count = cart.items.count()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'{menu_item.name} added to cart!',
                    'cart_count': cart_count
                })
            else:
                messages.success(request, f'{menu_item.name} added to cart!')
                return redirect('cart')
                
        except MenuItem.DoesNotExist:
            error_msg = 'Menu item not found'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            else:
                messages.error(request, error_msg)
                return redirect('order_now')
                
        except Exception as e:
            error_msg = f'Error adding item to cart: {str(e)}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg})
            else:
                messages.error(request, error_msg)
                return redirect('order_now')
    
    return redirect('order_now')

@login_required
@require_POST
@csrf_exempt
def place_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            delivery_details = data.get('delivery_details', {})
            
            # Get the user's cart
            cart = Cart.objects.filter(user=request.user).first()
            
            if not cart or not cart.cartitem_set.exists():
                return JsonResponse({'success': False, 'message': 'Cart is empty'})
            
            # Get cart items through the relationship
            cart_items = cart.cartitem_set.all()
            
            # Check stock availability before creating order
            insufficient_stock_items = []
            for cart_item in cart_items:
                menu_item = cart_item.menu_item
                if menu_item.stock < cart_item.quantity:
                    insufficient_stock_items.append({
                        'item_name': menu_item.name,
                        'requested': cart_item.quantity,
                        'available': menu_item.stock
                    })
            
            # If any items have insufficient stock, return error
            if insufficient_stock_items:
                error_messages = []
                for item in insufficient_stock_items:
                    error_messages.append(f"{item['item_name']}: Only {item['available']} available, you requested {item['requested']}")
                return JsonResponse({
                    'success': False, 
                    'message': 'Insufficient stock for some items',
                    'insufficient_items': insufficient_stock_items,
                    'detailed_message': '; '.join(error_messages)
                })
            
            # Calculate amounts using the correct field names
            subtotal = sum(item.unit_price * item.quantity for item in cart_items)  # Use unit_price from CartItem
            delivery_fee = 30 if delivery_details.get('type') == 'delivery' else 0
            total_amount = subtotal + delivery_fee
            
            # Create the order with all fields
            order = Order.objects.create(
                customer=request.user,
                customer_name=delivery_details.get('name'),
                contact_number=delivery_details.get('contact'),
                subtotal=subtotal,
                delivery_fee=delivery_fee,
                total_amount=total_amount,
                delivery_type=delivery_details.get('type', 'delivery'),
                address=delivery_details.get('address', ''),
                note=delivery_details.get('note', ''),
                payment_method=delivery_details.get('payment_method', 'cash'),
                status='pending'
            )
            
            # Create order items from cart items and decrease stock
            for cart_item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    menu_item=cart_item.menu_item,
                    quantity=cart_item.quantity,
                    unit_price=cart_item.unit_price,  # Use unit_price from CartItem
                    customization=cart_item.customization  # Use customization from CartItem
                )
                
                # Decrease stock for the menu item
                menu_item = cart_item.menu_item
                menu_item.stock -= cart_item.quantity
                menu_item.save()
                
                print(f"Stock updated: {menu_item.name} - decreased by {cart_item.quantity}, new stock: {menu_item.stock}")
            
            # Clear the cart items (not the cart itself)
            cart_items.delete()
            
            print(f"DEBUG - Order created successfully: {order.id}")
            
            return JsonResponse({
                'success': True, 
                'order_id': order.id,
                'order_number': order.order_number
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error placing order: {str(e)}'})
        
def order_confirmation(request, orderz_id):
    """Order confirmation with order ID"""
    order = get_object_or_404(Order, id=orderz_id, customer=request.user)
    gcash_settings = GCashSettings.objects.first()
    context = {
        'order': order,
        'gcash_settings': gcash_settings,
    }
    return render(request, 'order_confirmation.html', context)

def order_confirmation_simple(request):
    """Simple order confirmation without ID (shows latest order)"""
    latest_order = Order.objects.filter(customer=request.user).order_by('-created_at').first()
    gcash_settings = GCashSettings.objects.first()
    context = {
        'order': latest_order,
        'gcash_settings': gcash_settings,
    }
    return render(request, 'order_confirmation.html', context)

@login_required
def cart_count(request):
    """Get cart count for AJAX requests"""
    try:
        cart = Cart.objects.get(user=request.user, is_active=True)
        count = cart.items.count()
    except Cart.DoesNotExist:
        count = 0
    
    return JsonResponse({'count': count})

@staff_member_required
def analytics(request):
    """Analytics dashboard view"""
    from django.db.models import Sum, Count, Avg, F
    from django.utils import timezone
    from datetime import timedelta, datetime
    from .models import Order, OrderItem, Customer, MenuItem
    from django.contrib.auth.models import User
    import json
    from collections import defaultdict

    # Time helpers
    period = request.GET.get('period', 'week')
    today = timezone.now().date()
    # Last 7 days including today
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    last_30_start = today - timedelta(days=29)

    # Orders used for revenue/sales metrics (completed/delivered orders only)
    revenue_orders = Order.objects.filter(status__in=['completed', 'delivered'])

    # Sales overview metrics (across the whole dataset, not just selected period)
    sales_today_orders = revenue_orders.filter(created_at__date=today)
    sales_today = sum((o.computed_total for o in sales_today_orders), Decimal('0.00'))

    sales_week_orders = revenue_orders.filter(created_at__date__gte=week_start)
    sales_week = sum((o.computed_total for o in sales_week_orders), Decimal('0.00'))

    sales_month_orders = revenue_orders.filter(created_at__date__gte=month_start)
    sales_month = sum((o.computed_total for o in sales_month_orders), Decimal('0.00'))

    sales_year_orders = revenue_orders.filter(created_at__date__gte=year_start)
    sales_year = sum((o.computed_total for o in sales_year_orders), Decimal('0.00'))

    last_30_orders = revenue_orders.filter(created_at__date__gte=last_30_start)
    last_30_total = sum((o.computed_total for o in last_30_orders), Decimal('0.00'))
    avg_daily_sales = (last_30_total / Decimal('30')) if last_30_total else Decimal('0.00')

    # Determine date range for the selected period (used by charts and detail sections)
    if period == 'today':
        start_date = today
    elif period == 'week':
        start_date = week_start
    elif period == 'month':
        # Use the current calendar month (e.g., all days in November)
        start_date = month_start
    elif period == 'year':
        start_date = year_start
    else:  # all time
        start_date = None

    # Orders within the selected period for revenue-based metrics
    if start_date:
        orders = revenue_orders.filter(created_at__date__gte=start_date)
    else:
        orders = revenue_orders

    # Key metrics for selected period
    total_revenue = sum((o.computed_total for o in orders), Decimal('0.00'))
    total_orders = orders.count()
    completed_orders = orders.filter(status='completed').count()
    # Active non-staff customers (for a more useful metric)
    active_customers = User.objects.filter(is_active=True, is_staff=False, is_superuser=False).count()
    avg_order_value = (total_revenue / total_orders) if total_orders else Decimal('0.00')

    # Order status counts (for donut chart) - include cancelled orders
    if start_date:
        status_orders = Order.objects.filter(created_at__date__gte=start_date)
    else:
        status_orders = Order.objects.all()
    status_counts = {
        'pending': status_orders.filter(status='pending').count(),
        'preparing': status_orders.filter(status='preparing').count(),
        'ready': status_orders.filter(status='ready').count(),
        'completed': status_orders.filter(status='completed').count(),
        'cancelled': status_orders.filter(status='cancelled').count(),
    }

    # Product performance (based on orders in the selected period)
    order_items_qs = OrderItem.objects.filter(order__in=orders)

    product_stats_raw = list(
        order_items_qs.values('menu_item__name', 'menu_item__category').annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('unit_price') * F('quantity')),
        )
    )

    top_products = [
        {
            'name': item['menu_item__name'],
            'category': item['menu_item__category'],
            'quantity': item['total_quantity'] or 0,
            'sales': float(item['total_revenue'] or 0),
        }
        for item in sorted(product_stats_raw, key=lambda x: -(x['total_quantity'] or 0))[:5]
    ]

    least_products = [
        {
            'name': item['menu_item__name'],
            'category': item['menu_item__category'],
            'quantity': item['total_quantity'] or 0,
            'sales': float(item['total_revenue'] or 0),
        }
        for item in sorted(product_stats_raw, key=lambda x: (x['total_quantity'] or 0))[:5]
    ]

    category_sales_raw = list(
        order_items_qs.values('menu_item__category').annotate(
            revenue=Sum(F('unit_price') * F('quantity'))
        ).order_by('-revenue')
    )
    category_sales = [
        {
            'name': item['menu_item__category'],
            'sales': float(item['revenue'] or 0),
        }
        for item in category_sales_raw
    ]

    # Customer insights
    if start_date:
        new_customers_qs = Customer.objects.filter(created_at__date__gte=start_date)
    else:
        new_customers_qs = Customer.objects.all()
    new_customers_count = new_customers_qs.count()

    customer_order_counts = list(
        orders.exclude(customer__isnull=True).values('customer').annotate(
            order_count=Count('id')
        )
    )

    returning_customers_count = sum(
        1 for item in customer_order_counts if item['order_count'] > 1
    )

    top_customer = None
    if customer_order_counts:
        best = max(customer_order_counts, key=lambda x: x['order_count'])
        best_user = User.objects.filter(id=best['customer']).first()
        if best_user:
            top_customer = {
                'name': best_user.get_full_name() or best_user.username,
                'orders': best['order_count'],
            }

    # Peak hours (order volume by hour over selected period)
    peak_hours_raw = list(orders.extra({
        'hour': "strftime('%%H', created_at)"
    }).values('hour').annotate(
        count=Count('id')
    ).order_by('hour'))

    peak_hours = [
        {
            'label': f"{item['hour']}:00" if item['hour'] else '00:00',
            'count': item['count']
        }
        for item in peak_hours_raw
    ]

    # Low stock products (for inventory insight)
    low_stock_items = MenuItem.objects.filter(stock__lt=10).order_by('stock')[:5]

    # Recent orders log (most recent first)
    recent_orders = Order.objects.select_related('customer').order_by('-created_at')[:10]

    # Sales trend data (sales + order volume over time), using computed totals in Python
    sales_trend = []
    trend_labels = []

    if period == 'today':
        # Group by hour for today
        buckets = defaultdict(lambda: {'revenue': Decimal('0.00'), 'orders_count': 0})
        for o in orders:
            dt = timezone.localtime(o.created_at)
            hour = dt.hour
            buckets[hour]['revenue'] += o.computed_total
            buckets[hour]['orders_count'] += 1

        for hour in sorted(buckets.keys()):
            data = buckets[hour]
            label = f"{hour:02d}:00"
            sales_trend.append({
                'label': label,
                'sales': float(data['revenue']),
                'orders': data['orders_count'],
            })
        trend_labels = [entry['label'] for entry in sales_trend]

    elif period == 'week':
        # Group by day for this week
        buckets = defaultdict(lambda: {'revenue': Decimal('0.00'), 'orders_count': 0})
        for o in orders:
            day = timezone.localtime(o.created_at).date()
            buckets[day]['revenue'] += o.computed_total
            buckets[day]['orders_count'] += 1

        for day in sorted(buckets.keys()):
            data = buckets[day]
            label = day.strftime('%a')
            sales_trend.append({
                'label': label,
                'sales': float(data['revenue']),
                'orders': data['orders_count'],
            })
        trend_labels = [entry['label'] for entry in sales_trend]

    elif period == 'month':
        # Group by day of current month
        buckets = defaultdict(lambda: {'revenue': Decimal('0.00'), 'orders_count': 0})
        for o in orders:
            day = timezone.localtime(o.created_at).date()
            buckets[day]['revenue'] += o.computed_total
            buckets[day]['orders_count'] += 1

        for day in sorted(buckets.keys()):
            data = buckets[day]
            label = day.strftime('%b %d')
            sales_trend.append({
                'label': label,
                'sales': float(data['revenue']),
                'orders': data['orders_count'],
            })
        trend_labels = [entry['label'] for entry in sales_trend]

    elif period == 'year':
        # Group by month in the current year
        buckets = defaultdict(lambda: {'revenue': Decimal('0.00'), 'orders_count': 0})
        for o in orders:
            dt = timezone.localtime(o.created_at)
            key = dt.strftime('%Y-%m')  # e.g., '2025-11'
            buckets[key]['revenue'] += o.computed_total
            buckets[key]['orders_count'] += 1

        for key in sorted(buckets.keys()):
            try:
                dt = datetime.strptime(key, '%Y-%m')
                label = dt.strftime('%b')
            except ValueError:
                label = key
            data = buckets[key]
            sales_trend.append({
                'label': label,
                'sales': float(data['revenue']),
                'orders': data['orders_count'],
            })
        trend_labels = [entry['label'] for entry in sales_trend]

    else:
        # All time: group by month-year
        trend_map = defaultdict(lambda: {'revenue': Decimal('0.00'), 'orders_count': 0})
        for order in orders.order_by('created_at'):
            dt = timezone.localtime(order.created_at)
            key = dt.strftime('%Y-%m')  # e.g., '2024-11'
            trend_map[key]['revenue'] += order.computed_total
            trend_map[key]['orders_count'] += 1

        sales_trend = []
        for key in sorted(trend_map.keys()):
            try:
                dt = datetime.strptime(key, '%Y-%m')
                label = dt.strftime('%b %Y')  # e.g., 'Nov 2024'
            except ValueError:
                label = key
            data = trend_map[key]
            sales_trend.append({
                'label': label,
                'sales': float(data['revenue']),
                'orders': data['orders_count'],
            })
        trend_labels = [entry['label'] for entry in sales_trend]

    # Prepare JSON data for charts
    status_counts_json = json.dumps(status_counts)
    sales_trend_json = json.dumps(sales_trend)
    category_sales_json = json.dumps(category_sales)

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'active_customers': active_customers,
        'avg_order_value': avg_order_value,
        'completed_orders': completed_orders,
        'sales_today': sales_today,
        'sales_week': sales_week,
        'sales_month': sales_month,
        'sales_year': sales_year,
        'avg_daily_sales': avg_daily_sales,
        'new_customers_count': new_customers_count,
        'returning_customers_count': returning_customers_count,
        'top_customer': top_customer,
        'status_counts': status_counts_json,
        'top_products': top_products,
        'least_products': least_products,
        'category_sales': category_sales_json,
        'peak_hours': peak_hours,
        'low_stock_items': low_stock_items,
        'recent_orders': recent_orders,
        'sales_trend': sales_trend_json,
        'trend_labels': json.dumps(trend_labels),
        'period': period,
    }

    return render(request, 'analytics.html', context)

@login_required
def password_change(request):
    """Handle password change for authenticated users"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            # Update session to prevent logout
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Your password has been successfully changed!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'password_change.html', {'form': form})