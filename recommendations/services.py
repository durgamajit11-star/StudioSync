import math
import re
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Min

from bookings.models import BookingRequest
from studios.models import Review, Studio

from .models import StudioRecommendation


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(*values):
    text = " ".join(str(value or "").lower() for value in values)
    return Counter(token for token in TOKEN_RE.findall(text) if len(token) > 2)


def _weighted_overlap(left, right):
    if not left or not right:
        return 0.0
    overlap = sum(min(left[token], right[token]) for token in left.keys() & right.keys())
    total = sum(left.values()) or 1
    return min(1.0, overlap / total)


def _price_match(studio_price, preferred_budget):
    if not studio_price or not preferred_budget:
        return 0.5
    studio_price = float(studio_price)
    preferred_budget = float(preferred_budget)
    if studio_price <= 0 or preferred_budget <= 0:
        return 0.5
    distance = abs(studio_price - preferred_budget) / preferred_budget
    return max(0.0, 1.0 - min(distance, 1.0))


def _build_user_profile(user):
    bookings = list(
        BookingRequest.objects.filter(user=user)
        .exclude(status="Cancelled")
        .select_related("studio", "studio__category", "service")
        .order_by("-created_at")[:30]
    )
    reviews = list(
        Review.objects.filter(user=user)
        .select_related("studio", "studio__category")
        .order_by("-created_at")[:30]
    )

    profile_tokens = Counter()
    locations = Counter()
    categories = Counter()
    total_budget = Decimal("0")
    budget_samples = 0

    for booking in bookings:
        studio = booking.studio
        if booking.location:
            locations.update(_tokens(booking.location))
        if studio.location:
            locations.update(_tokens(studio.location))
        if studio.category:
            categories[studio.category_id] += 1
        if booking.amount:
            total_budget += Decimal(booking.amount)
            budget_samples += 1
        profile_tokens.update(
            _tokens(
                booking.event_type,
                booking.special_requirements,
                booking.service.service_name if booking.service else "",
                studio.specializations,
                studio.description,
                studio.category.name if studio.category else "",
            )
        )

    for review in reviews:
        if review.rating >= 4:
            studio = review.studio
            if studio.category:
                categories[studio.category_id] += 2
            if studio.location:
                locations.update(_tokens(studio.location))
            profile_tokens.update(
                _tokens(
                    review.comment,
                    studio.specializations,
                    studio.description,
                    studio.category.name if studio.category else "",
                )
            )

    if getattr(user, "address", None):
        locations.update(_tokens(user.address))

    return {
        "has_activity": bool(bookings or reviews or locations or categories or profile_tokens),
        "tokens": profile_tokens,
        "locations": locations,
        "categories": categories,
        "preferred_budget": (total_budget / budget_samples) if budget_samples else None,
        "booked_studio_ids": {booking.studio_id for booking in bookings},
    }


def _studio_price(studio):
    min_service_price = getattr(studio, "min_service_price", None)
    if studio.price_per_hour and studio.price_per_hour > 0:
        return studio.price_per_hour
    if min_service_price and min_service_price > 0:
        return min_service_price
    return None


def _score_studio(studio, profile):
    avg_rating = float(getattr(studio, "avg_rating", None) or studio.rating or 0)
    review_count = int(getattr(studio, "review_count", 0) or 0)
    booking_count = int(getattr(studio, "booking_count", 0) or 0)
    studio_tokens = _tokens(
        studio.studio_name,
        studio.description,
        studio.specializations,
        studio.location,
        studio.category.name if studio.category else "",
        " ".join(studio.services.values_list("service_name", flat=True)),
    )

    quality_score = 0
    quality_score += min(avg_rating, 5.0) / 5.0 * 18
    quality_score += min(math.log1p(review_count) / math.log1p(20), 1.0) * 7
    quality_score += min(math.log1p(booking_count) / math.log1p(25), 1.0) * 8
    quality_score += 4 if studio.is_featured else 0
    quality_score += min((studio.experience_years or 0) / 10, 1.0) * 5

    location_match = _weighted_overlap(profile["locations"], _tokens(studio.location))
    content_match = _weighted_overlap(profile["tokens"], studio_tokens)
    category_match = 1.0 if studio.category_id and studio.category_id in profile["categories"] else 0.0
    price_match = _price_match(_studio_price(studio), profile["preferred_budget"])

    personal_score = 0
    personal_score += location_match * 12
    personal_score += content_match * 14
    personal_score += category_match * 10
    personal_score += price_match * 8
    if studio.id in profile["booked_studio_ids"]:
        personal_score += 4

    cold_start_score = 0
    if not profile["has_activity"]:
        cold_start_score += 10 if studio.is_featured else 0
        cold_start_score += min(avg_rating, 5.0) / 5.0 * 20
        cold_start_score += min(math.log1p(booking_count) / math.log1p(25), 1.0) * 12

    score = 35 + quality_score + personal_score + cold_start_score
    return max(55, min(99, round(score, 1))), {
        "avg_rating": avg_rating,
        "location_match": location_match,
        "category_match": category_match,
        "content_match": content_match,
        "price_match": price_match,
    }


