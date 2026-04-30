from rest_framework import serializers
from studios.models import Studio, Portfolio, Review
from bookings.models import BookingRequest, BookingNote
from payments.models import Payment


# ==================== STUDIO SERIALIZERS ====================

class PortfolioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Portfolio
        fields = ['id', 'image', 'caption', 'uploaded_at']


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'user', 'user_name', 'rating', 'comment', 'created_at']


class StudioListSerializer(serializers.ModelSerializer):
    avg_rating = serializers.SerializerMethodField()
    total_bookings = serializers.SerializerMethodField()
    
    class Meta:
        model = Studio
        fields = ['id', 'studio_name', 'location', 'description', 'profile_image', 
                  'is_verified', 'avg_rating', 'total_bookings', 'experience_years']
    
    def get_avg_rating(self, obj):
        return obj.average_rating()
    
    def get_total_bookings(self, obj):
        return obj.total_bookings()


class StudioDetailSerializer(serializers.ModelSerializer):
    portfolios = PortfolioSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    avg_rating = serializers.SerializerMethodField()
    total_bookings = serializers.SerializerMethodField()
    
    class Meta:
        model = Studio
        fields = ['id', 'studio_name', 'location', 'description', 'profile_image',
                  'is_featured', 'is_verified', 'price_range', 'experience_years',
                  'specializations', 'phone', 'email', 'website', 'portfolios', 'reviews',
                  'avg_rating', 'total_bookings', 'created_at']
    
    def get_avg_rating(self, obj):
        return obj.average_rating()
    
    def get_total_bookings(self, obj):
        return obj.total_bookings()


# ==================== BOOKING SERIALIZERS ====================

class BookingNoteSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = BookingNote
        fields = ['id', 'user', 'user_name', 'message', 'created_at']


class BookingRequestSerializer(serializers.ModelSerializer):
    notes = BookingNoteSerializer(many=True, read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    studio_name = serializers.CharField(source='studio.studio_name', read_only=True)
    
    class Meta:
        model = BookingRequest
        fields = ['id', 'user', 'user_name', 'studio', 'studio_name', 'event_type',
                  'date', 'time', 'start_time', 'end_time', 'time_slot', 'duration_hours', 'location', 'special_requirements',
                  'amount', 'deposit_amount', 'status', 'payment_status', 'notes', 'created_at']


# ==================== PAYMENT SERIALIZERS ====================

class PaymentSerializer(serializers.ModelSerializer):
    booking_details = BookingRequestSerializer(source='booking', read_only=True)
    
    class Meta:
        model = Payment
        fields = ['id', 'booking', 'booking_details', 'amount', 'transaction_id',
                  'status', 'payment_method', 'gateway', 'gateway_order_id',
                  'gateway_payment_id', 'gateway_status', 'failure_reason',
                  'created_at', 'completed_at']
