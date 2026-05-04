from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.http import require_POST
from .models import BookingRequest, BookingNote


@login_required
def booking_list(request):
    """Legacy endpoint: route users to dashboard booking center."""
    return redirect('user_bookings')


@login_required
def booking_detail(request, booking_id):
    """Display detailed information about a booking"""
    booking = get_object_or_404(BookingRequest, id=booking_id)
    
    # Check permissions
    if booking.user != request.user and booking.studio.user != request.user:
        messages.error(request, 'You do not have permission to view this booking')
        return redirect('bookings:booking_list')
    
    notes = booking.notes.all()
    
    context = {
        'booking': booking,
        'notes': notes,
    }
    return render(request, 'bookings/booking_detail.html', context)


@login_required
def add_note(request, booking_id):
    """Add a note to a booking"""
    booking = get_object_or_404(BookingRequest, id=booking_id)
    
    # Check permissions
    if booking.user != request.user and booking.studio.user != request.user:
        messages.error(request, 'You do not have permission to add notes to this booking')
        return redirect('bookings:booking_list')
    
    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            BookingNote.objects.create(
                booking=booking,
                user=request.user,
                message=message
            )
            messages.success(request, 'Note added successfully!')
        return redirect('bookings:booking_detail', booking_id=booking_id)
    
    return redirect('bookings:booking_detail', booking_id=booking_id)


@login_required
def cancel_booking(request, booking_id):
    """Cancel a booking"""
    booking = get_object_or_404(BookingRequest, id=booking_id)
    
    if booking.user != request.user:
        messages.error(request, 'Only the booker can cancel this booking')
        return redirect('bookings:booking_list')
    
    if booking.status != 'Pending':
        messages.error(request, 'Only pending bookings can be cancelled')
        return redirect('bookings:booking_detail', booking_id=booking_id)
    
    booking.status = 'Cancelled'
    booking.save()
    messages.success(request, 'Booking cancelled successfully!')
    return redirect('bookings:booking_detail', booking_id=booking_id)


@login_required
@require_POST  # SECURITY FIX: booking approval must be POST-only
def approve_booking(request, booking_id):
    """Approve a booking (studio owner only)"""
    booking = get_object_or_404(BookingRequest, id=booking_id)

    if booking.studio.user != request.user:
        messages.error(request, 'You do not have permission to approve this booking')
        return redirect('studio_bookings')

    booking.status = 'Confirmed'
    booking.save()
    messages.success(request, 'Booking approved successfully!')
    return redirect('bookings:booking_detail', booking_id=booking_id)


@login_required
@require_POST  # SECURITY FIX: booking rejection must be POST-only
def reject_booking(request, booking_id):
    """Reject a booking (studio owner only)"""
    booking = get_object_or_404(BookingRequest, id=booking_id)

    if booking.studio.user != request.user:
        messages.error(request, 'You do not have permission to reject this booking')
        return redirect('studio_bookings')

    booking.status = 'Cancelled'
    booking.save()
    messages.success(request, 'Booking rejected!')
    return redirect('bookings:booking_detail', booking_id=booking_id)
