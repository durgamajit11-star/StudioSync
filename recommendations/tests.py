from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from bookings.models import BookingRequest
from recommendations.models import StudioRecommendation
from recommendations.services import get_user_recommendations, refresh_user_recommendations
from studios.models import Category, Review, Service, Studio


class StudioRecommendationServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="maya", password="pass", role="USER", address="Kochi")
        self.owner_one = User.objects.create_user(username="owner-one", password="pass", role="STUDIO")
        self.owner_two = User.objects.create_user(username="owner-two", password="pass", role="STUDIO")
        self.category = Category.objects.create(name="Wedding")

        self.best_match = Studio.objects.create(
            user=self.owner_one,
            studio_name="Kochi Wedding Studio",
            location="Kochi",
            category=self.category,
            specializations="wedding bridal candid photography",
            price_per_hour=Decimal("2000.00"),
            rating=Decimal("4.80"),
            experience_years=8,
            is_verified=True,
            is_featured=True,
        )
        Service.objects.create(studio=self.best_match, service_name="Wedding Shoot", price=Decimal("5000.00"))

        self.other_studio = Studio.objects.create(
            user=self.owner_two,
            studio_name="Product Lab",
            location="Mumbai",
            specializations="product commercial catalog",
            price_per_hour=Decimal("6500.00"),
            rating=Decimal("4.10"),
            experience_years=3,
            is_verified=True,
        )

        BookingRequest.objects.create(
            user=self.user,
            studio=self.best_match,
            service=self.best_match.services.first(),
            event_type="Wedding",
            date="2026-06-01",
            location="Kochi",
            amount=Decimal("5000.00"),
            total_price=Decimal("5000.00"),
            special_requirements="Candid bridal photos",
        )
        Review.objects.create(user=self.user, studio=self.best_match, rating=5, comment="Great wedding work")

    def test_refresh_generates_personalized_recommendations(self):
        recommendations = refresh_user_recommendations(self.user)

        self.assertGreaterEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0].studio, self.best_match)
        self.assertGreaterEqual(recommendations[0].score, 55)
        self.assertTrue(recommendations[0].reason)
        self.assertEqual(StudioRecommendation.objects.filter(user=self.user).count(), 2)

    def test_get_recommendations_auto_generates_when_empty(self):
        recommendations = get_user_recommendations(self.user)

        self.assertTrue(recommendations)
        self.assertTrue(hasattr(recommendations[0], "match_percent"))
        self.assertTrue(hasattr(recommendations[0], "display_price"))