def _reason_for(studio, profile, signals):
    reasons = []
    if signals["category_match"] and studio.category:
        reasons.append(f"matches your interest in {studio.category.name}")
    if signals["location_match"] >= 0.25:
        reasons.append(f"fits your preferred location around {studio.location}")
    if signals["content_match"] >= 0.2:
        reasons.append("matches your recent booking style")
    if signals["price_match"] >= 0.8 and profile["preferred_budget"]:
        reasons.append("fits your usual budget")
    if signals["avg_rating"] >= 4:
        reasons.append(f"has a strong {signals['avg_rating']:.1f}/5 rating")
    if not reasons and studio.is_featured:
        reasons.append("is featured by StudioSync")
    if not reasons:
        reasons.append("is a verified studio with strong platform activity")
    return "Recommended because it " + ", ".join(reasons[:3]) + "."


def _decorate_recommendations(recommendations):
    for rec in recommendations:
        studio = rec.studio
        if getattr(rec, "min_service_price", None) is not None:
            studio.min_service_price = rec.min_service_price
        if getattr(rec, "avg_rating", None) is not None:
            studio.avg_rating = rec.avg_rating
        price = _studio_price(studio)
        rec.match_percent = max(0, min(100, int(round(rec.score or 0))))
        rec.display_location = studio.location or "Location available on request"
        rec.display_rating = getattr(studio, "avg_rating", None) or studio.average_rating()
        rec.review_count = getattr(studio, "review_count", None) or studio.reviews.count()
        if price:
            prefix = "Rs."
            rec.display_price = f"{prefix} {int(price)}/hr" if studio.price_per_hour else f"From {prefix} {int(price)}"
        elif studio.price_range:
            rec.display_price = studio.price_range
        else:
            rec.display_price = "Contact for pricing"
    return recommendations


def refresh_user_recommendations(user, limit=12):
    profile = _build_user_profile(user)
    studios = list(
        Studio.objects.filter(is_verified=True, user__is_active=True)
        .select_related("category")
        .prefetch_related("services")
        .annotate(
            avg_rating=Avg("reviews__rating"),
            review_count=Count("reviews", distinct=True),
            booking_count=Count("booking_requests", distinct=True),
            min_service_price=Min("services__price"),
        )
        .order_by("-is_featured", "-created_at")[:100]
    )

    scored = []
    for studio in studios:
        score, signals = _score_studio(studio, profile)
        scored.append((score, studio, _reason_for(studio, profile, signals)))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:limit]

    with transaction.atomic():
        keep_ids = []
        for score, studio, reason in selected:
            keep_ids.append(studio.id)
            StudioRecommendation.objects.update_or_create(
                user=user,
                studio=studio,
                defaults={"score": score, "reason": reason},
            )
        StudioRecommendation.objects.filter(user=user).exclude(studio_id__in=keep_ids).delete()

    return get_user_recommendations(user, limit=limit, refresh=False)


def get_user_recommendations(user, limit=12, refresh=True):
    if refresh:
        existing_count = StudioRecommendation.objects.filter(user=user, studio__is_verified=True).count()
        if existing_count < min(limit, 4):
            return refresh_user_recommendations(user, limit=limit)

    recommendations = list(
        StudioRecommendation.objects.filter(user=user, studio__is_verified=True, studio__user__is_active=True)
        .select_related("studio", "studio__category")
        .prefetch_related("studio__services")
        .annotate(
            avg_rating=Avg("studio__reviews__rating"),
            review_count=Count("studio__reviews", distinct=True),
            min_service_price=Min("studio__services__price"),
        )
        .order_by("-score", "-updated_at")[:limit]
    )
    return _decorate_recommendations(recommendations)
