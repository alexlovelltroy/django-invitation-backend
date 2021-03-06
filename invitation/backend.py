from registration import signals
from django.contrib.auth.models import User
from django.contrib.auth.backends import ModelBackend

from .util import get_user, create_user


class InvitationBackend(object):
    def register(self, request, **kwargs):
        email, password = kwargs['email'], kwargs['password']
        last_name = kwargs.get('last_name', None)
        first_name = kwargs.get('first_name', None)
        new_user = create_user(email, password,
                               is_active=True,
                               first_name=first_name,
                               last_name=last_name,
                               )
        signals.user_registered.send(sender=self.__class__,
                                     user=new_user,
                                     request=request)
        return new_user


class EmailAuthBackend(ModelBackend):

    """Allow users to log in with their email address"""

    def authenticate(self, email=None, password=None, **kwargs):
        # Some authenticators expect to authenticate by 'username'
        if email is None:
            email = kwargs.get('username')

        try:
            user = get_user(email)
            if user.check_password(password):
                user.backend = "%s.%s" % (self.__module__, self.__class__.__name__)
                return user
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
