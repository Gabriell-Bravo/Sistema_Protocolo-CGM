from django.conf import settings
def layout(request):
    return {'lai_shell':getattr(settings,'LAI_BASE_TEMPLATE','lai/shell.html'),
            'lai_integrado':getattr(settings,'LAI_BASE_TEMPLATE','')=='base.html'}
