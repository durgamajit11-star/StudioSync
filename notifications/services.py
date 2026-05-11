from django.utils.text import Truncator

from .models import Notification


def create_notification(user, message, notification_type='general'):
    clean_message = ' '.join((message or '').split())
    if not user or not clean_message:
        return None

    return Notification.objects.create(
        user=user,
        message=Truncator(clean_message).chars(500),
        type=notification_type,
    )
