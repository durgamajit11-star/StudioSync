from django.urls import path

from . import views

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('chatbot/policy-report/weekly/', views.export_weekly_policy_report, name='admin_weekly_policy_report'),
    path('users/', views.manage_users, name='manage_users'),
    path('admins/', views.manage_admins, name='manage_admins'),
    path('users/toggle-status/<int:id>/', views.toggle_user_status, name='toggle_user_status'),
    path('admins/toggle-status/<int:id>/', views.toggle_admin_status, name='toggle_admin_status'),
    path('users/delete/<int:id>/', views.delete_user, name='delete_user'),
    path('users/notify/<int:id>/', views.notify_user, name='notify_user'),
    path('studios/', views.manage_studios, name='manage_studios'),
    path('studios/approve/<int:id>/', views.approve_studio, name='approve_studio'),
    path('studios/reject/<int:id>/', views.reject_studio, name='reject_studio'),
    path('studios/notify/<int:id>/', views.notify_studio, name='notify_studio'),
    path('studios/notify-selected/', views.notify_selected_studios, name='notify_selected_studios'),
    path('studios/<int:id>/', views.studio_review, name='studio_review'),
    path('bookings/', views.admin_bookings, name='admin_bookings'),
    path('bookings/cancel/<int:id>/', views.admin_cancel_booking, name='admin_cancel_booking'),
    path('payments/', views.admin_payments, name='admin_payments'),
    path('payments/<int:payment_id>/mark-payout-paid/', views.mark_studio_payout_paid, name='mark_studio_payout_paid'),
]
