from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from accounts.decorators import role_required
from accounts.forms import UserUpdateForm
from django.contrib import messages
from django.db.models import Avg, Sum, Count, Min, Max
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.contrib.sessions.models import Session
from django.contrib.auth import logout
from django.utils import timezone
from django.utils.timesince import timesince
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
import logging
import json
import re
from datetime import datetime, timedelta
from studios.models import Studio, Portfolio, Review, Service
from django.db.models import Q 
from .models import StudioPreference, UserPreference
from notifications.models import Notification


logger = logging.getLogger(__name__)


@never_cache
def landing_page(request):
    return render(request, "landing.html")


@never_cache
def landing_explore_studio(request):
    return render(request, "landing_explore_studio.html")


@login_required
@role_required(['USER'])
def studio_payment(request):
    from bookings.models import BookingRequest
    from payments.models import Payment
    from payments.services import (
        PaymentGatewayError,
        build_upi_payload,
        complete_demo_payment,
        payment_gateway_context,
        prepare_checkout_payment,
    )

    upi_id_pattern = re.compile(r'^[a-zA-Z0-9._-]{2,}@[a-zA-Z]{2,}$')

    unpaid_bookings = BookingRequest.objects.filter(
        user=request.user,
        payment_status='Unpaid',
        status='Confirmed',
    ).select_related('studio').order_by('date', 'time')

    pending_payment_bookings = BookingRequest.objects.filter(
        user=request.user,
        payment_status='Unpaid',
        status='Pending',
    ).select_related('studio').order_by('date', 'time')

    selected_booking_id = request.POST.get('booking_id') or request.GET.get('booking_id')
    selected_booking = None
    if selected_booking_id:
        selected_booking = unpaid_bookings.filter(id=selected_booking_id).first()
    if not selected_booking:
        selected_booking = unpaid_bookings.first()

    if request.method == 'POST':
        if not selected_booking:
            messages.error(request, 'Please select a confirmed booking first.')
            return redirect('studio_payment')

        payment_method = request.POST.get('payment_method', '').strip()
        payer_upi_id = request.POST.get('payer_upi_id', '').strip().lower()
        upi_reference = request.POST.get('upi_reference', '').strip().upper()
        valid_methods = {code for code, _ in Payment.PAYMENT_METHOD_CHOICES}

        if payment_method not in valid_methods:
            messages.error(request, 'Please select a valid payment method')
            return redirect(f"{request.path}?booking_id={selected_booking.id}")

        existing_payment = getattr(selected_booking, 'payment', None)
        if existing_payment and existing_payment.status == 'Completed':
            messages.warning(request, 'Payment already exists for this booking')
            return redirect('payments:payment_detail', payment_id=existing_payment.id)

        if payment_gateway_context()['enabled']:
            messages.info(request, 'Use the gateway checkout button to complete this payment.')
            return redirect('payments:create_payment', booking_id=selected_booking.id)

        if payment_method == 'UPI':
            if payer_upi_id and not upi_id_pattern.match(payer_upi_id):
                messages.error(request, 'Please enter a valid UPI ID (example: name@bank)')
                return redirect(f"{request.path}?booking_id={selected_booking.id}")
            if not upi_reference or len(upi_reference) < 8:
                messages.error(request, 'Please enter a valid UPI reference/UTR (minimum 8 characters)')
                return redirect(f"{request.path}?booking_id={selected_booking.id}")

        try:
            payment = prepare_checkout_payment(selected_booking, payment_method)
            payment.payment_method = payment_method
            payment.status = 'Processing'
            payment.save(update_fields=['payment_method', 'status', 'payment_status', 'updated_at'])
            complete_demo_payment(payment, upi_reference=upi_reference, payer_upi_id=payer_upi_id)
            messages.success(request, 'Payment successful.')
            return redirect('payments:payment_detail', payment_id=payment.id)
        except PaymentGatewayError as exc:
            messages.error(request, f'Unable to process payment: {exc}')
            return redirect(f"{request.path}?booking_id={selected_booking.id}")

    upi_payload = None
    gateway = payment_gateway_context()
    selected_payment = None
    if selected_booking:
        upi_payload = build_upi_payload(selected_booking.amount, selected_booking.id, size=340)
        try:
            selected_payment = prepare_checkout_payment(selected_booking)
        except PaymentGatewayError as exc:
            messages.error(request, str(exc))

    context = {
        'unpaid_bookings': unpaid_bookings[:12],
        'pending_payment_bookings': pending_payment_bookings[:12],
        'selected_booking': selected_booking,
        'selected_payment': selected_payment,
        'gateway': gateway,
        'upi_payload': upi_payload,
        'payment_methods': Payment.PAYMENT_METHOD_CHOICES,
    }
    return render(request, "user/dashboard/studio_payment.html", context)

