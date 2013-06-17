import datetime
import hashlib
import random

from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site, RequestSite
from django.db import models
from django.template.loader import render_to_string
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from .util import _email_to_username

import app_settings
import signals


class InvitationError(Exception):
    pass


class InvitationManager(models.Manager):
    def invite(self, user, email=None, first_name=None, last_name=None):
        """Get or create an invitation for ``email`` from ``user``.

        This method doesn't an send email. You need to call ``send_email()``
        method on returned ``Invitation`` instance.
        """
        invitation = None
        if email:
            oursecret = "%s%s" % (user.email, email)
            try:
                # It is possible that there is more than one invitation fitting
                # the criteria. Normally this means some older invitations are
                # expired or an email is invited consequtively.
                invitation = self.filter(user=user, email=email)[0]
                if not invitation.is_valid():
                    invitation = None
            except (Invitation.DoesNotExist, IndexError):
                pass
        elif first_name and last_name:
            oursecret = "%s%s%s" % (user.email, first_name, last_name)
            try:
                # It is possible that there is more than one invitation fitting
                # the criteria. Normally this means some older invitations are
                # expired or an email is invited consequtively.
                invitation = self.filter(user=user, first_name=first_name, last_name=last_name)[0]
                if not invitation.is_valid():
                    invitation = None
            except (Invitation.DoesNotExist, IndexError):
                pass
        if invitation is None:
            prekey = '%s%0.16f%s' % (settings.SECRET_KEY, random.random(),
                                    oursecret)
            key = hashlib.sha1(prekey).hexdigest()
            if not email:
                email = ""
            if not first_name:
                first_name = ""
            if not last_name:
                last_name = ""
            invitation = self.create(user=user, email=email, first_name=first_name, last_name=last_name,  key=key)
            signals.invitation_added.send(sender=self, invitation=invitation)
        return invitation
    invite.alters_data = True

    def find(self, invitation_key):
        """Find a valid invitation for the given key or raise
        ``Invitation.DoesNotExist``.

        This function always returns a valid invitation. If an invitation is
        found but not valid it will be automatically deleted.
        """
        try:
            invitation = self.filter(key=invitation_key)[0]
        except IndexError:
            raise Invitation.DoesNotExist
        if not invitation.is_valid():
            invitation.delete()
            raise Invitation.DoesNotExist
        return invitation

    def valid(self):
        """Filter valid invitations."""
        expiration = now() - datetime.timedelta(app_settings.EXPIRE_DAYS)
        return self.get_query_set().filter(date_invited__gte=expiration)

    def invalid(self):
        """Filter invalid invitation."""
        expiration = now() - datetime.timedelta(app_settings.EXPIRE_DAYS)
        return self.get_query_set().filter(date_invited__le=expiration)

    def delete_expired_keys(self):
        """Removes expired instances of ``Invitation``.

        Invitation keys to be deleted are identified by searching for
        instances of ``Invitation`` with difference between now and
        `date_invited` date greater than ``EXPIRE_DAYS``.

        It is recommended that this method be executed regularly as
        part of your routine site maintenance; this application
        provides a custom management command which will call this
        method, accessible as ``manage.py cleanupinvitations``.
        """
        return self.invalid().delete()


class Invitation(models.Model):
    user = models.ForeignKey(User, related_name='invitations', verbose_name="Existing User")
    first_name = models.CharField(u'first name', max_length=30, blank=True, null=True)
    last_name = models.CharField(u'last name', max_length=30, blank=True, null=True)
    email = models.EmailField(u'e-mail', blank=True, null=True)
    key = models.CharField(_(u'invitation key'), max_length=40, unique=True)
    date_invited = models.DateTimeField(_(u'date invited'), default=now())

    objects = InvitationManager()

    class Meta:
        verbose_name = _(u'invitation')
        verbose_name_plural = _(u'invitations')
        ordering = ('-date_invited',)

    def __unicode__(self):
        return _('%(username)s invited %(email)s on %(date)s') % {
            'username': self.user.username,
            'email': self.email,
            'date': str(self.date_invited.date()),
        }

    @models.permalink
    def get_absolute_url(self):
        return ('invitation_register', (), {'invitation_key': self.key})

    @property
    def _expires_at(self):
        return self.date_invited + datetime.timedelta(app_settings.EXPIRE_DAYS)

    def is_valid(self):
        """Return ``True`` if the invitation is still valid, ``False``
        otherwise.
        """
        return now() < self._expires_at

    def expiration_date(self):
        """Return a ``datetime.date()`` object representing expiration date.
        """
        return self._expires_at.date()
    expiration_date.short_description = _(u'expiration date')
    expiration_date.admin_order_field = 'date_invited'

    def send_email(self, email=None, site=None, request=None):
        """Send invitation email.

        Both ``email`` and ``site`` parameters are optional. If not supplied
        instance's ``email`` field and current site will be used.

        **Templates:**

        :invitation/invitation_email_subject.txt:
            Template used to render the email subject.

            **Context:**

            :invitation: ``Invitation`` instance ``send_email`` is called on.
            :site: ``Site`` instance to be used.

        :invitation/invitation_email.txt:
            Template used to render the email body.

            **Context:**

            :invitation: ``Invitation`` instance ``send_email`` is called on.
            :expiration_days: ``INVITATION_EXPIRE_DAYS`` setting.
            :site: ``Site`` instance to be used.

        **Signals:**

        ``invitation.signals.invitation_sent`` is sent on completion.
        """
        email = email or self.email
        if site is None:
            if Site._meta.installed:
                site = Site.objects.get_current()
            elif request is not None:
                site = RequestSite(request)
        subject = render_to_string('invitation/invitation_email_subject.txt',
                                   {'invitation': self, 'site': site})
        # Email subject *must not* contain newlines
        subject = ''.join(subject.splitlines())
        message = render_to_string('invitation/invitation_email.txt', {
            'invitation': self,
            'expiration_days': app_settings.EXPIRE_DAYS,
            'site': site
        })
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        signals.invitation_sent.send(sender=self)

    def mark_accepted(self, new_user):
        """Update sender's invitation statistics and delete self.

        ``invitation.signals.invitation_accepted`` is sent just before the
        instance is deleted.
        """
        signals.invitation_accepted.send(sender=self,
                                         inviting_user=self.user,
                                         new_user=new_user)
        self.delete()
    mark_accepted.alters_data = True




# Horrible monkey patching.
# User.username always presents as the email, but saves as a hash of the email.
# It would be possible to avoid such a deep level of monkey-patching,
# but Django's admin displays the "Welcome, username" using user.username,
# and there's really no other way to get around it.
def user_init_patch(self, *args, **kwargs):
    super(User, self).__init__(*args, **kwargs)
    self._username = self.username
    if self.username == _email_to_username(self.email):
        # Username should be replaced by email, since the hashes match
        self.username = self.email


def user_save_patch(self, *args, **kwargs):
    email_as_username = (self.username.lower() == self.email.lower())
    if self.pk is not None:
        old_user = self.__class__.objects.get(pk=self.pk)
        email_as_username = (
            email_as_username or
            ('@' in self.username and old_user.username == old_user.email)
        )

    if email_as_username:
        self.username = _email_to_username(self.email)
    try:
        super(User, self).save_base(*args, **kwargs)
    finally:
        if email_as_username:
            self.username = self.email


original_init = User.__init__
original_save_base = User.save_base


def monkeypatch_user():
    User.__init__ = user_init_patch
    User.save_base = user_save_patch


def unmonkeypatch_user():
    User.__init__ = original_init
    User.save_base = original_save_base


monkeypatch_user()
