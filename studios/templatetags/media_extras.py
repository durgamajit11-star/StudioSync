from django import template
from django.core.files.storage import default_storage


register = template.Library()


@register.filter
def storage_exists(file_field):
    if not file_field:
        return False

    try:
        name = file_field.name
    except ValueError:
        return False

    if not name:
        return False

    try:
        return default_storage.exists(name)
    except Exception:
        return False