@login_required
@role_required(['USER'])
def studio_booking(request):
    from bookings.models import BookingRequest
    from studios.models import Service

    camera_options = [
        {'code': 'none', 'label': 'Use Studio Default Camera Setup', 'price': Decimal('0')},
        {'code': 'dslr_basic', 'label': 'DSLR Basic Kit', 'price': Decimal('1200')},
        {'code': 'mirrorless_pro', 'label': 'Mirrorless Pro Kit', 'price': Decimal('2500')},
        {'code': 'cinema_4k', 'label': 'Cinema 4K Camera Kit', 'price': Decimal('4200')},
    ]
    camera_price_map = {opt['code']: opt['price'] for opt in camera_options}
    camera_label_map = {opt['code']: opt['label'] for opt in camera_options}
    gst_rate = Decimal('0.18')

    selected_studio_id = request.POST.get('studio_id') or request.GET.get('studio_id')
    if not str(selected_studio_id or '').isdigit():
        messages.info(request, 'Please select a studio from Explore or Studio Detail to start booking.')
        return redirect('explore_studios')

    selected_studio = Studio.objects.filter(id=selected_studio_id, is_verified=True).first()
    if not selected_studio:
        messages.error(request, 'Selected studio is not available for booking right now.')
        return redirect('explore_studios')

    services_queryset = Service.objects.filter(studio=selected_studio).order_by('service_name')

    if request.method == 'POST':
        event_type = request.POST.get('event_type', '').strip()
        booking_date = request.POST.get('date')
        start_time_raw = request.POST.get('start_time', '').strip()
        end_time_raw = request.POST.get('end_time', '').strip()
        location = request.POST.get('location', '').strip()
        special_requirements = request.POST.get('special_requirements', '').strip()
        service_id = request.POST.get('service_id')
        camera_option = request.POST.get('camera_option', 'none').strip()

        if not event_type or not booking_date or not start_time_raw or not end_time_raw:
            messages.error(request, 'Event type, booking date, start time, and end time are required')
            return redirect(f"{request.path}?studio_id={selected_studio.id}")

        service = None
        if service_id:
            service = Service.objects.filter(id=service_id, studio=selected_studio).first()

        try:
            start_time_obj = datetime.strptime(start_time_raw, '%H:%M').time()
            end_time_obj = datetime.strptime(end_time_raw, '%H:%M').time()
        except ValueError:
            messages.error(request, 'Please enter valid start and end times')
            return redirect(f"{request.path}?studio_id={selected_studio.id}")

        start_minutes = (start_time_obj.hour * 60) + start_time_obj.minute
        end_minutes = (end_time_obj.hour * 60) + end_time_obj.minute
        if end_minutes <= start_minutes:
            messages.error(request, 'End time must be later than start time')
            return redirect(f"{request.path}?studio_id={selected_studio.id}")

        duration_minutes = end_minutes - start_minutes
        duration_hours = max(1, (duration_minutes + 59) // 60)
        if duration_hours > 24:
            messages.error(request, 'Booking duration cannot exceed 24 hours')
            return redirect(f"{request.path}?studio_id={selected_studio.id}")

        time_slot = f"{start_time_obj.strftime('%I:%M %p')} - {end_time_obj.strftime('%I:%M %p')}"

        if camera_option not in camera_price_map:
            camera_option = 'none'

        base_rate = selected_studio.price_per_hour or Decimal('0')
        base_price = (base_rate * Decimal(duration_hours)).quantize(Decimal('0.01'))
        service_price = (service.price if service and service.price is not None else Decimal('0')).quantize(Decimal('0.01'))
        camera_price = camera_price_map[camera_option].quantize(Decimal('0.01'))

        subtotal = (base_price + service_price + camera_price).quantize(Decimal('0.01'))
        gst_amount = (subtotal * gst_rate).quantize(Decimal('0.01'))
        total_amount = (subtotal + gst_amount).quantize(Decimal('0.01'))

        if total_amount <= 0:
            messages.error(request, 'Unable to compute total bill. Please contact studio or choose another package.')
            return redirect(f"{request.path}?studio_id={selected_studio.id}")

        notes_lines = []
        if special_requirements:
            notes_lines.append(f"User Notes: {special_requirements}")
        if service:
            notes_lines.append(f"Service: {service.service_name} (Rs. {service_price})")
        if camera_option != 'none':
            notes_lines.append(f"Camera: {camera_label_map[camera_option]} (Rs. {camera_price})")
        notes_lines.append(f"Base Price: Rs. {base_price}")
        notes_lines.append(f"GST (18%): Rs. {gst_amount}")

        final_notes = "\n".join(notes_lines)

        booking = BookingRequest.objects.create(
            studio=selected_studio,
            user=request.user,
            service=service,
            event_type=event_type,
            date=booking_date,
            booking_date=booking_date,
            time=start_time_obj,
            time_slot=time_slot,
            start_time=start_time_obj,
            end_time=end_time_obj,
            duration_hours=duration_hours,
            location=location or selected_studio.location,
            special_requirements=final_notes,
            amount=total_amount,
            total_price=total_amount,
        )

        messages.success(request, 'Booking created successfully. Complete payment to confirm.')
        return redirect(f"{reverse('studio_payment')}?booking_id={booking.id}")

    context = {
        'selected_studio': selected_studio,
        'services': services_queryset,
        'camera_options': camera_options,
        'gst_percent': int(gst_rate * 100),
        'recent_bookings': BookingRequest.objects.filter(user=request.user).select_related('studio').order_by('-created_at')[:6],
    }
    return render(request, "user/dashboard/studio_booking.html", context)

@login_required
@role_required(['USER'])
def user_dashboard(request):
    from bookings.models import BookingRequest
    from payments.models import Payment
    from recommendations.models import StudioRecommendation
    from studios.models import Review

    featured_studios_qs = (
        Studio.objects.filter(is_verified=True)
        .annotate(min_service_price=Min('services__price'))
        .order_by('-is_featured', '-is_verified', '-created_at')
    )
    featured_studios = list(featured_studios_qs[:4])
    for studio in featured_studios:
        hourly_price = studio.price_per_hour if studio.price_per_hour and studio.price_per_hour > 0 else None
        fallback_price = studio.min_service_price if studio.min_service_price and studio.min_service_price > 0 else None
        effective_price = hourly_price or fallback_price

        if effective_price:
            amount = int(effective_price)
            studio.display_price = f"₹ {amount}/hr" if hourly_price else f"From ₹ {amount}"
            if effective_price < 1000:
                studio.price_bucket = 'low'
            elif effective_price < 3000:
                studio.price_bucket = 'mid'
            else:
                studio.price_bucket = 'high'
        elif studio.price_range:
            studio.display_price = studio.price_range
            studio.price_bucket = 'mid'
        else:
            studio.display_price = 'Contact for pricing'
            studio.price_bucket = 'mid'

    user_bookings = BookingRequest.objects.filter(user=request.user)
    recent_bookings = user_bookings.select_related('studio').order_by('-created_at')[:4]
    upcoming_booking = user_bookings.exclude(status='Cancelled').order_by('date', 'time').first()

    recent_payments = Payment.objects.filter(user=request.user).select_related('booking', 'booking__studio').order_by('-created_at')[:4]
    recent_reviews = Review.objects.filter(user=request.user).select_related('studio').order_by('-created_at')[:3]
    recommendations = StudioRecommendation.objects.filter(user=request.user).select_related('studio').order_by('-score')[:4]
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    recent_notifications = notifications[:4]
    unread_notifications = notifications.filter(is_read=False)

    price_insights = Studio.objects.filter(is_verified=True).aggregate(
        min_price=Min('price_per_hour'),
        max_price=Max('price_per_hour'),
        avg_price=Avg('price_per_hour'),
    )

    trending_categories = (
        Studio.objects.filter(is_verified=True)
        .exclude(category__isnull=True)
        .values('category__name')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )

    active_booking = user_bookings.exclude(status='Cancelled').order_by('-updated_at').first()
    booking_timeline = []
    if active_booking:
        booking_timeline = [
            {'label': 'Request Submitted', 'done': True},
            {'label': 'Studio Confirmed', 'done': active_booking.status in ['Confirmed', 'Completed']},
            {'label': 'Payment Completed', 'done': active_booking.payment_status == 'Paid'},
            {'label': 'Shoot Completed', 'done': active_booking.status == 'Completed'},
        ]

    recommendation_reasons = [
        {
            'studio': rec.studio,
            'score': rec.score,
            'reason': rec.reason or 'Matched based on your recent activity and preferences.',
        }
        for rec in recommendations
    ]

    trust_metrics = {
        'verified_studios': Studio.objects.filter(is_verified=True).count(),
        'secure_payments': 'UPI/Card/Wallet protected checkout',
        'support': '24x7 assistance via dashboard and chatbot',
        'refund_policy': 'Refund requests available from payment history',
    }

    spotlight_offers = [
        {'title': 'First Booking Offer', 'desc': 'Get priority support on your first confirmed booking.'},
        {'title': 'Bundle Value Pack', 'desc': 'Combine shoot + editing for better package value.'},
        {'title': 'Prime Time Slots', 'desc': 'Book early for weekend slots at top-rated studios.'},
    ]

    context = {
        'featured_studios': featured_studios,
        'total_bookings': user_bookings.count(),
        'pending_bookings': user_bookings.filter(status='Pending').count(),
        'confirmed_bookings': user_bookings.filter(status='Confirmed').count(),
        'completed_bookings': user_bookings.filter(status='Completed').count(),
        'upcoming_booking': upcoming_booking,
        'recent_bookings': recent_bookings,
        'recent_payments': recent_payments,
        'recent_reviews': recent_reviews,
        'recent_notifications': recent_notifications,
        'unread_notifications_count': unread_notifications.count(),
        'recommendations': recommendations,
        'recommendation_reasons': recommendation_reasons,
        'price_insights': price_insights,
        'trending_categories': trending_categories,
        'active_booking': active_booking,
        'booking_timeline': booking_timeline,
        'trust_metrics': trust_metrics,
        'spotlight_offers': spotlight_offers,
    }
    return render(request, 'user/dashboard/user_dashboard.html', context)


@login_required
@role_required(['USER'])
def user_dashboard_live_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    recent_notifications = notifications[:4]

    payload = {
        'success': True,
        'unread_count': notifications.filter(is_read=False).count(),
        'recent_notifications': [
            {
                'id': n.id,
                'message': n.message,
                'is_read': n.is_read,
                'age': f"{timesince(n.created_at)} ago",
            }
            for n in recent_notifications
        ]
    }
    return JsonResponse(payload)

@login_required
@role_required(['USER'])
def user_profile(request):
    profile_preferences, created = UserPreference.objects.get_or_create(
        user=request.user,
        defaults={
            'dark_theme': (request.COOKIES.get('studiosync_theme', 'dark') == 'dark')
        }
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'update_profile').strip()

        if action == 'save_preferences':
            profile_preferences.email_notifications = request.POST.get('email_notifications') == 'true'
            profile_preferences.sms_alerts = request.POST.get('sms_alerts') == 'true'
            profile_preferences.marketing_emails = request.POST.get('marketing_emails') == 'true'
            profile_preferences.dark_theme = request.POST.get('dark_theme') == 'true'
            profile_preferences.save(update_fields=[
                'email_notifications',
                'sms_alerts',
                'marketing_emails',
                'dark_theme',
                'updated_at',
            ])
            return JsonResponse({'success': True, 'message': 'Preferences saved successfully.'})

        form = UserUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('user_profile')
    else:
        form = UserUpdateForm(instance=request.user)

    return render(request, 'user/dashboard/user_profile.html', {
        'form': form,
        'profile_preferences': {
            'email_notifications': profile_preferences.email_notifications,
            'sms_alerts': profile_preferences.sms_alerts,
            'marketing_emails': profile_preferences.marketing_emails,
            'dark_theme': profile_preferences.dark_theme,
        },
        'profile_preferences_updated_at': profile_preferences.updated_at,
        'profile_preferences_created': created,
    })


@login_required
@role_required(['USER'])
@require_POST
def user_logout_all_devices(request):
    current_session_key = request.session.session_key
    sessions = Session.objects.filter(expire_date__gte=timezone.now())

    removed_sessions = 0
    for session in sessions:
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(request.user.id) and session.session_key != current_session_key:
            session.delete()
            removed_sessions += 1

    return JsonResponse({
        'success': True,
        'message': f'Logged out from {removed_sessions} other device(s).'
    })


@login_required
@role_required(['USER'])
@require_POST
def delete_user_account(request):
    user = request.user
    logout(request)
    user.delete()
    return JsonResponse({'success': True, 'redirect_url': '/'})


@login_required
@role_required(['USER'])
def user_bookings(request):
    from bookings.models import BookingRequest
    status = request.GET.get('status', '').strip()
    search = request.GET.get('search', '').strip()

    base_queryset = BookingRequest.objects.filter(user=request.user)
    bookings = base_queryset.order_by('-created_at')

    if status:
        bookings = bookings.filter(status=status)

    if search:
        bookings = bookings.filter(
            Q(studio__studio_name__icontains=search)
            | Q(event_type__icontains=search)
            | Q(location__icontains=search)
        )

    context = {
        'bookings': bookings,
        'status': status,
        'search': search,
        'total_bookings': base_queryset.count(),
        'pending_count': base_queryset.filter(status='Pending').count(),
        'confirmed_count': base_queryset.filter(status='Confirmed').count(),
        'completed_count': base_queryset.filter(status='Completed').count(),
        'cancelled_count': base_queryset.filter(status='Cancelled').count(),
    }
    return render(request, 'user/dashboard/user_bookings.html', context)

@login_required
@role_required(['USER'])
def user_recommendations(request):
    from recommendations.models import StudioRecommendation
    recommendations = StudioRecommendation.objects.filter(user=request.user, studio__is_verified=True).order_by('-score')[:12]
    return render(request, 'user/dashboard/user_recommendations.html', {'recommendations': recommendations})


@login_required
@role_required(['USER'])
def explore_studios(request):
    query = request.GET.get('q')
    location = request.GET.get('location')
    category = request.GET.get('category')
    sort = request.GET.get('sort')

    studios = Studio.objects.filter(is_verified=True).annotate(
        avg_rating=Avg('reviews__rating'),
        review_count=Count('reviews', distinct=True),
    )

   # 🔍 SMART SEARCH (FIX)
    if query:
        studios = studios.filter(
            Q(studio_name__icontains=query) |
            Q(description__icontains=query) |
            Q(specializations__icontains=query)
        )

    # 📍 Location filter
    if location:
        studios = studios.filter(location__icontains=location)

    # 🎯 Filter by category
    if category:
        studios = studios.filter(category__id=category)

    # 🔥 Sorting options
    if sort == 'rating':
        studios = studios.order_by('-avg_rating', '-review_count', '-is_verified', '-created_at')
    elif sort == 'experience':
        studios = studios.order_by('-experience_years')
    elif sort == 'new':
        studios = studios.order_by('-created_at')

    # 🌟 Featured/Trending Studios (dynamic)
    featured_limit = 6
    manual_featured = Studio.objects.filter(is_featured=True, is_verified=True).annotate(
        avg_rating=Avg('reviews__rating'),
        review_count=Count('reviews', distinct=True),
    ).order_by('-is_verified', '-avg_rating', '-review_count', '-created_at')

    featured_studios = list(manual_featured[:featured_limit])
    featured_ids = {studio.id for studio in featured_studios}

    dynamic_candidates = Studio.objects.filter(is_verified=True).exclude(id__in=featured_ids).annotate(
        avg_rating=Avg('reviews__rating'),
        review_count=Count('reviews', distinct=True),
        confirmed_booking_count=Count(
            'booking_requests',
            filter=Q(booking_requests__status__in=['Confirmed', 'Completed']),
            distinct=True,
        ),
    ).order_by(
        '-is_verified',
        '-avg_rating',
        '-confirmed_booking_count',
        '-review_count',
        '-created_at',
    )

    if len(featured_studios) < featured_limit:
        needed = featured_limit - len(featured_studios)
        featured_studios.extend(list(dynamic_candidates[:needed]))

    featured_section_title = 'Featured Studios' if manual_featured.exists() else 'Trending Studios'
    featured_section_hint = 'Pinned by platform + live ranking' if manual_featured.exists() else 'Auto-ranked by rating, trust, and booking activity'

    # 📂 Categories (for filter buttons)
    from studios.models import Category
    categories = Category.objects.all()

    context = {
        'studios': studios,
        'featured_studios': featured_studios,
        'featured_section_title': featured_section_title,
        'featured_section_hint': featured_section_hint,
        'categories': categories,
        'selected_category': category,
        'selected_sort': sort,
    }

    return render(request, 'user/dashboard/explore_studios.html', context)


@login_required
@role_required(['USER'])
def user_reviews(request):
    from studios.models import Review
    reviews = Review.objects.filter(user=request.user).order_by('-created_at')
    context = {'reviews': reviews}
    return render(request, 'user/dashboard/user_reviews.html', context)


def _user_can_review_studio(user, studio):
    from bookings.models import BookingRequest

    return BookingRequest.objects.filter(
        user=user,
        studio=studio,
    ).filter(
        Q(status__in=['Confirmed', 'Completed']) | Q(payment_status='Paid')
    ).exists()


@login_required
@role_required(['USER'])
def add_review(request, studio_id):
    studio = get_object_or_404(Studio, id=studio_id)
    existing_review = Review.objects.filter(studio=studio, user=request.user).first()
    can_review = _user_can_review_studio(request.user, studio)

    if not can_review:
        messages.error(request, 'You can review this studio only after a confirmed booking.')
        return redirect('studios:studio_detail', studio_id=studio.id)

    if request.method == 'POST':
        rating_raw = (request.POST.get('rating') or '').strip()
        comment = (request.POST.get('comment') or '').strip()

        if not rating_raw or not comment:
            messages.error(request, 'Rating and comment are required.')
            return redirect('dashboard_add_review', studio_id=studio.id)

        try:
            rating = int(rating_raw)
        except ValueError:
            messages.error(request, 'Invalid rating value.')
            return redirect('dashboard_add_review', studio_id=studio.id)

        if rating < 1 or rating > 5:
            messages.error(request, 'Rating must be between 1 and 5.')
            return redirect('dashboard_add_review', studio_id=studio.id)

        if existing_review:
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.save(update_fields=['rating', 'comment', 'updated_at'])
            messages.success(request, 'Review updated successfully.')
        else:
            Review.objects.create(
                studio=studio,
                user=request.user,
                rating=rating,
                comment=comment,
            )
            messages.success(request, 'Review posted successfully.')

        return redirect('studios:studio_detail', studio_id=studio.id)

    return render(request, 'studios/add_review.html', {
        'studio': studio,
        'existing_review': existing_review,
    })


@login_required
@role_required(['USER'])
def edit_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)

    if request.method == 'POST':
        rating_raw = (request.POST.get('rating') or '').strip()
        comment = (request.POST.get('comment') or '').strip()

        if not rating_raw or not comment:
            messages.error(request, 'Rating and comment are required.')
            return redirect('edit_review', review_id=review.id)

        try:
            rating = int(rating_raw)
        except ValueError:
            messages.error(request, 'Invalid rating value.')
            return redirect('edit_review', review_id=review.id)

        if rating < 1 or rating > 5:
            messages.error(request, 'Rating must be between 1 and 5.')
            return redirect('edit_review', review_id=review.id)

        review.rating = rating
        review.comment = comment
        review.save(update_fields=['rating', 'comment', 'updated_at'])
        messages.success(request, 'Review updated successfully.')
        return redirect('user_reviews')

    return render(request, 'studios/add_review.html', {
        'studio': review.studio,
        'existing_review': review,
    })


