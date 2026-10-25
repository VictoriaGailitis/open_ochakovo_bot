"""Django transport for the VK Mini App and its shared PostgreSQL domain."""
import json
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings
from django.db import DatabaseError
from django.db import transaction as django_transaction
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt

from .app import API, APIError, MAX_BODY
from . import media
from .postgres import runtime_store
from .level_rules import runtime_rule_source


class PostgreSQLAPI(API):
    def __init__(self):
        config=dict(os.environ)
        super().__init__(runtime_store(),config)

    def item(self,group,item_id):
        from .catalog_store import item
        value=item(None,group,item_id)
        if value is None:raise APIError(404,'Объект не найден или снят с публикации.','not_found')
        return value

    def dispatch(self,*args,**kwargs):
        if args[1].rstrip('/').startswith('/api/admin'):
            raise APIError(410, 'Используйте кабинет команды с персональным доступом.', 'admin_api_retired')
        from .catalog_store import resolve_rule
        token=runtime_rule_source.set(resolve_rule)
        try:
            if args[0]=='PUT' and args[1].rstrip('/')=='/api/profile':
                from backoffice.operations.models import ConsentHistory
                from .postgres import connect
                with django_transaction.atomic():
                    result=super().dispatch(*args,**kwargs)
                    headers=kwargs.get('headers') or (args[3] if len(args)>3 else {})
                    uid=self.session(connect(),headers)
                    profile=result['profile']
                    ConsentHistory.objects.create(user_id=uid,actor=None,event='granted',consent=True,future_contact=profile.get('futureContact') is True,original_consented_at=profile['consentedAt'],policy_version='2026-10-25-v1',reason='Пользователь сохранил анкету и подтвердил согласие в мини-приложении.')
            else:result=super().dispatch(*args,**kwargs)
            if args[0]=='GET' and args[1].rstrip('/')=='/api/health':
                from .postgres import connect
                connect().execute('SELECT 1')
                result['database']='postgresql'
            return result
        finally:runtime_rule_source.reset(token)


def _response_error(error):
    value={'error':error.message,'code':error.code}
    if error.details:value['details']=error.details
    return JsonResponse(value,status=error.status,json_dumps_params={'ensure_ascii':False})


@xframe_options_exempt
@csrf_exempt
def bridge_view(request,**kwargs):
    # Bearer-only endpoints do not use Django's admin session or cookie authority.
    # Django /admin/ keeps its own CSRF middleware and authentication.
    api=PostgreSQLAPI()
    response=None
    origin=request.headers.get('Origin','')
    allowed=set(filter(None,api.config.get('ALLOWED_ORIGINS','').split(',')))
    own=request.build_absolute_uri('/').rstrip('/')
    if origin and origin not in allowed and origin!=own:
        return _response_error(APIError(403,'Источник запроса не разрешён.','origin_forbidden'))
    try:
        if request.method=='OPTIONS':
            response=HttpResponse(status=204)
            response['Access-Control-Allow-Methods']='GET, POST, PUT, DELETE, PATCH, OPTIONS'
            response['Access-Control-Allow-Headers']='Authorization, Content-Type, X-Admin-Token, X-File-Name, X-Media-Audience'
        else:
            if request.path.rstrip('/').startswith('/api/admin'):
                raise APIError(410, 'Используйте кабинет команды с персональным доступом.', 'admin_api_retired')
            upload=request.method=='POST' and request.path.rstrip('/')=='/api/admin/media'
            if upload:api.require_admin(request.headers)
            try:length=int(request.headers.get('Content-Length') or '0')
            except ValueError:raise APIError(400,'Некорректная длина запроса.')
            if not 0<=length<=(media.MAX_UPLOAD if upload else MAX_BODY):raise APIError(413,'Запрос слишком большой.')
            body={}
            if upload:body=request.body
            elif length:
                if request.content_type!='application/json':raise APIError(415,'Используйте application/json.')
                try:body=json.loads(request.body)
                except (ValueError,UnicodeDecodeError):raise APIError(400,'Некорректный JSON.')
                if not isinstance(body,dict):raise APIError(400,'Тело запроса должно быть объектом.')
            if request.path.rstrip('/')=='/api/game-assets' and request.method=='GET':
                from .catalog_store import publicassets
                result=publicassets()
            elif request.method=='GET' and (match:=re.fullmatch(r'/api/game-assets/([A-Za-z0-9_-]+)/?',request.path)):
                from .catalog_store import asset
                result=asset(match[1])
                if result is None:raise APIError(404,'Спрайт не найден.','not_found')
            else:result=api.dispatch(request.method,request.path,body,request.headers,request.META.get('REMOTE_ADDR','127.0.0.1'))
            if isinstance(result,dict) and isinstance(result.get('content'),bytes):
                response=HttpResponse(result['content'],content_type=result['mimeType'])
                response['Content-Disposition']='inline; filename="'+result['filename']+'"'
                response['Content-Security-Policy']="default-src 'none'; sandbox"
            else:response=JsonResponse(result,safe=not isinstance(result,list),json_dumps_params={'ensure_ascii':False})
    except APIError as error:response=_response_error(error)
    except DatabaseError:response=_response_error(APIError(503,'Хранилище временно недоступно. Повторите запрос.','storage_unavailable'))
    response['Cache-Control']='no-store'
    response['X-Content-Type-Options']='nosniff'
    if origin in allowed:
        response['Access-Control-Allow-Origin']=origin
        response['Vary']='Origin'
    return response


@xframe_options_exempt
def frontend_view(request,path=''):
    if request.method not in ('GET','HEAD'):return HttpResponse(status=405)
    root=Path(settings.BASE_DIR,'dist').resolve()
    route=unquote(path)
    if '\\' in route or any(part.startswith('.') or part=='..' for part in Path(route).parts):return HttpResponse(status=404)
    target=(root/route).resolve()
    if not target.is_relative_to(root):return HttpResponse(status=404)
    if not route:target=root/'index.html'
    elif not target.is_file() and not Path(route).suffix:target=root/'index.html'
    if not target.is_file():return HttpResponse('Выполните npm run build.',status=404)
    response=FileResponse(target.open('rb'),content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
    response['Cache-Control']='no-cache' if target.suffix=='.html' else 'public, max-age=3600'
    return response
