from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms
from .models import CustomUser


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ("email",)


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ("email",)


class SignUpForm(UserCreationForm):
    common_attrs = {
        "class": "w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-primary focus:border-primary text-sm"
    }
    first_name = forms.CharField(widget=forms.TextInput(attrs=common_attrs))
    last_name = forms.CharField(widget=forms.TextInput(attrs=common_attrs))
    email = forms.CharField(widget=forms.TextInput(attrs=common_attrs))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs=common_attrs))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs=common_attrs))

    class Meta:
        model = CustomUser
        fields = ("first_name", "last_name", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)  # Call the parent class's save method
        # user.username = self.generate_unique_username(self.cleaned_data["first_name"]) # Removed
        user.is_active = True
        user.is_staff = False

        if commit:
            user.save()
        return user
