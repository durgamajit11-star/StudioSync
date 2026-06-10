from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bookings.models import BookingRequest
from studios.models import Studio


class BookingRedirectRegressionTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			username='booking_user',
			password='Pass123!@#',
			role='USER',
			email='booking_user@example.com',
		)
		self.studio_owner = user_model.objects.create_user(
			username='booking_studio_owner',
			password='Pass123!@#',
			role='STUDIO',
			email='booking_studio_owner@example.com',
		)
		self.studio = Studio.objects.create(
			user=self.studio_owner,
			studio_name='Redirect Studio',
			location='Nagpur',
			price_per_hour=1200,
		)

	def _create_booking(self, status='Pending'):
		return BookingRequest.objects.create(
			studio=self.studio,
			user=self.user,
			event_type='Portrait',
			date=date.today(),
			booking_date=date.today(),
			amount=2500,
			total_price=2500,
			status=status,
			payment_status='Unpaid',
		)

	def test_cancel_pending_booking_redirects_to_namespaced_detail(self):
		booking = self._create_booking(status='Pending')
		self.client.login(username='booking_user', password='Pass123!@#')

		response = self.client.post(reverse('bookings:cancel_booking', kwargs={'booking_id': booking.id}))

		self.assertRedirects(
			response,
			reverse('bookings:booking_detail', kwargs={'booking_id': booking.id}),
		)

	def test_cancel_non_pending_booking_redirects_to_namespaced_detail(self):
		booking = self._create_booking(status='Confirmed')
		self.client.login(username='booking_user', password='Pass123!@#')

		response = self.client.post(reverse('bookings:cancel_booking', kwargs={'booking_id': booking.id}))

		self.assertRedirects(
			response,
			reverse('bookings:booking_detail', kwargs={'booking_id': booking.id}),
		)
