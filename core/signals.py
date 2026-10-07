from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from classes.models import Student

# Name of the attribute UserCreateSerializer sets on a new user to hand the
# phone number to create_student.
PHONE_NUMBER_ATTR = "_phone_number"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_student(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return
    # Users created by createsuperuser or the admin have no phone number and
    # get no Student.
    phone_number = getattr(instance, PHONE_NUMBER_ATTR, None)
    if phone_number:
        Student.objects.create(user=instance, phone_number=phone_number)
