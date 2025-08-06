# protocolo_project/urls.py
from django.contrib import admin
from django.urls import path, include  # Adicione 'include' aqui
from django.conf import settings
from django.conf.urls.static import static
from processos_app import views
from django.urls import path
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('processos_app.urls')),
    path('accounts/', include('django.contrib.auth.urls')),  # Nova linha
    # Esta URL será para a sua custom login view
    path('login/', views.user_login, name='login'),
    # Nova URL para registro de usuário
    path('register/', views.register, name='register'),
    # Nova URL para gerenciar usuários
    path('manage_users/', views.manage_users, name='manage_users'),
    path('password_change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html'), name='password_change'),
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html'), name='password_change_done'),
]

# Apenas para desenvolvimento: servir arquivos estáticos e de mídia
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
