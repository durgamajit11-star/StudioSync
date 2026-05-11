from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.conf import settings
from bookings.models import BookingRequest


def default_commission_rate():
    return Decimal(str(getattr(settings, 'PLATFORM_COMMISSION_PERCENT', '10.00')))


class Payment(models.Model):
    """Payment model for booking transactions"""
    
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Processing', 'Processing'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
        ('Refunded', 'Refunded'),
    )

    PAYMENT_METHOD_CHOICES = (
        ('Card', 'Credit/Debit Card'),
        ('Bank', 'Bank Transfer'),
        ('Wallet', 'Wallet'),
        ('UPI', 'UPI'),
    )

    GATEWAY_CHOICES = (
        ('Demo', 'Demo / Manual'),
        ('Razorpay', 'Razorpay'),
    )

    PAYOUT_STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Ready', 'Ready for Payout'),
        ('Paid', 'Paid to Studio'),
        ('Hold', 'On Hold'),
        ('Cancelled', 'Cancelled'),
    )

    booking = models.OneToOneField(BookingRequest, on_delete=models.CASCADE, related_name='payment')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=default_commission_rate)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    studio_payout_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transaction_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default='Demo')
    gateway_order_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    gateway_payment_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    gateway_signature = models.CharField(max_length=255, blank=True, null=True)
    gateway_status = models.CharField(max_length=50, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    raw_gateway_payload = models.JSONField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payout_status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default='Pending')
    payout_reference = models.CharField(max_length=120, blank=True, null=True)
    payout_notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    payout_processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment for Booking #{self.booking.id} - {self.amount}"

    def refresh_commission_split(self):
        amount = Decimal(self.amount or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        rate = Decimal(self.commission_rate or 0)
        commission = ((amount * rate) / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.commission_amount = commission
        self.studio_payout_amount = (amount - commission).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.refresh_commission_split()
        if self.status and self.payment_status != self.status:
            self.payment_status = self.status
        elif self.payment_status and self.status != self.payment_status:
            self.status = self.payment_status
        super().save(*args, **kwargs)


class PaymentRefund(models.Model):
    """Refund model for payments"""
    
    STATUS_CHOICES = (
        ('Requested', 'Requested'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Processed', 'Processed'),
    )

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    reason = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Requested')
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund for Payment #{self.payment.id} - {self.amount}"
