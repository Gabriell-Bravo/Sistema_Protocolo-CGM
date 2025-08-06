# processos/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Processo, Profile # Import Profile

class CustomUserCreationForm(UserCreationForm):
    # Add a field for the user level
    level = forms.ChoiceField(
        choices=Profile.USER_LEVEL_CHOICES,
        label="Nível do Usuário",
        initial='3'
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('is_staff', 'is_superuser', 'email',) # Include is_staff and is_superuser

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'] # Save email
        if commit:
            user.save()
            # Create or update profile
            profile, created = Profile.objects.get_or_create(user=user)
            profile.level = self.cleaned_data['level']
            profile.save()
        return user

# ... (rest of your forms like ProcessoForm, AuthenticationForm remain the same)
class ProcessoForm(forms.ModelForm):
    # Your existing ProcessoForm...
    class Meta:
        model = Processo
        fields = '__all__'


# If you have an existing AuthenticationForm, ensure it's here
class AuthenticationForm(AuthenticationForm):
    pass