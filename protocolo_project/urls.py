# protocolo_project/urls.py
from django.contrib import admin
from django.urls import path, include # Adicione 'include' aqui
from django.conf import settings
from django.conf.urls.static import static
from processos_app import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('processos_app.urls')),
    path('accounts/', include('django.contrib.auth.urls')), # Nova linha
    path('login/', views.user_login, name='login'), # Esta URL será para a sua custom login view
    path('register/', views.register, name='register'), # Nova URL para registro de usuário
    path('manage_users/', views.manage_users, name='manage_users'), # Nova URL para gerenciar usuários
]

# Apenas para desenvolvimento: servir arquivos estáticos e de mídia
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)