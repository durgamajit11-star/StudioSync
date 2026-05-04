from django.shortcuts import render, redirect, get_object_or_404
from .models import Notification
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from django.views.decorators.http import require_POST
from django.contrib import messages


@login_required
@role_required(['USER'])
def user_notifications(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    unread_count = notifications.filter(is_read=False).count()

    return render(request, 'user/dashboard/user_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
@role_required(['USER'])
@require_POST  # SECURITY FIX: state-change must be POST only — prevents CSRF via GET links
def mark_as_read(request, id):
    n = get_object_or_404(Notification, id=id, user=request.user)
    n.is_read = True
    n.save(update_fields=['is_read'])
    return redirect('user_notifications')  # FIX: was 'notifications' (NoReverseMatch)


@login_required
@role_required(['USER'])
@require_POST
def clear_notifications(request):
    deleted_count, _ = Notification.objects.filter(user=request.user).delete()
    messages.success(request, f'Cleared {deleted_count} notification(s).')
    return redirect('user_notifications')  # FIX: was 'notifications' (NoReverseMatch)