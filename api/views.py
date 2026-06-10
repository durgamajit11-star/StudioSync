from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import models
from studios.models import Studio, Portfolio, Review
from bookings.models import BookingRequest, BookingNote
from payments.models import Payment
from .serializers import (
    StudioListSerializer, StudioDetailSerializer, PortfolioSerializer,
    ReviewSerializer, BookingRequestSerializer, BookingNoteSerializer,
    PaymentSerializer
)


# ==================== STUDIO VIEWSETS ====================

class StudioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Studio.objects.all()
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = Studio.objects.all()
        user = self.request.user

        if user.is_authenticated and user.is_staff:
            return queryset

        return queryset.filter(is_verified=True)
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return StudioDetailSerializer
        return StudioListSerializer
    
    @action(detail=True, methods=['get'])
    def portfolio(self, request, pk=None):
        studio = self.get_object()
        portfolios = studio.portfolios.all()
        serializer = PortfolioSerializer(portfolios, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        studio = self.get_object()
        reviews = studio.reviews.all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        featured_studios = self.get_queryset().filter(is_featured=True)[:6]
        serializer = self.get_serializer(featured_studios, many=True)
        return Response(serializer.data)


class PortfolioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Portfolio.objects.filter(studio__is_verified=True)
    serializer_class = PortfolioSerializer
    permission_classes = [AllowAny]


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# ==================== BOOKING VIEWSETS ====================

class BookingRequestViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BookingRequestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        # Return bookings for the user or the studio owner
        if hasattr(user, 'studio'):
            return BookingRequest.objects.filter(studio__user=user)
        return BookingRequest.objects.filter(user=user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        booking = self.get_object()
        if booking.studio.user != request.user:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        booking.status = 'Confirmed'
        booking.save()
        return Response({'status': 'booking approved'})
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        booking = self.get_object()
        if booking.studio.user != request.user:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        booking.status = 'Cancelled'
        booking.save()
        return Response({'status': 'booking rejected'})


class BookingNoteViewSet(viewsets.ModelViewSet):
    serializer_class = BookingNoteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        return BookingNote.objects.filter(
            models.Q(booking__user=user) | models.Q(booking__studio__user=user)
        ).distinct()
    
    def perform_create(self, serializer):
        booking = serializer.validated_data['booking']
        if booking.user != self.request.user and booking.studio.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this booking.')
        serializer.save(user=self.request.user)


# ==================== PAYMENT VIEWSETS ====================

class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)
