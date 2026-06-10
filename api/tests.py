from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from bookings.models import BookingRequest, BookingNote
from studios.models import Studio


class ApiAuthorizationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.client_user = User.objects.create_user(username='client', password='pass', role='USER')
        self.other_user = User.objects.create_user(username='other', password='pass', role='USER')
        self.studio_user = User.objects.create_user(username='studio', password='pass', role='STUDIO')
        self.studio = Studio.objects.create(
            user=self.studio_user,
            studio_name='Secure Studio',
            location='Nagpur',
            price_per_hour=Decimal('1000.00'),
            is_verified=True,
        )
        self.booking = BookingRequest.objects.create(
            studio=self.studio,
            user=self.client_user,
            event_type='Portrait',
            date=date.today(),
            amount=Decimal('2000.00'),
        )

    def test_anonymous_user_cannot_create_or_delete_studio(self):
        create_response = self.client.post('/api/studios/', {'studio_name': 'Injected'})
        delete_response = self.client.delete(f'/api/studios/{self.studio.id}/')

        self.assertEqual(create_response.status_code, 405)
        self.assertEqual(delete_response.status_code, 405)
        self.assertTrue(Studio.objects.filter(pk=self.studio.pk).exists())

    def test_user_cannot_mutate_booking_through_api(self):
        self.client.force_authenticate(self.client_user)

        response = self.client.patch(
            f'/api/bookings/{self.booking.id}/',
            {'amount': '1.00', 'payment_status': 'Paid', 'status': 'Confirmed'},
        )

        self.assertEqual(response.status_code, 405)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.amount, Decimal('2000.00'))
        self.assertEqual(self.booking.payment_status, 'Unpaid')

    def test_user_cannot_add_note_to_someone_elses_booking(self):
        self.client.force_authenticate(self.other_user)

        response = self.client.post(
            '/api/booking-notes/',
            {'booking': self.booking.id, 'message': 'Unauthorized note'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(BookingNote.objects.filter(message='Unauthorized note').exists())
