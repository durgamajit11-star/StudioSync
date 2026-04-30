import hashlib
import hmac
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from bookings.models import BookingRequest
from studios.models import Studio

from .models import Payment
from .services import (
    complete_demo_payment,
    complete_razorpay_checkout,
    prepare_checkout_payment,
    verify_webhook_signature,
)


class PaymentServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='client', password='pass', role='USER')
        self.studio_user = User.objects.create_user(username='studio', password='pass', role='STUDIO')
        self.studio = Studio.objects.create(
            user=self.studio_user,
            studio_name='Pixel Loft',
            location='Nagpur',
            price_per_hour=Decimal('1500.00'),
        )
        self.booking = BookingRequest.objects.create(
            studio=self.studio,
            user=self.user,
            event_type='Portrait',
            date='2026-05-10',
            amount=Decimal('3000.00'),
            status='Confirmed',
            payment_status='Unpaid',
        )

    @override_settings(PAYMENT_GATEWAY_ENABLED=False, PAYMENT_GATEWAY_MODE='demo')
    def test_prepare_checkout_payment_reuses_existing_pending_payment(self):
        first = prepare_checkout_payment(self.booking)
        second = prepare_checkout_payment(self.booking)

        self.assertEqual(first.id, second.id)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(first.status, 'Pending')

    @override_settings(PAYMENT_GATEWAY_ENABLED=False, PAYMENT_GATEWAY_MODE='demo')
    def test_demo_completion_marks_payment_and_booking_paid(self):
        payment = prepare_checkout_payment(self.booking)

        complete_demo_payment(payment, upi_reference='UTR12345678', payer_upi_id='client@upi')

        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(payment.status, 'Completed')
        self.assertEqual(payment.transaction_id, f'UPI-UTR12345678-{payment.id:04d}')
        self.assertEqual(self.booking.payment_status, 'Paid')

    @override_settings(RAZORPAY_KEY_SECRET='secret')
    def test_razorpay_checkout_completion_requires_valid_signature(self):
        payment = Payment.objects.create(
            booking=self.booking,
            user=self.user,
            amount=self.booking.amount,
            payment_method='UPI',
            gateway='Razorpay',
            gateway_order_id='order_123',
        )
        signature = hmac.new(
            b'secret',
            b'order_123|pay_123',
            hashlib.sha256,
        ).hexdigest()

        complete_razorpay_checkout(payment, 'order_123', 'pay_123', signature)

        payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(payment.status, 'Completed')
        self.assertEqual(payment.gateway_payment_id, 'pay_123')
        self.assertEqual(self.booking.payment_status, 'Paid')

    @override_settings(RAZORPAY_WEBHOOK_SECRET='webhook-secret')
    def test_webhook_signature_uses_raw_body(self):
        body = b'{"event":"payment.captured"}'
        signature = hmac.new(b'webhook-secret', body, hashlib.sha256).hexdigest()

        self.assertTrue(verify_webhook_signature(body, signature))
        self.assertFalse(verify_webhook_signature(body, 'bad-signature'))
