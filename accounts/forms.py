
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


def _validate_password_strength(password: str) -> str:
    try:
        validate_password(password)
    except ValidationError as exc:
        raise forms.ValidationError(list(exc.messages))
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise forms.ValidationError(
            "Password must contain at least one letter and one number."
        )
    return password


class CustomerRegisterForm(forms.Form):
    full_name = forms.CharField(max_length=255, required=False)
    email     = forms.EmailField()
    password  = forms.CharField(min_length=8, widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        return _validate_password_strength(self.cleaned_data["password"])

    def clean(self):
        cleaned = super().clean()
        pw  = cleaned.get("password")
        pw2 = cleaned.get("password2")
        if pw and pw2 and pw != pw2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class CustomerLoginForm(forms.Form):
    email       = forms.EmailField()
    password    = forms.CharField(widget=forms.PasswordInput)
    remember_me = forms.BooleanField(required=False)

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()



class AdminLoginForm(forms.Form):
    email    = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    remember = forms.BooleanField(required=False)

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()



class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()


class PasswordResetConfirmForm(forms.Form):
    password  = forms.CharField(min_length=8, widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_password(self):
        return _validate_password_strength(self.cleaned_data["password"])

    def clean(self):
        cleaned = super().clean()
        pw  = cleaned.get("password")
        pw2 = cleaned.get("password2")
        if pw and pw2 and pw != pw2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class ChangePasswordForm(forms.Form):
    old_password  = forms.CharField(widget=forms.PasswordInput)
    new_password  = forms.CharField(min_length=8, widget=forms.PasswordInput)
    new_password2 = forms.CharField(widget=forms.PasswordInput, label="Confirm new password")

    def clean_new_password(self):
        return _validate_password_strength(self.cleaned_data["new_password"])

    def clean(self):
        cleaned = super().clean()
        pw  = cleaned.get("new_password")
        pw2 = cleaned.get("new_password2")
        if pw and pw2 and pw != pw2:
            self.add_error("new_password2", "Passwords do not match.")
        return cleaned



class ProfileUpdateForm(forms.Form):
    full_name = forms.CharField(max_length=255, required=False)