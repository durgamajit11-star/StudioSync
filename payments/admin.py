from django.contrib import admin
from .models import Payment, PaymentRefund


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'booking', 'amount', 'status', 'payment_method', 'gateway', 'created_at')
    list_filter = ('status', 'payment_method', 'gateway', 'created_at')
    search_fields = ('user__username', 'booking__id', 'transaction_id', 'gateway_order_id', 'gateway_payment_id')
    readonly_fields = (
        'created_at',
        'updated_at',
        'completed_at',
        'transaction_id',
        'gateway_order_id',
        'gateway_payment_id',
        'gateway_signature',
        'raw_gateway_payload',
    )
    fieldsets = (
        ('Payment Information', {'fields': ('booking', 'user', 'amount', 'transaction_id')}),
        ('Details', {'fields': ('status', 'payment_method', 'gateway')}),
        ('Gateway', {'fields': ('gateway_order_id', 'gateway_payment_id', 'gateway_signature', 'gateway_status', 'failure_reason', 'raw_gateway_payload')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'completed_at'), 'classes': ('collapse',)}),
    )


@admin.register(PaymentRefund)
class PaymentRefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'user', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('payment__id', 'user__username', 'reason')
    readonly_fields = ('created_at', 'processed_at')
    fieldsets = (
        ('Refund Information', {'fields': ('payment', 'user', 'amount')}),
        ('Details', {'fields': ('reason', 'status')}),
        ('Timestamps', {'fields': ('created_at', 'processed_at'), 'classes': ('collapse',)}),
    )
