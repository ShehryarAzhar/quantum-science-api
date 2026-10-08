from rest_framework.permissions import BasePermission


class IsStudent(BasePermission):
    message = "Only students can use this resource."

    def has_permission(self, request, view):
        # Users created by createsuperuser or the admin have no Student.
        return hasattr(request.user, "student")
