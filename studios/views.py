from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Avg, Q
from django.core.paginator import Paginator
from django.urls import reverse
from datetime import datetime
from studios.models import Studio, Review, Service, StudioImage
from bookings.models import BookingRequest

# ==================== PUBLIC VIEWS ====================

def studio_detail(request, studio_id):
    """Display detailed information about a specific studio"""
    studio_queryset = Studio.objects.filter(id=studio_id)

    if request.user.is_authenticated:
        if request.user.is_staff:
            studio = get_object_or_404(studio_queryset)
        else:
            studio = get_object_or_404(studio_queryset.filter(Q(is_verified=True) | Q(user=request.user)))
    else:
        studio = get_object_or_404(studio_queryset.filter(is_verified=True))

    portfolios = studio.portfolios.all()[:12]
    studio_images = studio.studio_images.all()[:12]
    services = studio.services.all().order_by('price', 'service_name')
    reviews = studio.reviews.select_related('user').all()

    related_studios = Studio.objects.filter(
        Q(category=studio.category) | Q(location__icontains=studio.location),
        is_verified=True,
    ).exclude(id=studio.id).order_by('-is_featured', '-created_at').distinct()[:4]

    recent_reviews = reviews[:6]
    specialization_tags = [item.strip() for item in (studio.specializations or '').split(',') if item.strip()]

    min_service_price = services.order_by('price').values_list('price', flat=True).first()
    max_service_price = services.order_by('-price').values_list('price', flat=True).first()
    existing_user_review = None
    if request.user.is_authenticated:
        existing_user_review = reviews.filter(user=request.user).first()

    user_booking = None
    booking_status_label = None
    booking_status_tone = 'secondary'
    payment_status_label = None
    open_review_modal = request.GET.get('open_review') == '1'
    review_form_draft = {'rating': '', 'comment': ''}

    can_review_studio = False
    if request.user.is_authenticated:
        user_booking = BookingRequest.objects.filter(
            user=request.user,
            studio=studio,
        ).order_by('-created_at').first()

        can_review_studio = BookingRequest.objects.filter(
            user=request.user,
            studio=studio,
        ).filter(
            Q(status__in=['Confirmed', 'Completed']) | Q(payment_status='Paid')
        ).exists()

        status_tones = {
            'Pending': 'warning',
            'Confirmed': 'success',
            'Completed': 'info',
            'Cancelled': 'danger',
        }
        if user_booking:
            booking_status_label = user_booking.status
            booking_status_tone = status_tones.get(user_booking.status, 'secondary')
            payment_status_label = user_booking.payment_status

        draft_session_key = f'review_draft_studio_{studio.id}'
        review_form_draft = request.session.pop(draft_session_key, review_form_draft)
        if review_form_draft.get('rating') or review_form_draft.get('comment'):
            open_review_modal = True
    
    context = {
        'studio': studio,
        'portfolios': portfolios,
        'studio_images': studio_images,
        'services': services,
        'reviews': recent_reviews,
        'related_studios': related_studios,
        'specialization_tags': specialization_tags,
        'avg_rating': studio.average_rating(),
        'total_reviews': reviews.count(),
        'total_bookings': studio.total_bookings(),
        'confirmed_bookings': studio.confirmed_bookings(),
        'avg_booking_value': studio.average_booking_value(),
        'portfolio_count': portfolios.count(),
        'gallery_count': studio_images.count(),
        'service_count': services.count(),
        'min_service_price': min_service_price,
        'max_service_price': max_service_price,
        'existing_user_review': existing_user_review,
        'can_review_studio': can_review_studio,
        'user_booking': user_booking,
        'booking_status_label': booking_status_label,
        'booking_status_tone': booking_status_tone,
        'payment_status_label': payment_status_label,
        'open_review_modal': open_review_modal,
        'review_form_draft': review_form_draft,
    }
    
    return render(request, 'studios/studio_detail.html', context)


# ==================== USER AUTHENTICATED VIEWS ====================

@login_required
def user_studios_list(request):
    """Users can browse and filter studios"""
    return redirect('explore_studios')