@login_required
@role_required(['USER'])
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    review.delete()
    messages.success(request, 'Review deleted successfully.')
    return redirect('user_reviews')


@login_required
@role_required(['USER'])
def user_payments(request):
    from payments.models import Payment
    status = request.GET.get('status', '').strip()
    method = request.GET.get('method', '').strip()
    search = request.GET.get('search', '').strip()

    base_queryset = Payment.objects.filter(user=request.user)
    payments = base_queryset.order_by('-created_at')

    if status:
        payments = payments.filter(status=status)

    if method:
        payments = payments.filter(payment_method=method)

    if search:
        payments = payments.filter(
            Q(transaction_id__icontains=search)
            | Q(booking__studio__studio_name__icontains=search)
        )

    completed_queryset = base_queryset.filter(status='Completed')
    total_amount = completed_queryset.aggregate(total=Sum('amount'))['total'] or 0

    context = {
        'payments': payments,
        'total_amount': total_amount,
        'status': status,
        'method': method,
        'search': search,
        'total_payments': base_queryset.count(),
        'completed_count': completed_queryset.count(),
        'processing_count': base_queryset.filter(status='Processing').count(),
        'pending_count': base_queryset.filter(status='Pending').count(),
        'failed_count': base_queryset.filter(status='Failed').count(),
    }
    return render(request, 'user/dashboard/user_payments.html', context)


