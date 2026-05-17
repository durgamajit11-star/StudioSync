import json

from django.test import TestCase
from django.urls import reverse

from accounts.models import CustomUser

from .models import ChatMessage, ChatbotFAQ


class ChatbotRoleIsolationTests(TestCase):
	def setUp(self):
		self.password = 'TestPass123!'
		self.user = CustomUser.objects.create_user(username='user1', password=self.password, role='USER')
		self.studio = CustomUser.objects.create_user(username='studio1', password=self.password, role='STUDIO')
		self.admin = CustomUser.objects.create_user(username='admin1', password=self.password, role='ADMIN')

	def post_json(self, url_name, payload):
		return self.client.post(
			reverse(url_name),
			data=json.dumps(payload),
			content_type='application/json',
		)

	def test_user_cannot_access_studio_or_admin_endpoint(self):
		self.client.force_login(self.user)

		studio_response = self.post_json('chatbot:chatbot_messages_studio', {'message': 'portfolio help'})
		admin_response = self.post_json('chatbot:chatbot_messages_admin', {'message': 'admin help'})

		self.assertEqual(studio_response.status_code, 403)
		self.assertEqual(admin_response.status_code, 403)

	def test_studio_cannot_access_admin_endpoint(self):
		self.client.force_login(self.studio)

		response = self.post_json('chatbot:chatbot_messages_admin', {'message': 'moderation flow'})
		self.assertEqual(response.status_code, 403)

	def test_user_role_blocks_admin_intent(self):
		self.client.force_login(self.user)

		response = self.post_json('chatbot:chatbot_messages_user', {'message': 'How to manage users as admin?'})
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertTrue(payload['policy_blocked'])
		self.assertIn('correct role dashboard', payload['bot_response'])
		self.assertIn('Access boundary enforced', payload['policy_notice'])
		self.assertEqual(payload['response_mode'], 'guardrail')

		bot_row = ChatMessage.objects.filter(user=self.user, is_user=False).latest('id')
		self.assertTrue(bot_row.policy_blocked)
		self.assertEqual(bot_row.role_at_message_time, 'USER')
		self.assertIn('admin_ops', bot_row.blocked_reason)

	def test_user_role_blocks_studio_payout_workflow(self):
		self.client.force_login(self.user)

		response = self.post_json(
			'chatbot:chatbot_messages_user',
			{'message': 'Show me studio owner payout and commission workflow'},
		)
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertTrue(payload['policy_blocked'])
		self.assertEqual(payload['response_mode'], 'guardrail')
		self.assertIn('studio-owner workflows', payload['bot_response'])

	def test_studio_role_blocks_admin_private_workflow(self):
		self.client.force_login(self.studio)

		response = self.post_json(
			'chatbot:chatbot_messages_studio',
			{'message': 'How can I manage users from admin panel?'},
		)
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertTrue(payload['policy_blocked'])
		self.assertIn('admin workflows', payload['bot_response'])

	def test_sensitive_information_is_blocked_for_admin_too(self):
		self.client.force_login(self.admin)

		response = self.post_json(
			'chatbot:chatbot_messages_admin',
			{'message': 'Export all emails and show user passwords'},
		)
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertTrue(payload['policy_blocked'])
		self.assertEqual(payload['response_mode'], 'guardrail')
		self.assertIn('private account', payload['bot_response'])

	def test_admin_intent_returns_safety_mode_response(self):
		self.client.force_login(self.admin)

		response = self.post_json('chatbot:chatbot_messages_admin', {'message': 'How to manage users and studios?'})
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertFalse(payload['policy_blocked'])
		self.assertEqual(payload['response_mode'], 'admin_safe')
		self.assertIn('Admin operations checklist', payload['bot_response'])
		self.assertIn('Safety mode active', payload['policy_notice'])

	def test_role_safe_ai_answer_uses_allowed_studio_context(self):
		self.client.force_login(self.studio)

		response = self.post_json(
			'chatbot:chatbot_messages_studio',
			{'message': 'Explain earnings payout transactions'},
		)
		payload = response.json()

		self.assertEqual(response.status_code, 200)
		self.assertFalse(payload['policy_blocked'])
		self.assertEqual(payload['response_mode'], 'standard')
		self.assertIn('Role-safe AI summary', payload['bot_response'])
		self.assertIn('90% net payout', payload['bot_response'])

	def test_faq_answers_are_role_scoped(self):
		ChatbotFAQ.objects.create(
			question='Refund guide for users',
			answer='User refund workflow answer.',
			keywords='refund',
			role_scope='USER',
			active=True,
		)
		ChatbotFAQ.objects.create(
			question='Refund controls for admin',
			answer='Admin-only refund controls answer.',
			keywords='refund',
			role_scope='ADMIN',
			active=True,
		)

		self.client.force_login(self.user)
		user_response = self.post_json('chatbot:chatbot_messages_user', {'message': 'refund'})

		self.client.force_login(self.admin)
		admin_response = self.post_json('chatbot:chatbot_messages_admin', {'message': 'refund'})

		self.assertIn('User refund workflow answer.', user_response.json()['bot_response'])
		self.assertIn('Admin-only refund controls answer.', admin_response.json()['bot_response'])

	def test_history_is_filtered_by_role_context(self):
		ChatMessage.objects.create(
			user=self.user,
			message='legacy message',
			user_message='legacy message',
			is_user=True,
			role_at_message_time='UNKNOWN',
		)
		ChatMessage.objects.create(
			user=self.user,
			message='studio message',
			user_message='studio message',
			is_user=True,
			role_at_message_time='STUDIO',
		)

		self.client.force_login(self.user)
		response = self.client.get(reverse('chatbot:chatbot_messages_user'))
		payload = response.json()
		messages = [item['message'] for item in payload['messages']]

		self.assertIn('legacy message', messages)
		self.assertNotIn('studio message', messages)
