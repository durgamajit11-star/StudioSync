from django.urls import path, include
from . import views

urlpatterns = [
    # USER
    path('user/', views.user_dashboard, name='user_dashboard'),
    path('payment/', views.studio_payment, name='studio_payment'),
    path('user/booking/', views.studio_booking, name='studio_booking'),
    path('profile/', views.user_profile, name='user_profile'),
    path('bookings/', views.user_bookings, name='user_bookings'),
    path('recommendations/', views.user_recommendations, name='user_recommendations'),
    path('explore/', views.explore_studios, name='explore_studios'),
    path('reviews/', views.user_reviews, name='user_reviews'),
    path('reviews/all/', views.user_reviews, name='dashboard_user_reviews'),
    path('profile/logout-all/', views.user_logout_all_devices, name='user_logout_all_devices'),
    path('profile/delete-account/', views.delete_user_account, name='delete_user_account'),
    path('reviews/studio/<int:studio_id>/add/', views.add_review, name='dashboard_add_review'),
    path('reviews/<int:review_id>/edit/', views.edit_review, name='edit_review'),
    path('reviews/<int:review_id>/delete/', views.delete_review, name='delete_review'),
    path('payments/', views.user_payments, name='user_payments'),
    path('notifications/', views.user_notifications, name='user_notifications'),
    path('notifications/live/', views.user_dashboard_live_notifications, name='user_dashboard_live_notifications'),

    #=============== STUDIO===============#
    
    # ================= STUDIO DASHBOARD =================
    path('studio/', views.studio_dashboard, name='studio_dashboard'),
    path('studio/live/', views.studio_dashboard_live, name='studio_dashboard_live'),

    # ================= PORTFOLIO =================
    path('studio/portfolio/', views.studio_portfolio, name='studio_portfolio'),
    path('studio/portfolio/delete/<int:photo_id>/', views.delete_photo, name='delete_photo'),

    # ================= BOOKINGS =================
    path('studio/bookings/', views.studio_bookings, name='studio_bookings'),
    path('studio/bookings/approve/<int:booking_id>/', views.approve_booking, name='studio_approve_booking'),
    path('studio/bookings/cancel/<int:booking_id>/', views.cancel_booking, name='studio_cancel_booking'),
    path('studio/bookings/complete/<int:booking_id>/', views.complete_booking, name='studio_complete_booking'),
    path('studio/bookings/notify/<int:booking_id>/', views.studio_notify_booking_user, name='studio_notify_booking_user'),

    # ================= EARNINGS =================
    path('studio/earnings/', views.studio_earnings, name='studio_earnings'),

    # ================= REVIEWS =================
    path('studio/reviews/', views.studio_reviews, name='studio_reviews'),
    path('studio/reviews/all/', views.studio_reviews, name='dashboard_studio_reviews'),

    # ================= NOTIFICATIONS =================
    path('studio/notifications/', views.studio_notifications, name='studio_notifications'),
    path('studio/notifications/read/<int:notification_id>/', views.studio_mark_notification_read, name='studio_mark_notification_read'),
    path('studio/notifications/read-all/', views.studio_mark_all_notifications_read, name='studio_mark_all_notifications_read'),
    path('studio/notifications/clear/', views.studio_clear_notifications, name='studio_clear_notifications'),
    path('studio/notifications/live/', views.studio_notifications_live, name='studio_notifications_live'),

    # ================= PROFILE =================
    path('studio/profile/', views.studio_profile, name='studio_profile'),
    path('studio/profile/preferences/', views.save_studio_preferences, name='save_studio_preferences'),
    path('studio/profile/logout-all/', views.logout_all_devices, name='logout_all_devices'),
    path('studio/profile/delete-account/', views.delete_studio_account, name='delete_studio_account'),

    # ADMIN APP ROUTES
    path('admin/', include('adminpanel.urls')),
]
