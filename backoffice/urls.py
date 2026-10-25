from django.contrib import admin
from django.urls import path, re_path

from server.django_api import bridge_view, frontend_view
from .static_views import serve_admin_static

admin.site.site_header = 'Очаково: изнутри'
admin.site.site_title = 'Управление Очаково'
admin.site.index_title = 'Панель управления'

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^api(?:/.*)?$', bridge_view),
    path('static/<path:path>', serve_admin_static),
    re_path(r'^(?P<path>.*)$', frontend_view),
]
