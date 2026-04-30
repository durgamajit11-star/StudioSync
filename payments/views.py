import json
import re
from decimal import Decimal, InvalidOperation

from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Payment, PaymentRefund
from bookings.models import BookingRequest
from .services import (
    PaymentGatewayError,
    build_upi_payload,
    complete_demo_payment,
    complete_razorpay_checkout,
    handle_razorpay_webhook_event,
    payment_amount_subunits,
    payment_gateway_context,
    prepare_checkout_payment,
    verify_webhook_signature,
)


UPI_ID_PATTERN = re.compile(r'^[a-zA-Z0-9._-]{2,}@[a-zA-Z]{2,}$')


@login_required
def payment_list(request):
    """Display all payments for the user"""
    payments = Payment.objects.filter(user=request.user).order_by('-created_at')
    
    # Filter by status
    status = request.GET.get('status', '')
    if status:
        payments = payments.filter(status=status)

    completed_payments = Payment.objects.filter(user=request.user, status='Completed')
    total_payments = completed_payments.aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'payments': payments,
        'status': status,
        'total_payments': total_payments,
        'completed_count': completed_payments.count(),
        'processing_count': Payment.objects.filter(user=request.user, status='Processing').count(),
    }
    return render(request, 'payments/payment_list.html', context)


@login_required
def create_payment(request, booking_id):
    """Create a payment for a booking"""
    booking = get_object_or_404(BookingRequest, id=booking_id, user=request.user)
    
    if booking.status == 'Cancelled':
        messages.error(request, 'Cancelled bookings cannot be paid')
        return redirect('bookings:booking_detail', booking_id=booking_id)

    if booking.status != 'Confirmed':
        messages.warning(request, 'Payment is available only after the studio approves your booking.')
        return redirect('bookings:booking_detail', booking_id=booking_id)

    existing_payment = getattr(booking, 'payment', None)
    if existing_payment and existing_payment.status == 'Completed':
        messages.warning(request, 'Payment already exists for this booking')
        return redirect('payments:payment_detail', payment_id=existing_payment.id)

    try:
        payment = prepare_checkout_payment(booking)
    except PaymentGatewayError as exc:
        messages.error(request, str(exc))
        return redirect('bookings:booking_detail', booking_id=booking_id)
    
    if request.method == 'POST':
        payment_method = request.POST.get('payment_method')
        payer_upi_id = request.POST.get('payer_upi_id', '').strip().lower()
        upi_reference = request.POST.get('upi_reference', '').strip().upper()

        valid_methods = {code for code, _ in Payment.PAYMENT_METHOD_CHOICES}
        
        if not payment_method or payment_method not in valid_methods:
            messages.error(request, 'Please select a payment method')
            return redirect('payments:create_payment', booking_id=booking_id)

        if payment_gateway_context()['enabled']:
            messages.info(request, 'Please complete payment using the gateway checkout button.')
            return redirect('payments:create_payment', booking_id=booking_id)

        if payment_method == 'UPI':
            if payer_upi_id and not UPI_ID_PATTERN.match(payer_upi_id):
                messages.error(request, 'Please enter a valid UPI ID (example: name@bank)')
                return redirect('payments:create_payment', booking_id=booking_id)

            if not upi_reference or len(upi_reference) < 8:
                messages.error(request, 'Please enter a valid UPI reference/UTR (minimum 8 characters)')
                return redirect('payments:create_payment', booking_id=booking_id)
        
        try:
            payment.payment_method = payment_method
            payment.status = 'Processing'
            payment.save(update_fields=['payment_method', 'status', 'payment_status', 'updated_at'])
            complete_demo_payment(payment, upi_reference=upi_reference, payer_upi_id=payer_upi_id)
            messages.success(request, 'Payment successful!')
            return redirect('payments:payment_detail', payment_id=payment.id)
        except PaymentGatewayError as exc:
            messages.error(request, str(exc))
            return redirect('bookings:booking_detail', booking_id=booking_id)

    upi_payload = build_upi_payload(booking.amount, booking.id)
    context = {
        'booking': booking,
        'payment': payment,
        'payment_amount_subunits': payment_amount_subunits(payment.amount),
        'gateway': payment_gateway_context(),
        'upi_payload': upi_payload,
        'payment_methods': Payment.PAYMENT_METHOD_CHOICES,
    }
    return render(request, 'payments/create_payment.html', context)


@login_required
@require_POST
def razorpay_checkout_complete(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)
    razorpay_order_id = request.POST.get('razorpay_order_id', '')
    razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
    razorpay_signature = request.POST.get('razorpay_signature', '')

    try:
        complete_razorpay_checkout(payment, razorpay_order_id, razorpay_payment_id, razorpay_signature)
    except PaymentGatewayError as exc:
        messages.error(request, str(exc))
        return redirect('payments:create_payment', booking_id=payment.booking_id)

    messages.success(request, 'Payment verified successfully!')
    return redirect('payments:payment_detail', payment_id=payment.id)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    signature = request.headers.get('X-Razorpay-Signature', '')
    if not verify_webhook_signature(request.body, signature):
        return HttpResponseBadRequest('Invalid webhook signature')

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return HttpResponseBadRequest('Invalid webhook payload')

    handle_razorpay_webhook_event(payload)
    return JsonResponse({'ok': True})


@login_required
def payment_detail(request, payment_id):
    """Display detailed information about a payment"""
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)

    refunds = payment.refunds.all()
    context = {
        'payment': payment,
        'refunds': refunds,
        'can_request_refund': payment.status == 'Completed',
    }
    return render(request, 'payments/payment_detail.html', context)


@login_required
def request_refund(request, payment_id):
    """Request a refund for a payment"""
    payment = get_object_or_404(Payment, id=payment_id, user=request.user)
    
    # Check if refund already exists
    if payment.status == 'Refunded':
        messages.warning(request, 'This payment has already been refunded')
        return redirect('payments:payment_detail', payment_id=payment_id)

    if payment.status != 'Completed':
        messages.error(request, 'Refund can only be requested for completed payments')
        return redirect('payments:payment_detail', payment_id=payment_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason')
        amount_raw = request.POST.get('amount', payment.amount)
        
        if not reason:
            messages.error(request, 'Please provide a reason for refund')
            return redirect('payments:request_refund', payment_id=payment_id)

        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0 or amount > payment.amount:
                messages.error(request, 'Refund amount must be greater than 0 and not exceed paid amount')
                return redirect('payments:request_refund', payment_id=payment_id)
        except (InvalidOperation, TypeError):
            messages.error(request, 'Please enter a valid refund amount')
            return redirect('payments:request_refund', payment_id=payment_id)

        existing = PaymentRefund.objects.filter(payment=payment, status__in=['Requested', 'Approved']).exists()
        if existing:
            messages.warning(request, 'A refund request is already in progress for this payment')
            return redirect('payments:payment_detail', payment_id=payment_id)
        
        try:
            refund = PaymentRefund.objects.create(
                payment=payment,
                user=request.user,
                reason=reason,
                amount=amount,
                status='Requested'
            )
            messages.success(request, 'Refund request submitted!')
            return redirect('payments:payment_detail', payment_id=payment_id)
        except Exception as e:
            messages.error(request, f'Error submitting refund: {str(e)}')
            return redirect('payments:payment_detail', payment_id=payment_id)
    
    context = {'payment': payment}
    return render(request, 'payments/request_refund.html', context)
