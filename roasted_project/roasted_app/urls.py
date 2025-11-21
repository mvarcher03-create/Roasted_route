# roasted_app/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Authentication URLs
    path('', views.home, name='home'),
    path('login/', views.custom_login, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.custom_logout, name='logout'),
    
    # Admin URLs
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('menu-management/', views.menu_management, name='menu_management'),
    path('add-menu-item/', views.add_menu_item, name='add_menu_item'),
    path('edit-menu-item/<int:item_id>/', views.edit_menu_item, name='edit_menu_item'),
    path('delete-menu-item/<int:item_id>/', views.delete_menu_item, name='delete_menu_item'),
    path('toggle-availability/<int:item_id>/', views.toggle_availability, name='toggle_availability'),
    path('menu-item-sales/<int:item_id>/', views.menu_item_sales, name='menu_item_sales'),
    path('manage-customers/', views.manage_customers, name='manage_customers'),
    path('activity-logs/', views.activity_logs, name='activity_logs'),
    path('analytics/', views.analytics, name='analytics'),
    path('view-orders/', views.view_orders, name='view_orders'),
    path('order-detail/<int:order_id>/', views.order_detail, name='order_detail'),
    path('update-order-status/<int:order_id>/', views.update_order_status, name='update_order_status'),
    path('update-payment-status/<int:order_id>/', views.update_payment_status, name='update_payment_status'),
    path('cancel-order/<int:order_id>/', views.cancel_order, name='cancel_order'),
    
    # Customer URLs
    path('customer-dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('order-now/', views.order_now, name='order_now'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('order-history/', views.order_history, name='order_history'),
    path('reorder/<int:order_id>/', views.reorder_order, name='reorder_order'),
    path('rate-order/<int:order_id>/', views.rate_order, name='rate_order'),
    path('notify-admin-order-delivered/<int:order_id>/', views.notify_admin_order_delivered, name='notify_admin_order_delivered'),
    path('profile/', views.profile, name='profile'),
    path('change-password/', views.password_change, name='password_change'),
    path('customer/cancel-order/<int:order_id>/', views.customer_cancel_order, name='customer_cancel_order'),
    path('orders/<int:order_id>/upload-payment-proof/', views.upload_payment_proof, name='upload_payment_proof'),
    path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Cart and Checkout URLs
    path('cart/', views.cart_view, name='cart'),
    path('update-cart-item/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('add-to-cart/', views.add_to_cart, name='add_to_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('process-checkout/', views.process_checkout, name='process_checkout'),
    path('order-confirmation/<int:orderz_id>/', views.order_confirmation, name='order_confirmation'),
    path('order-confirmation/', views.order_confirmation_simple, name='order_confirmation_simple'),
    
    # API URLs
    path('cart-count/', views.cart_count, name='cart_count'),
    path('get-cart-data/', views.get_cart_data, name='get_cart_data'),
    path('place-order/', views.place_order, name='place_order'),
    path('api/update-order-status/<int:order_id>/', views.update_order_status, name='api_update_order_status'),
]