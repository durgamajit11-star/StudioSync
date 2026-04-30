# Generated manually for payment gateway hardening.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_payment_payment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='failure_reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='gateway',
            field=models.CharField(choices=[('Demo', 'Demo / Manual'), ('Razorpay', 'Razorpay')], default='Demo', max_length=20),
        ),
        migrations.AddField(
            model_name='payment',
            name='gateway_order_id',
            field=models.CharField(blank=True, db_index=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='gateway_payment_id',
            field=models.CharField(blank=True, db_index=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='gateway_signature',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='gateway_status',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='raw_gateway_payload',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
