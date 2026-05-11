from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from bookings.models import BookingRequest
from notifications.models import Notification
from studios.models import Review, Studio
from studios.models import Service


class UserReviewFlowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			username='reviewer',
			password='Pass123!@#',
			role='USER',
			email='reviewer@example.com',
		)
		self.other_user = user_model.objects.create_user(
			username='otheruser',
			password='Pass123!@#',
			role='USER',
			email='other@example.com',
		)
		self.studio_owner = user_model.objects.create_user(
			username='studioowner',
			password='Pass123!@#',
			role='STUDIO',
			email='studio@example.com',
		)
		self.studio = Studio.objects.create(
			user=self.studio_owner,
			studio_name='Lens House',
			location='Nagpur',
			description='Test studio',
			price_per_hour=1000,
			is_verified=True,
		)

	def _create_booking(self, status='Confirmed'):
		return BookingRequest.objects.create(
			studio=self.studio,
			user=self.user,
			event_type='Wedding',
			date=date.today(),
			booking_date=date.today(),
			amount=2500,
			total_price=2500,
			status=status,
			payment_status='Paid',
		)

	def test_cannot_review_without_confirmed_booking(self):
		self.client.login(username='reviewer', password='Pass123!@#')
		response = self.client.post(
			reverse('dashboard_add_review', args=[self.studio.id]),
			{'rating': '5', 'comment': 'Great studio'},
		)
		self.assertRedirects(response, reverse('studios:studio_detail', args=[self.studio.id]))
		self.assertEqual(Review.objects.filter(studio=self.studio, user=self.user).count(), 0)

	def test_can_create_review_with_confirmed_booking(self):
		self._create_booking(status='Confirmed')
		self.client.login(username='reviewer', password='Pass123!@#')

		response = self.client.post(
			reverse('dashboard_add_review', args=[self.studio.id]),
			{'rating': '4', 'comment': 'Nice experience'},
		)

		self.assertRedirects(response, reverse('studios:studio_detail', args=[self.studio.id]))
		review = Review.objects.get(studio=self.studio, user=self.user)
		self.assertEqual(review.rating, 4)
		self.assertEqual(review.comment, 'Nice experience')

	def test_second_post_updates_existing_review(self):
		self._create_booking(status='Completed')
		Review.objects.create(studio=self.studio, user=self.user, rating=3, comment='Old')
		self.client.login(username='reviewer', password='Pass123!@#')

		response = self.client.post(
			reverse('dashboard_add_review', args=[self.studio.id]),
			{'rating': '5', 'comment': 'Updated review text'},
		)

		self.assertRedirects(response, reverse('studios:studio_detail', args=[self.studio.id]))
		self.assertEqual(Review.objects.filter(studio=self.studio, user=self.user).count(), 1)
		review = Review.objects.get(studio=self.studio, user=self.user)
		self.assertEqual(review.rating, 5)
		self.assertEqual(review.comment, 'Updated review text')

	def test_user_can_edit_and_delete_own_review(self):
		review = Review.objects.create(studio=self.studio, user=self.user, rating=2, comment='Initial')
		self.client.login(username='reviewer', password='Pass123!@#')

		edit_response = self.client.post(
			reverse('edit_review', args=[review.id]),
			{'rating': '4', 'comment': 'Edited text'},
		)
		self.assertRedirects(edit_response, reverse('user_reviews'))

		review.refresh_from_db()
		self.assertEqual(review.rating, 4)
		self.assertEqual(review.comment, 'Edited text')

		delete_response = self.client.post(reverse('delete_review', args=[review.id]))
		self.assertRedirects(delete_response, reverse('user_reviews'))
		self.assertFalse(Review.objects.filter(id=review.id).exists())

	def test_user_cannot_edit_other_users_review(self):
		foreign_review = Review.objects.create(studio=self.studio, user=self.other_user, rating=4, comment='Other review')
		self.client.login(username='reviewer', password='Pass123!@#')

		response = self.client.get(reverse('edit_review', args=[foreign_review.id]))
		self.assertEqual(response.status_code, 404)

	def test_studio_detail_shows_locked_review_button_without_eligible_booking(self):
		self.client.login(username='reviewer', password='Pass123!@#')
		response = self.client.get(reverse('studios:studio_detail', args=[self.studio.id]))

		self.assertContains(response, 'Write Review (Locked)')
		self.assertContains(response, 'Need confirmed or paid booking')

	def test_studio_detail_shows_review_modal_trigger_with_eligible_booking(self):
		self._create_booking(status='Confirmed')
		self.client.login(username='reviewer', password='Pass123!@#')
		response = self.client.get(reverse('studios:studio_detail', args=[self.studio.id]))

		self.assertContains(response, 'data-bs-target="#reviewModal"')
		self.assertContains(response, 'id="reviewModal"')

	def test_invalid_review_submission_reopens_modal_on_studio_detail(self):
		self._create_booking(status='Confirmed')
		self.client.login(username='reviewer', password='Pass123!@#')

		response = self.client.post(
			reverse('studios:add_review', args=[self.studio.id]),
			{'rating': '5', 'comment': ''},
		)

		self.assertRedirects(response, f"{reverse('studios:studio_detail', args=[self.studio.id])}?open_review=1")

		followed = self.client.get(f"{reverse('studios:studio_detail', args=[self.studio.id])}?open_review=1")
		self.assertContains(followed, 'id="reviewModal"')
		self.assertContains(followed, 'reviewModal.show();')


class UserDashboardPriceRenderingTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.user = user_model.objects.create_user(
			username='dashuser',
			password='Pass123!@#',
			role='USER',
			email='dashuser@example.com',
		)

		self.owner_one = user_model.objects.create_user(
			username='ownerone',
			password='Pass123!@#',
			role='STUDIO',
			email='ownerone@example.com',
		)
		self.owner_two = user_model.objects.create_user(
			username='ownertwo',
			password='Pass123!@#',
			role='STUDIO',
			email='ownertwo@example.com',
		)

		self.hourly_studio = Studio.objects.create(
			user=self.owner_one,
			studio_name='Hourly Studio',
			location='Nagpur',
			price_per_hour=6000,
			is_verified=True,
		)
		self.service_fallback_studio = Studio.objects.create(
			user=self.owner_two,
			studio_name='Service Fallback Studio',
			location='Amravati',
			price_per_hour=0,
			is_verified=True,
		)
		Service.objects.create(
			studio=self.service_fallback_studio,
			service_name='Portrait Package',
			price=2000,
		)

	def test_dashboard_shows_hourly_price_when_available(self):
		self.client.login(username='dashuser', password='Pass123!@#')

		response = self.client.get(reverse('user_dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '6000/hr')

	def test_dashboard_shows_service_fallback_price_when_hourly_missing(self):
		self.client.login(username='dashuser', password='Pass123!@#')

		response = self.client.get(reverse('user_dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'From ₹ 2000')


class StudioBookingCompletionFlowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.studio_owner = user_model.objects.create_user(
			username='studio_complete_owner',
			password='Pass123!@#',
			role='STUDIO',
			email='studio_complete@example.com',
		)
		self.user = user_model.objects.create_user(
			username='studio_complete_user',
			password='Pass123!@#',
			role='USER',
			email='studio_complete_user@example.com',
		)

		self.studio = Studio.objects.create(
			user=self.studio_owner,
			studio_name='Completion Studio',
			location='Nagpur',
			price_per_hour=1500,
			is_verified=True,
		)

		self.booking = BookingRequest.objects.create(
			studio=self.studio,
			user=self.user,
			event_type='Portrait Session',
			date=date.today(),
			booking_date=date.today(),
			amount=3000,
			total_price=3000,
			status='Confirmed',
			payment_status='Paid',
		)

	def test_studio_can_mark_confirmed_booking_completed(self):
		self.client.login(username='studio_complete_owner', password='Pass123!@#')
		response = self.client.post(reverse('studio_complete_booking', args=[self.booking.id]))

		self.assertRedirects(response, reverse('studio_bookings'))
		self.booking.refresh_from_db()
		self.assertEqual(self.booking.status, 'Completed')
		self.assertTrue(Notification.objects.filter(user=self.user, type='booking_completed').exists())

	def test_studio_can_notify_booking_user(self):
		self.client.login(username='studio_complete_owner', password='Pass123!@#')
		response = self.client.post(
			reverse('studio_notify_booking_user', args=[self.booking.id]),
			{'message': 'Please arrive 10 minutes early.'},
		)

		self.assertRedirects(response, reverse('studio_bookings'))
		notification = Notification.objects.get(user=self.user, type='studio_message')
		self.assertIn('Please arrive 10 minutes early.', notification.message)

	def test_completed_status_reflects_on_user_bookings_page(self):
		self.client.login(username='studio_complete_owner', password='Pass123!@#')
		self.client.post(reverse('studio_complete_booking', args=[self.booking.id]))

		self.client.login(username='studio_complete_user', password='Pass123!@#')
		response = self.client.get(reverse('user_bookings'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Completed')
