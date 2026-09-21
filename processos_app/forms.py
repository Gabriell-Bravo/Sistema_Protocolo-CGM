# processos/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import User
from .models import Processo, Profile # Import Profile
from .services.permissions import PAPEL_PARA_NIVEL

class CustomUserCreationForm(UserCreationForm):
    # O campo continua se chamando `level` no POST, mas grava o papel novo
    # e mantém o nível legado em sincronia.
    level = forms.ChoiceField(
        choices=Profile.PAPEL_CHOICES,
        label="Papel do Usuário",
        initial='GESTAO'
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
            profile.papel = self.cleaned_data['level']
            profile.level = PAPEL_PARA_NIVEL.get(profile.papel, '3')
            profile.save()
        return user


class AdminResetPasswordForm(SetPasswordForm):
    """Redefinição de senha feita pelo superadministrador, sem a senha atual."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['new_password1'].label = 'Nova senha'
        self.fields['new_password2'].label = 'Confirme a nova senha'

# ... (rest of your forms like ProcessoForm, AuthenticationForm remain the same)
class ProcessoForm(forms.ModelForm):
    """item 18: lista EXPLÍCITA de campos — só dados de protocolo (item 17).

    A criação de processo não passa mais por este form: a regra única está
    em services/processos.criar_processo. O form continua disponível para
    quem precisar renderizar os campos de protocolo.
    """
    volume = forms.CharField(required=True, max_length=255, label='Volume')

    class Meta:
        model = Processo
        fields = [
            'numero_processo', 'volume', 'secretaria', 'data_entrada',
            'hora_entrada', 'genero', 'especie', 'objeto', 'contratada',
            'recorrente',
        ]


# If you have an existing AuthenticationForm, ensure it's here
class AuthenticationForm(AuthenticationForm):
    pass