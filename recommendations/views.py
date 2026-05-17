from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_required
from .models import StudioRecommendation
from .services import get_user_recommendations, refresh_user_recommendations


@login_required
@role_required(['USER'])
def user_recommendations(request):
    """Display AI-powered studio recommendations for the current user"""
    try:
        recommendations = get_user_recommendations(request.user, limit=12)
    except Exception as e:
        messages.warning(request, f'Error loading recommendations: {str(e)}')
        recommendations = []
    
    context = {
        'recommendations': recommendations,
        'total_recommendations': len(recommendations),
    }
    return render(request, 'user/dashboard/user_recommendations.html', context)


@login_required
@role_required(['USER'])
def refresh_recommendations(request):
    """Refresh recommendations for the current user"""
    try:
        StudioRecommendation.objects.filter(user=request.user).delete()
        refresh_user_recommendations(request.user, limit=12)
        messages.success(request, 'Recommendations refreshed!')
    except Exception as e:
        messages.error(request, f'Error refreshing recommendations: {str(e)}')
    
    return redirect('user_recommendations')
