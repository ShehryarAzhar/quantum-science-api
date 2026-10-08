from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import TRIAL_LESSON_LOCKED_MESSAGE


class IsStudent(BasePermission):
    message = "Only students can use this resource."

    def has_permission(self, request, view):
        # Users created by createsuperuser or the admin have no Student.
        return hasattr(request.user, "student")


class IsTrialLessonOpen(BasePermission):
    message = TRIAL_LESSON_LOCKED_MESSAGE

    def has_object_permission(self, request, view, obj):
        # A locked lesson stays readable.
        return request.method in SAFE_METHODS or not obj.is_locked
