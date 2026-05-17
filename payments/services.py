import hashlib
import hmac
from decimal import Decimal
from urllib.parse import quote

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Payment
from notifications.services import create_notification


UPI_PAYEE_ID = 'studiosync@upi'
UPI_PAYEE_NAME = 'StudioSync'
RAZORPAY_API_BASE = 'https://api.razorpay.com/v1'


class PaymentGatewayError(Exception):
    """Raised when a gateway action cannot be completed."""


def payment_gateway_context():
    return {
        'mode': settings.PAYMENT_GATEWAY_MODE,
        'enabled': settings.PAYMENT_GATEWAY_ENABLED,
        'provider': 'Razorpay' if settings.PAYMENT_GATEWAY_ENABLED else 'Demo',
        'razorpay_key_id': settings.RAZORPAY_KEY_ID if settings.PAYMENT_GATEWAY_ENABLED else '',
    }


def build_upi_payload(amount, booking_id, size=360):
    amount_str = f"{Decimal(amount):.2f}"
    note = f"Studio booking #{booking_id}"
    upi_intent = (
        f"upi://pay?pa={quote(UPI_PAYEE_ID)}"
        f"&pn={quote(UPI_PAYEE_NAME)}"
        f"&am={amount_str}"
        f"&cu=INR"
        f"&tn={quote(note)}"
    )
    qr_url = f"https://chart.googleapis.com/chart?cht=qr&chs={size}x{size}&chl={quote(upi_intent, safe='')}"
    return {
        'upi_id': UPI_PAYEE_ID,
        'upi_name': UPI_PAYEE_NAME,
        'upi_intent': upi_intent,
        'upi_qr_url': qr_url,
    }


def payment_amount_subunits(amount):
    return int((Decimal(amount).quantize(Decimal('0.01')) * 100).to_integral_value())


def get_or_create_pending_payment(booking, payment_method='UPI'):
    try:
        with transaction.atomic():
            locked_booking = booking.__class__.objects.select_for_update().get(pk=booking.pk)
            payment, created = Payment.objects.get_or_create(
                booking=locked_booking,
                defaults={
                    'user': locked_booking.user,
                    'amount': locked_booking.amount,
                    'commission_rate': settings.PLATFORM_COMMISSION_PERCENT,
                    'payment_method': payment_method,
                    'status': 'Pending',
                    'gateway': 'Razorpay' if settings.PAYMENT_GATEWAY_ENABLED else 'Demo',
                },
            )
            return payment, created
    except IntegrityError as exc:
        raise PaymentGatewayError('A payment already exists for this booking.') from exc


