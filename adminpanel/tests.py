from django.test import TestCase
from django.urls import reverse
from decimal import Decimal

from accounts.models import CustomUser
from bookings.models import BookingRequest
from chatbot.models import ChatMessage
from notifications.models import Notification
from payments.models import Payment
from studios.models import Studio


class AdminChatbotAnalyticsTests(TestCase):
	def setUp(self):
		self.password = 'TestPass123!'
		self.admin = CustomUser.objects.create_user(username='admin_analytics', password=self.password, role='ADMIN')
		self.user = CustomUser.objects.create_user(username='regular_user', password=self.password, role='USER')

	def test_dashboard_includes_chatbot_policy_metrics(self):
		ChatMessage.objects.create(
			user=self.user,
			is_user=False,
			message='Blocked response 1',
			role_at_message_time='USER',
			policy_blocked=True,
			blocked_reason='admin_ops is not allowed for role USER.',
			response_mode='guardrail',
		)
		ChatMessage.objects.create(
			user=self.user,
			is_user=False,
			message='FAQ response',
			role_at_message_time='USER',
			policy_blocked=False,
			response_mode='faq_hit',
		)
		ChatMessage.objects.create(
			user=self.user,
			is_user=False,
			message='Fallback response',
			role_at_message_time='USER',
			policy_blocked=False,
			response_mode='fallback',
		)

		self.client.force_login(self.admin)
		response = self.client.get(reverse('admin_dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['blocked_by_role']['USER'], 1)
		self.assertEqual(response.context['total_blocked_intents'], 1)
		self.assertEqual(response.context['faq_hits'], 1)
		self.assertEqual(response.context['fallback_count'], 1)
		self.assertEqual(response.context['faq_hit_rate'], 50.0)
		self.assertEqual(response.context['fallback_rate'], 50.0)
		self.assertEqual(len(response.context['policy_trend_labels']), 7)
		self.assertEqual(len(response.context['blocked_trend_data']), 7)
		self.assertEqual(len(response.context['faq_hit_rate_trend_data']), 7)

	def test_weekly_policy_report_export_returns_csv(self):
		ChatMessage.objects.create(
			user=self.user,
			is_user=False,
			message='Blocked response export',
			role_at_message_time='USER',
			policy_blocked=True,
			blocked_reason='studio_ops is not allowed for role USER.',
			response_mode='guardrail',
		)

		self.client.force_login(self.admin)
		response = self.client.get(reverse('admin_weekly_policy_report'))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response['Content-Type'], 'text/csv')
		self.assertIn('attachment; filename=', response['Content-Disposition'])

		csv_text = response.content.decode('utf-8')
		self.assertIn('StudioSync Weekly Moderation Policy Report', csv_text)
		self.assertIn('Weekly Blocked Intents', csv_text)
		self.assertIn('Blocked Message Details', csv_text)
		self.assertIn('Blocked response export', csv_text)

	def test_admin_can_notify_user(self):
		self.client.force_login(self.admin)
		response = self.client.post(
			reverse('notify_user', args=[self.user.id]),
			{'message': 'Your booking policy has been updated.'},
		)

		self.assertRedirects(response, reverse('manage_users'))
		notification = Notification.objects.get(user=self.user, type='admin_notice')
		self.assertIn('Your booking policy has been updated.', notification.message)

	def test_admin_marks_studio_payout_paid_and_notifies_owner(self):
		studio_owner = CustomUser.objects.create_user(username='studio_owner', password=self.password, role='STUDIO')
		studio = Studio.objects.create(
			user=studio_owner,
			studio_name='Payout Studio',
			location='Nagpur',
			price_per_hour=Decimal('1500.00'),
		)
		booking = BookingRequest.objects.create(
			studio=studio,
			user=self.user,
			event_type='Portrait',
			date='2026-05-10',
			amount=Decimal('5000.00'),
			status='Confirmed',
			payment_status='Paid',
		)
		payment = Payment.objects.create(
			booking=booking,
			user=self.user,
			amount=Decimal('5000.00'),
			payment_method='UPI',
			status='Completed',
			payout_status='Ready',
			transaction_id='TXN-PAYOUT-1',
		)

		self.client.force_login(self.admin)
		response = self.client.post(
			reverse('mark_studio_payout_paid', args=[payment.id]),
			{'payout_reference': 'BANK-REF-90', 'payout_notes': 'Settled to owner account'},
		)

		self.assertRedirects(response, reverse('admin_payments'))
		payment.refresh_from_db()
		self.assertEqual(payment.payout_status, 'Paid')
		self.assertEqual(payment.payout_reference, 'BANK-REF-90')
		self.assertEqual(payment.studio_payout_amount, Decimal('4500.00'))
		self.assertEqual(payment.commission_amount, Decimal('500.00'))
		self.assertTrue(Notification.objects.filter(user=studio_owner, type='studio_payout_paid').exists())