@login_required
def book_studio(request, studio_id):
    """Create a booking with a studio"""
    studio = get_object_or_404(Studio, id=studio_id, is_verified=True)
    
    GST_RATE = Decimal('0.18')

    if request.method == 'POST':
        service_id = request.POST.get('service_id')
        event_type = request.POST.get('event_type')
        date = request.POST.get('date')
        start_time_raw = (request.POST.get('start_time') or '').strip()
        end_time_raw = (request.POST.get('end_time') or '').strip()

        if not all([event_type, date, start_time_raw, end_time_raw]):
            messages.error(request, 'Event type, date, start time, and end time are required')
            return redirect('studios:studio_detail', studio_id=studio_id)  # FIX: namespaced URL

        try:
            start_time_obj = datetime.strptime(start_time_raw, '%H:%M').time()
            end_time_obj = datetime.strptime(end_time_raw, '%H:%M').time()

            start_minutes = (start_time_obj.hour * 60) + start_time_obj.minute
            end_minutes = (end_time_obj.hour * 60) + end_time_obj.minute
            if end_minutes <= start_minutes:
                messages.error(request, 'End time must be later than start time')
                return redirect('studios:studio_detail', studio_id=studio_id)  # FIX: namespaced URL

            duration_minutes = end_minutes - start_minutes
            duration_hours = max(1, (duration_minutes + 59) // 60)
            time_slot = f"{start_time_obj.strftime('%I:%M %p')} - {end_time_obj.strftime('%I:%M %p')}"

            service = None
            if service_id:
                service = Service.objects.filter(id=service_id, studio=studio).first()

            # Base price: service price or hourly rate × duration
            if service and service.price is not None:
                base_price = Decimal(str(service.price)).quantize(Decimal('0.01'))
            else:
                base_rate = Decimal(str(studio.price_per_hour or 0))
                base_price = (base_rate * Decimal(duration_hours)).quantize(Decimal('0.01'))

            # Apply 18% GST — consistent with dashboard booking flow
            gst_amount = (base_price * GST_RATE).quantize(Decimal('0.01'))
            total_price = (base_price + gst_amount).quantize(Decimal('0.01'))

            if total_price <= 0:
                messages.error(request, 'Unable to compute total price. Please contact the studio.')
                return redirect('studios:studio_detail', studio_id=studio_id)

            booking = BookingRequest.objects.create(
                studio=studio,
                user=request.user,
                service=service,
                event_type=event_type,
                date=date,
                booking_date=date,
                time=start_time_obj,
                time_slot=time_slot,
                start_time=start_time_obj,
                end_time=end_time_obj,
                duration_hours=duration_hours,
                amount=total_price,
                total_price=total_price,
                special_requirements=f"Base: ₹{base_price} | GST (18%): ₹{gst_amount}",
            )
            messages.success(request, 'Booking created successfully! Complete payment after studio approval.')
            return redirect('user_bookings')
        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')
            return redirect('studios:studio_detail', studio_id=studio_id)  # FIX: namespaced URL
    
    context = {
        'studio': studio,
        'services': Service.objects.filter(studio=studio).order_by('service_name')
    }
    return render(request, 'studios/book_studio.html', context)


@login_required
def add_review(request, studio_id):
    """Add or update a review for a studio"""
    from bookings.models import BookingRequest

    studio = get_object_or_404(Studio, id=studio_id, is_verified=True)
    
    # Check if user has already reviewed this studio
    existing_review = Review.objects.filter(studio=studio, user=request.user).first()
    has_eligible_booking = BookingRequest.objects.filter(
        user=request.user,
        studio=studio,
    ).filter(
        Q(status__in=['Confirmed', 'Completed']) | Q(payment_status='Paid')
    ).exists()

    if not has_eligible_booking:
        messages.error(request, 'You can review this studio only after a confirmed booking.')
        return redirect('studios:studio_detail', studio_id=studio.id)

    detail_url = reverse('studios:studio_detail', args=[studio.id])
    draft_session_key = f'review_draft_studio_{studio.id}'

    if request.method != 'POST':
        return redirect(f'{detail_url}?open_review=1')
    
    rating = (request.POST.get('rating') or '').strip()
    comment = (request.POST.get('comment') or '').strip()

    request.session[draft_session_key] = {
        'rating': rating,
        'comment': comment,
    }

    if not rating or not comment:
        messages.error(request, 'Rating and comment are required')
        return redirect(f'{detail_url}?open_review=1')

    try:
        rating_value = int(rating)
        if rating_value < 1 or rating_value > 5:
            raise ValueError('Rating out of range')

        if existing_review:
            # Update existing review
            existing_review.rating = rating_value
            existing_review.comment = comment
            existing_review.save(update_fields=['rating', 'comment', 'updated_at'])
            messages.success(request, 'Review updated successfully!')
        else:
            # Create new review
            Review.objects.create(
                studio=studio,
                user=request.user,
                rating=rating_value,
                comment=comment
            )
            messages.success(request, 'Review added successfully!')

        if draft_session_key in request.session:
            del request.session[draft_session_key]
        return redirect('studios:studio_detail', studio_id=studio_id)
    except Exception as e:
        messages.error(request, f'Error saving review: {str(e)}')
        return redirect(f'{detail_url}?open_review=1')