def create_razorpay_order(payment):
    if not settings.PAYMENT_GATEWAY_ENABLED:
        return payment

    if payment.gateway_order_id:
        return payment

    payload = {
        'amount': payment_amount_subunits(payment.amount),
        'currency': 'INR',
        'receipt': f"booking-{payment.booking_id}-payment-{payment.id}",
        'notes': {
            'booking_id': str(payment.booking_id),
            'payment_id': str(payment.id),
            'user_id': str(payment.user_id),
        },
    }
    try:
        response = requests.post(
            f"{RAZORPAY_API_BASE}/orders",
            json=payload,
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PaymentGatewayError('Could not create Razorpay order. Please try again.') from exc

    data = response.json()
    payment.gateway = 'Razorpay'
    payment.gateway_order_id = data.get('id')
    payment.gateway_status = data.get('status')
    payment.raw_gateway_payload = data
    payment.status = 'Pending'
    payment.save(update_fields=[
        'gateway',
        'gateway_order_id',
        'gateway_status',
        'raw_gateway_payload',
        'status',
        'payment_status',
        'updated_at',
    ])
    return payment


def prepare_checkout_payment(booking, payment_method='UPI'):
    payment, _ = get_or_create_pending_payment(booking, payment_method)
    if settings.PAYMENT_GATEWAY_ENABLED:
        payment = create_razorpay_order(payment)
    return payment


def complete_demo_payment(payment, upi_reference='', payer_upi_id=''):
    transaction_id = f"UPI-{upi_reference}-{payment.id:04d}" if upi_reference else f"TXN{payment.id:06d}"
    raw_payload = {
        'upi_reference': upi_reference,
        'payer_upi_id': payer_upi_id,
        'source': 'demo_manual_checkout',
    }
    return mark_payment_completed(payment, transaction_id=transaction_id, raw_payload=raw_payload)


def verify_razorpay_signature(order_id, payment_id, signature):
    message = f"{order_id}|{payment_id}".encode('utf-8')
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def verify_webhook_signature(raw_body, signature):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def complete_razorpay_checkout(payment, razorpay_order_id, razorpay_payment_id, razorpay_signature):
    if payment.gateway_order_id and payment.gateway_order_id != razorpay_order_id:
        payment.status = 'Failed'
        payment.failure_reason = 'Razorpay order mismatch.'
        payment.save(update_fields=['status', 'payment_status', 'failure_reason', 'updated_at'])
        raise PaymentGatewayError('Payment order mismatch. Please contact support if money was debited.')

    if not verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        payment.status = 'Failed'
        payment.failure_reason = 'Razorpay checkout signature verification failed.'
        payment.save(update_fields=['status', 'payment_status', 'failure_reason', 'updated_at'])
        raise PaymentGatewayError('Payment verification failed. Please contact support if money was debited.')

    return mark_payment_completed(
        payment,
        transaction_id=razorpay_payment_id,
        gateway_payment_id=razorpay_payment_id,
        gateway_order_id=razorpay_order_id,
        gateway_signature=razorpay_signature,
        gateway_status='paid',
        raw_payload={'source': 'razorpay_checkout'},
    )


def mark_payment_completed(
    payment,
    transaction_id,
    gateway_payment_id=None,
    gateway_order_id=None,
    gateway_signature=None,
    gateway_status='completed',
    raw_payload=None,
):
    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().select_related('booking').get(pk=payment.pk)
        locked_booking = locked_payment.booking

        locked_payment.transaction_id = transaction_id
        locked_payment.gateway_payment_id = gateway_payment_id or locked_payment.gateway_payment_id
        locked_payment.gateway_order_id = gateway_order_id or locked_payment.gateway_order_id
        locked_payment.gateway_signature = gateway_signature or locked_payment.gateway_signature
        locked_payment.gateway_status = gateway_status
        locked_payment.raw_gateway_payload = raw_payload or locked_payment.raw_gateway_payload
        locked_payment.failure_reason = ''
        locked_payment.status = 'Completed'
        if locked_payment.payout_status == 'Pending':
            locked_payment.payout_status = 'Ready'
        locked_payment.completed_at = locked_payment.completed_at or timezone.now()
        locked_payment.save()

        locked_booking.payment_status = 'Paid'
        locked_booking.save(update_fields=['payment_status', 'updated_at'])
        create_notification(
            locked_booking.user,
            (
                f"Payment received by StudioSync for booking #{locked_booking.id} "
                f"with {locked_booking.studio.studio_name}. Studio payout is now queued."
            ),
            'payment_completed',
        )
        create_notification(
            locked_booking.studio.user,
            (
                f"StudioSync received Rs. {locked_payment.amount} for booking #{locked_booking.id}. "
                f"Your net payout is Rs. {locked_payment.studio_payout_amount} after "
                f"{locked_payment.commission_rate}% platform commission."
            ),
            'studio_payment_received',
        )
        return locked_payment


def mark_payment_failed(payment, reason, raw_payload=None):
    payment.status = 'Failed'
    payment.gateway_status = 'failed'
    payment.failure_reason = reason
    payment.raw_gateway_payload = raw_payload or payment.raw_gateway_payload
    payment.save(update_fields=[
        'status',
        'payment_status',
        'gateway_status',
        'failure_reason',
        'raw_gateway_payload',
        'updated_at',
    ])
    return payment


def handle_razorpay_webhook_event(payload):
    event = payload.get('event')
    entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
    order_id = entity.get('order_id')
    payment_id = entity.get('id')

    if not order_id:
        return None

    try:
        payment = Payment.objects.get(gateway_order_id=order_id)
    except Payment.DoesNotExist:
        return None

    if event in {'payment.captured', 'order.paid'}:
        return mark_payment_completed(
            payment,
            transaction_id=payment_id or order_id,
            gateway_payment_id=payment_id,
            gateway_order_id=order_id,
            gateway_status=entity.get('status') or 'paid',
            raw_payload=payload,
        )

    if event == 'payment.authorized':
        payment.status = 'Processing'
        payment.gateway_payment_id = payment_id or payment.gateway_payment_id
        payment.gateway_status = entity.get('status') or 'authorized'
        payment.raw_gateway_payload = payload
        payment.save(update_fields=[
            'status',
            'payment_status',
            'gateway_payment_id',
            'gateway_status',
            'raw_gateway_payload',
            'updated_at',
        ])
        return payment

    if event == 'payment.failed':
        error_reason = entity.get('error_description') or entity.get('error_reason') or 'Payment failed at gateway.'
        return mark_payment_failed(payment, error_reason, payload)

    payment.gateway_status = entity.get('status') or event
    payment.raw_gateway_payload = payload
    payment.save(update_fields=['gateway_status', 'raw_gateway_payload', 'updated_at'])
    return payment
