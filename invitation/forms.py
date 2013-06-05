from django import forms
from django.contrib.auth.models import User
from registration.forms import RegistrationFormTermsOfService
from email_integration.models import EmailAddress


class InvitationForm(forms.Form):
    email = forms.EmailField()
def clean_email(self):
        """
        Validate that the supplied email address is unique for the
        site.

        """
        if User.objects.filter(email__iexact=self.cleaned_data['email']):
            raise forms.ValidationError("This email address is already in use. Please supply a different email address.")
        if EmailAddress.objects.filter(email_address__iexact=self.cleaned_data['email']):
            raise forms.ValidationError("This email address is already in use. Please supply a different email address.")
        return self.cleaned_data['email']

class Email(forms.EmailField):
    def clean(self, value):
        super(Email, self).clean(value)
        try:
            User.objects.get(email=value)

            raise forms.ValidationError("This email is already registered. Use the 'forgot password' link on the login page")
        except User.DoesNotExist:
            return value


class UserRegistrationForm(RegistrationFormTermsOfService):
    #email will be become username
    email = Email()
    first_name = forms.CharField(label="First Name")
    last_name = forms.CharField(label="Last Name")

    def __init__(self, *args, **kwargs):
        super (UserRegistrationForm, self).__init__(*args,**kwargs)
        self.fields.pop('username')
        self.fields.keyOrder = ['first_name', 'last_name', 'email', 'password1', 'password2', 'tos']
