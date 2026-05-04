from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthViewTests(TestCase):
	def setUp(self):
		self.user_model = get_user_model()

	def test_user_can_log_in_and_redirects_to_dashboard(self):
		self.user_model.objects.create_user(
			username='demo',
			password='Pass123!@#',
			role='USER',
			email='demo@example.com',
		)

		response = self.client.post(
			reverse('auth_page'),
			{
				'login_submit': '1',
				'username': 'demo',
				'password': 'Pass123!@#',
			},
		)

		self.assertRedirects(response, reverse('user_dashboard'))

	def test_invalid_role_is_rejected_with_message(self):
		user = self.user_model.objects.create_user(
			username='broken',
			password='Pass123!@#',
			role='USER',
			email='broken@example.com',
		)
		self.user_model.objects.filter(pk=user.pk).update(role='GUEST')

		response = self.client.post(
			reverse('auth_page'),
			{
				'login_submit': '1',
				'username': 'broken',
				'password': 'Pass123!@#',
			},
			follow=True,
		)

		self.assertContains(response, 'Your account role is not configured correctly.')