@login_required
@role_required(['USER'])
def user_notifications(request):
    return render(request, 'user/dashboard/user_notifications.html')


@login_required
@role_required(['STUDIO'])
def studio_dashboard(request):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        # Create studio profile if doesn't exist
        try:
            studio = Studio.objects.create(
                user=request.user,
                studio_name=request.user.studio_name or f"{request.user.username}'s Studio",
                location=request.user.address or 'Not specified'
            )
            messages.success(request, 'Studio profile created successfully!')
        except Exception as e:
            messages.error(request, f'Error creating studio profile: {str(e)}')
            return redirect('user_dashboard')
    
    # Get stats
    from bookings.models import BookingRequest
    from payments.models import Payment

    bookings_qs = BookingRequest.objects.filter(studio=studio)
    total_bookings = bookings_qs.count()
    pending_bookings = bookings_qs.filter(status='Pending').count()
    confirmed_bookings = bookings_qs.filter(status='Confirmed').count()
    completed_bookings = bookings_qs.filter(status='Completed').count()

    avg_rating = studio.average_rating()
    total_earnings = bookings_qs.filter(status='Confirmed').aggregate(Sum('amount'))['amount__sum'] or 0
    portfolio_count = Portfolio.objects.filter(studio=studio).count()
    total_reviews = Review.objects.filter(studio=studio).count()

    today = timezone.localdate()
    today_bookings = (
        bookings_qs.filter(date=today)
        .select_related('user', 'service')
        .order_by('time', 'time_slot')[:6]
    )
    recent_bookings = (
        bookings_qs.select_related('user', 'service')
        .order_by('-created_at')[:6]
    )

    monthly = (
        bookings_qs.filter(status='Confirmed')
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    revenue_labels = [item['month'].strftime('%b %Y') for item in monthly]
    revenue_data = [float(item['total'] or 0) for item in monthly]

    payment_summary = Payment.objects.filter(booking__studio=studio).aggregate(
        completed=Count('id', filter=Q(status='Completed')),
        processing=Count('id', filter=Q(status='Processing')),
        pending=Count('id', filter=Q(status='Pending')),
        failed=Count('id', filter=Q(status='Failed')),
    )

    booking_rate = int((confirmed_bookings / total_bookings) * 100) if total_bookings else 0
    satisfaction_rate = int((float(avg_rating) / 5) * 100) if avg_rating else 0
    portfolio_completion_rate = min(100, int((portfolio_count / 20) * 100)) if portfolio_count else 0
    booking_status_data = [confirmed_bookings, pending_bookings, completed_bookings]
    
    context = {
        'studio': studio,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'confirmed_bookings': confirmed_bookings,
        'completed_bookings': completed_bookings,
        'avg_rating': avg_rating,
        'total_earnings': total_earnings,
        'portfolio_count': portfolio_count,
        'total_reviews': total_reviews,
        'today_bookings': today_bookings,
        'recent_bookings': recent_bookings,
        'revenue_labels': revenue_labels,
        'revenue_data': revenue_data,
        'payment_summary': payment_summary,
        'booking_rate': booking_rate,
        'satisfaction_rate': satisfaction_rate,
        'portfolio_completion_rate': portfolio_completion_rate,
        'booking_status_data': booking_status_data,
    }
    return render(request, 'studio/dashboard/studio_dashboard.html', context)


@login_required
@role_required(['STUDIO'])
def studio_dashboard_live(request):
    studio = Studio.objects.filter(user=request.user).first()

    if not studio:
        return JsonResponse({'success': False, 'message': 'Studio profile not found.'}, status=404)

    from bookings.models import BookingRequest

    bookings_qs = BookingRequest.objects.filter(studio=studio)
    total_bookings = bookings_qs.count()
    pending_bookings = bookings_qs.filter(status='Pending').count()
    confirmed_bookings = bookings_qs.filter(status='Confirmed').count()
    completed_bookings = bookings_qs.filter(status='Completed').count()
    avg_rating = float(studio.average_rating() or 0)
    total_earnings = float(bookings_qs.filter(status='Confirmed').aggregate(Sum('amount'))['amount__sum'] or 0)

    today = timezone.localdate()
    today_bookings = (
        bookings_qs.filter(date=today)
        .select_related('user')
        .order_by('time', 'time_slot')[:6]
    )
    recent_bookings = (
        bookings_qs.select_related('user')
        .order_by('-created_at')[:4]
    )

    payload = {
        'success': True,
        'last_updated': timezone.localtime().strftime('%I:%M:%S %p'),
        'stats': {
            'total_bookings': total_bookings,
            'confirmed_bookings': confirmed_bookings,
            'total_earnings': round(total_earnings, 2),
            'avg_rating': round(avg_rating, 1),
            'pending_bookings': pending_bookings,
            'completed_bookings': completed_bookings,
        },
        'today_bookings': [
            {
                'time': b.time_window_display,
                'event_type': b.event_type or 'Shoot Session',
                'client': b.user.get_full_name() or b.user.username,
            }
            for b in today_bookings
        ],
        'recent_activity': [
            {
                'event': f"{(b.event_type or 'Shoot')} booking {(b.status or '').lower()}",
                'age': f"{timesince(b.created_at)} ago",
            }
            for b in recent_bookings
        ],
        'booking_status_data': [confirmed_bookings, pending_bookings, completed_bookings],
    }

    return JsonResponse(payload)


@login_required
@role_required(['STUDIO'])
def studio_portfolio(request):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    if request.method == 'POST':
        is_ajax_upload = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        images = request.FILES.getlist('image')
        caption = (request.POST.get('description') or request.POST.get('caption') or '').strip()
        category = (request.POST.get('category') or 'other').strip().lower()
        tags = (request.POST.get('tags') or '').strip()
        max_image_size = 4 * 1024 * 1024

        allowed_categories = {'wedding', 'product', 'fashion', 'other'}
        if category not in allowed_categories:
            category = 'other'

        if images:
            created = 0
            for image in images:
                if image.size > max_image_size:
                    message = 'Each portfolio image must be under 4MB. Please choose smaller images or upload fewer at a time.'
                    messages.error(request, message)
                    if is_ajax_upload:
                        return JsonResponse({'success': False, 'message': message}, status=413)
                    return redirect('studio_portfolio')

                base_caption = caption
                if not base_caption:
                    raw_name = (image.name or 'Portfolio Photo').rsplit('.', 1)[0]
                    base_caption = raw_name.replace('_', ' ').replace('-', ' ').strip().title() or 'Portfolio Photo'

                try:
                    Portfolio.objects.create(
                        studio=studio,
                        image=image,
                        caption=base_caption[:255],
                        category=category,
                        tags=tags[:255],
                    )
                    created += 1
                except Exception as exc:
                    logger.exception('Portfolio image upload failed for studio_id=%s', studio.id)
                    message = 'Unable to upload this image. Please check Cloudinary configuration and try again.'
                    messages.error(
                        request,
                        message
                    )
                    if is_ajax_upload:
                        return JsonResponse({'success': False, 'message': message}, status=500)
                    return redirect('studio_portfolio')

            messages.success(request, f'Uploaded {created} photo(s) successfully!')
            if is_ajax_upload:
                return JsonResponse({'success': True, 'created': created})
            return redirect('studio_portfolio')
        else:
            message = 'Please select at least one image to upload.'
            messages.error(request, message)
            if is_ajax_upload:
                return JsonResponse({'success': False, 'message': message}, status=400)

    portfolios = Portfolio.objects.filter(studio=studio).order_by('-uploaded_at')
    total_photos = portfolios.count()
    this_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_uploads = portfolios.filter(uploaded_at__gte=this_month_start).count()
    last_uploaded_at = portfolios.first().uploaded_at if total_photos else None
    portfolio_target = 24
    portfolio_completion_rate = min(100, int((total_photos / portfolio_target) * 100)) if total_photos else 0
    category_counts = {
        'all': total_photos,
        'wedding': portfolios.filter(category='wedding').count(),
        'product': portfolios.filter(category='product').count(),
        'fashion': portfolios.filter(category='fashion').count(),
        'other': portfolios.filter(category='other').count(),
    }

    return render(request, 'studio/dashboard/studio_portfolio.html', {
        'studio': studio,
        'portfolios': portfolios,
        'total_photos': total_photos,
        'this_month_uploads': this_month_uploads,
        'last_uploaded_at': last_uploaded_at,
        'portfolio_completion_rate': portfolio_completion_rate,
        'portfolio_target': portfolio_target,
        'category_counts': category_counts,
    })


@login_required
@role_required(['STUDIO'])
def studio_bookings(request):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')
    
    from bookings.models import BookingRequest
    bookings = BookingRequest.objects.filter(studio=studio).order_by('-created_at')
    
    # Summary stats
    pending = bookings.filter(status='Pending').count()
    confirmed = bookings.filter(status='Confirmed').count()
    urgent_count = bookings.filter(status='Pending', created_at__lte=timezone.now() - timedelta(days=2)).count()

    return render(request, 'studio/dashboard/studio_bookings.html', {
        'studio': studio,
        'bookings': bookings,
        'pending': pending,
        'confirmed': confirmed,
        'urgent_count': urgent_count,
    })


@login_required
@role_required(['STUDIO'])
def studio_earnings(request):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    from bookings.models import BookingRequest
    from payments.models import Payment
    
    bookings = BookingRequest.objects.filter(studio=studio)
    total_earnings = bookings.filter(payment_status="Paid").aggregate(Sum('amount'))['amount__sum'] or 0
    total_bookings = bookings.count()
    completed_bookings = bookings.filter(status="Completed").count()
    pending_amount = bookings.filter(payment_status="Unpaid").aggregate(Sum('amount'))['amount__sum'] or 0

    payments = Payment.objects.filter(booking__studio=studio).select_related('booking', 'user').order_by('-created_at')
    recent_payments = payments[:10]

    avg_booking_value = bookings.filter(status='Confirmed').aggregate(avg=Avg('amount'))['avg'] or 0
    paid_count = payments.filter(status='Completed').count()
    payment_completion_rate = int((paid_count / total_bookings) * 100) if total_bookings else 0

    monthly = (
        payments.filter(status='Completed')
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    revenue_labels = [item['month'].strftime('%b %Y') for item in monthly]
    revenue_data = [float(item['total'] or 0) for item in monthly]

    status_counts = {
        'paid': payments.filter(status='Completed').count(),
        'pending': payments.filter(status__in=['Pending', 'Processing']).count(),
        'failed': payments.filter(status='Failed').count(),
    }

    top_services = (
        bookings.filter(status='Confirmed')
        .values('service__service_name')
        .annotate(bookings_count=Count('id'), revenue=Sum('amount'))
        .order_by('-bookings_count')[:3]
    )

    recent_booking_dates = list(
        payments.filter(status='Completed', completed_at__isnull=False)
        .values_list('booking__date', 'completed_at')[:40]
    )
    total_days = 0
    total_samples = 0
    for booking_date, completed_at in recent_booking_dates:
        if booking_date and completed_at:
            total_days += max(0, (completed_at.date() - booking_date).days)
            total_samples += 1
    avg_days_to_payment = round(total_days / total_samples, 1) if total_samples else 0

    monthly_average = round(float(total_earnings) / 6, 2) if float(total_earnings) > 0 else 0

    return render(request, 'studio/dashboard/studio_earnings.html', {
        'total_earnings': total_earnings,
        'total_bookings': total_bookings,
        'completed_bookings': completed_bookings,
        'pending_amount': pending_amount,
        'recent_payments': recent_payments,
        'avg_booking_value': avg_booking_value,
        'monthly_average': monthly_average,
        'payment_completion_rate': payment_completion_rate,
        'avg_days_to_payment': avg_days_to_payment,
        'revenue_labels': revenue_labels,
        'revenue_data': revenue_data,
        'status_counts': status_counts,
        'top_services': top_services,
    })


@login_required
@role_required(['STUDIO'])
def studio_reviews(request):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    from studios.models import Review
    reviews = Review.objects.filter(studio=studio).order_by('-created_at')
    avg_rating = studio.average_rating()

    rating_counts = {
        5: reviews.filter(rating=5).count(),
        4: reviews.filter(rating=4).count(),
        3: reviews.filter(rating=3).count(),
        2: reviews.filter(rating=2).count(),
        1: reviews.filter(rating=1).count(),
    }
    total_reviews = reviews.count()
    positive_count = rating_counts[5] + rating_counts[4]

    current_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    this_month_count = reviews.filter(created_at__gte=current_month_start).count()
    last_month_count = reviews.filter(created_at__gte=previous_month_start, created_at__lt=current_month_start).count()
    trend_count = this_month_count - last_month_count

    rating_rows = []
    for stars in [5, 4, 3, 2, 1]:
        count = rating_counts[stars]
        percent = int((count / total_reviews) * 100) if total_reviews else 0
        rating_rows.append({'stars': stars, 'count': count, 'percent': percent})
    rating_distribution_data = [row['count'] for row in rating_rows]

    return render(request, 'studio/dashboard/studio_reviews.html', {
        'studio': studio,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'total_reviews': total_reviews,
        'positive_count': positive_count,
        'trend_count': trend_count,
        'rating_counts': rating_counts,
        'rating_rows': rating_rows,
        'rating_distribution_data': rating_distribution_data,
    })


@login_required
@role_required(['STUDIO'])
def studio_notifications(request):
    notifications = Notification.objects.filter(
        user=request.user,
        type='admin_notice'
    ).order_by('-created_at')

    unread_count = notifications.filter(is_read=False).count()
    read_count = notifications.count() - unread_count

    return render(request, 'studio/dashboard/studio_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'read_count': read_count,
        'total_count': notifications.count(),
    })


@login_required
@role_required(['STUDIO'])
@require_POST
def studio_mark_notification_read(request, notification_id):
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user,
        type='admin_notice'
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        messages.success(request, 'Notification marked as read.')
    return redirect('studio_notifications')


@login_required
@role_required(['STUDIO'])
@require_POST
def studio_mark_all_notifications_read(request):
    updated_count = Notification.objects.filter(
        user=request.user,
        type='admin_notice',
        is_read=False
    ).update(is_read=True)
    messages.success(request, f'Marked {updated_count} notification(s) as read.')
    return redirect('studio_notifications')


@login_required
@role_required(['STUDIO'])
@require_POST
def studio_clear_notifications(request):
    deleted_count, _ = Notification.objects.filter(
        user=request.user,
        type='admin_notice'
    ).delete()
    messages.success(request, f'Cleared {deleted_count} notification(s).')
    return redirect('studio_notifications')


@login_required
@role_required(['STUDIO'])
def studio_notifications_live(request):
    notifications = Notification.objects.filter(
        user=request.user,
        type='admin_notice'
    ).order_by('-created_at')

    recent_notifications = notifications[:8]
    unread_count = notifications.filter(is_read=False).count()
    total_count = notifications.count()

    payload = {
        'success': True,
        'unread_count': unread_count,
        'read_count': total_count - unread_count,
        'total_count': total_count,
        'notifications': [
            {
                'id': n.id,
                'message': n.message,
                'is_read': n.is_read,
                'created_display': n.created_at.strftime('%b %d, %Y, %I:%M %p'),
                'age': f"{timesince(n.created_at)} ago",
                'mark_read_url': reverse('studio_mark_notification_read', args=[n.id]),
            }
            for n in recent_notifications
        ],
    }
    return JsonResponse(payload)


@login_required
@role_required(['STUDIO'])
def studio_profile(request):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    preferences, _ = StudioPreference.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user_instance = form.save(commit=False)
            user_instance.owner_name = (request.POST.get('owner_name', '') or '').strip()
            user_instance.address = request.POST.get('owner_address', '') or ''
            user_instance.bio = request.POST.get('owner_bio', '') or ''

            license_file = request.FILES.get('studio_license')
            if license_file:
                user_instance.license = license_file

            portfolio_file = request.FILES.get('studio_portfolio')
            if portfolio_file:
                user_instance.portfolio = portfolio_file

            user_instance.save()
            # Studio profile fields editable by studio owner
            studio.studio_name = request.POST.get('studio_name', studio.studio_name).strip() or studio.studio_name
            studio.location = request.POST.get('studio_location', studio.location).strip() or studio.location
            studio.description = request.POST.get('studio_description', '')
            studio.phone = request.POST.get('studio_phone', '')
            studio.email = request.POST.get('studio_email', '')
            studio.website = request.POST.get('studio_website', '')
            studio.specializations = request.POST.get('studio_specializations', '')

            experience_raw = request.POST.get('experience_years', '').strip()
            if experience_raw:
                try:
                    studio.experience_years = max(0, int(experience_raw))
                except ValueError:
                    pass

            price_per_hour_raw = request.POST.get('price_per_hour', '').strip()
            if price_per_hour_raw:
                try:
                    studio.price_per_hour = Decimal(price_per_hour_raw)
                except InvalidOperation:
                    pass

            cover_image = request.FILES.get('studio_cover_image')
            if cover_image:
                studio.profile_image = cover_image

            studio.save()

            # Replace services with submitted rows to keep studio offerings in sync.
            service_names = request.POST.getlist('service_name[]')
            service_prices = request.POST.getlist('service_price[]')
            service_descriptions = request.POST.getlist('service_description[]')

            Service.objects.filter(studio=studio).delete()
            rows_count = max(len(service_names), len(service_prices), len(service_descriptions))
            for idx in range(rows_count):
                name = (service_names[idx] if idx < len(service_names) else '').strip()
                price_raw = (service_prices[idx] if idx < len(service_prices) else '').strip()
                description = (service_descriptions[idx] if idx < len(service_descriptions) else '').strip()

                if not name or not price_raw:
                    continue

                try:
                    price_value = Decimal(price_raw)
                except InvalidOperation:
                    continue

                if price_value < 0:
                    continue

                Service.objects.create(
                    studio=studio,
                    service_name=name,
                    price=price_value,
                    description=description,
                )

            messages.success(request, "Profile updated successfully!")
            return redirect('studio_profile')
    else:
        form = UserUpdateForm(instance=request.user)

    verification_checklist = [
        {
            'label': 'License document uploaded',
            'done': bool(request.user.license),
        },
        {
            'label': 'Portfolio document uploaded',
            'done': bool(request.user.portfolio),
        },
        {
            'label': 'Studio name and location set',
            'done': bool((studio.studio_name or '').strip() and (studio.location or '').strip()),
        },
        {
            'label': 'Studio description added',
            'done': bool((studio.description or '').strip()),
        },
        {
            'label': 'Studio contact phone and email set',
            'done': bool((studio.phone or '').strip() and (studio.email or '').strip()),
        },
        {
            'label': 'At least one service listed',
            'done': studio.services.exists(),
        },
    ]
    verification_completed = sum(1 for item in verification_checklist if item['done'])

    return render(request, 'studio/dashboard/studio_profile.html', {
        'studio': studio,
        'studio_services': studio.services.all().order_by('service_name'),
        'form': form,
        'user': request.user,
        'preferences': preferences,
        'verification_checklist': verification_checklist,
        'verification_completed': verification_completed,
    })


@login_required
@role_required(['STUDIO'])
@require_POST
def save_studio_preferences(request):
    preferences, _ = StudioPreference.objects.get_or_create(user=request.user)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)

    preferences.email_notifications = bool(payload.get('email_notifications', preferences.email_notifications))
    preferences.sms_alerts = bool(payload.get('sms_alerts', preferences.sms_alerts))
    preferences.portfolio_visibility = bool(payload.get('portfolio_visibility', preferences.portfolio_visibility))
    preferences.marketing_emails = bool(payload.get('marketing_emails', preferences.marketing_emails))
    preferences.two_factor_enabled = bool(payload.get('two_factor_enabled', preferences.two_factor_enabled))
    preferences.device_login_alerts = bool(payload.get('device_login_alerts', preferences.device_login_alerts))
    preferences.save()

    return JsonResponse({'success': True, 'message': 'Preferences saved successfully.'})


