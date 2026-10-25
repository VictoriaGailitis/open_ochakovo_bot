"""Serve public collected admin assets without exposing uploads or source files."""
import mimetypes

from django.conf import settings
from django.contrib.staticfiles.views import serve as development_static
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe


@require_safe
def serve_admin_static(request, path):
    if settings.DEBUG:
        return development_static(request, path, insecure=True)
    root = settings.STATIC_ROOT.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except (ValueError, OSError):
        raise Http404('Файл не найден.')
    if not target.is_file():
        raise Http404('Файл не найден.')
    try:
        stream = target.open('rb')
    except OSError:
        raise Http404('Файл не найден.')
    response = FileResponse(stream, content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    response['Cache-Control'] = 'public, max-age=3600'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
