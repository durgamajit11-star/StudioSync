from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.payment_list, name='payment_list'),
    path('detail/<int:payment_id>/', views.payment_detail, name='payment_detail'),
    path('create/<int:booking_id>/', views.create_payment, name='create_payment'),
    path('razorpay/complete/<int:payment_id>/', views.razorpay_checkout_complete, name='razorpay_checkout_complete'),
    path('razorpay/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('refund/<int:payment_id>/', views.request_refund, name='request_refund'),
]