@login_required
@role_required(['STUDIO'])
@require_POST
def logout_all_devices(request):
    current_session_key = request.session.session_key
    sessions = Session.objects.filter(expire_date__gte=timezone.now())

    removed_sessions = 0
    for session in sessions:
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == str(request.user.id) and session.session_key != current_session_key:
            session.delete()
            removed_sessions += 1

    return JsonResponse({
        'success': True,
        'message': f'Logged out from {removed_sessions} other device(s).'
    })


@login_required
@role_required(['STUDIO'])
@require_POST
def delete_studio_account(request):
    user = request.user
    logout(request)
    user.delete()
    return JsonResponse({'success': True, 'redirect_url': '/'})


@login_required
@role_required(['STUDIO'])
def delete_photo(request, photo_id):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    photo = get_object_or_404(Portfolio, id=photo_id, studio=studio)
    photo.delete()
    messages.success(request, 'Photo deleted successfully!')

    return redirect('studio_portfolio')


@login_required
@role_required(['STUDIO'])
def approve_booking(request, booking_id):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    from bookings.models import BookingRequest
    booking = get_object_or_404(BookingRequest, id=booking_id, studio=studio)
    booking.status = "Confirmed"
    booking.save()
    messages.success(request, 'Booking approved!')

    return redirect('studio_bookings')


@login_required
@role_required(['STUDIO'])
def cancel_booking(request, booking_id):
    studio = Studio.objects.filter(user=request.user).first()
    
    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    from bookings.models import BookingRequest
    booking = get_object_or_404(BookingRequest, id=booking_id, studio=studio)
    booking.status = "Cancelled"
    booking.save()
    messages.success(request, 'Booking cancelled!')

    return redirect('studio_bookings')


@login_required
@role_required(['STUDIO'])
@require_POST
def complete_booking(request, booking_id):
    studio = Studio.objects.filter(user=request.user).first()

    if not studio:
        messages.error(request, 'Studio profile not found')
        return redirect('studio_dashboard')

    from bookings.models import BookingRequest
    booking = get_object_or_404(BookingRequest, id=booking_id, studio=studio)

    if booking.status != 'Confirmed':
        messages.warning(request, 'Only confirmed bookings can be marked as completed.')
        return redirect('studio_bookings')

    booking.status = 'Completed'
    booking.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Booking marked as completed!')

    return redirect('studio_bookings')
