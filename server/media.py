"""Authenticated image/video storage. No public paths or bearer tokens in URLs."""
import json
import re
import secrets
from datetime import datetime, timezone
from .errors import APIError
from .community import visible

MAX_UPLOAD=50*1024*1024
MIMES={'image/png':'png','image/jpeg':'jpg','image/webp':'webp','video/mp4':'mp4','video/webm':'webm'}


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS material_media (
        id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime_type TEXT NOT NULL,
        audience TEXT NOT NULL CHECK(audience IN ('candidate','staff','all')),
        size INTEGER NOT NULL CHECK(size>0), content BLOB NOT NULL, created TEXT NOT NULL)''')


def upload(db, data, headers):
    mime=headers.get('Content-Type','').split(';')[0].strip().lower()
    audience=headers.get('X-Media-Audience','candidate')
    name=headers.get('X-File-Name','media')
    if mime not in MIMES: raise APIError(415,'Поддерживаются PNG, JPEG, WebP, MP4 и WebM.','media_type')
    if audience not in ('candidate','staff','all'): raise APIError(422,'Укажите аудиторию файла.')
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_UPLOAD: raise APIError(413,'Размер файла должен быть от 1 байта до 50 МБ.')
    valid={'image/png':data.startswith(b'\x89PNG\r\n\x1a\n'),
           'image/jpeg':data.startswith(b'\xff\xd8\xff'),
           'image/webp':data.startswith(b'RIFF') and data[8:12]==b'WEBP',
           'video/mp4':len(data)>=12 and data[4:8]==b'ftyp',
           'video/webm':data.startswith(b'\x1aE\xdf\xa3')}[mime]
    if not valid: raise APIError(415,'Содержимое файла не соответствует формату.','media_type')
    if not isinstance(name,str) or len(name)>200 or any(ord(c)<32 for c in name): raise APIError(422,'Проверьте имя файла.')
    media_id='media-'+secrets.token_urlsafe(18)
    stamp=datetime.now(timezone.utc).isoformat()
    db.execute('INSERT INTO material_media VALUES(?,?,?,?,?,?,?)',(media_id,name,mime,audience,len(data),data,stamp))
    return {'media':{'id':media_id,'filename':name,'mimeType':mime,'audience':audience,'size':len(data),'created':stamp}}


def validate_media(db,media_id,audience):
    row=db.execute('SELECT audience FROM material_media WHERE id=?',(media_id,)).fetchone()
    if not row or (row['audience']!='all' and row['audience']!=audience):
        raise ValueError('Файл не найден или недоступен выбранной аудитории.')


def read(db,media_id,staff=False,admin=False):
    row=db.execute('SELECT * FROM material_media WHERE id=?',(media_id,)).fetchone()
    if not row or (not admin and not visible(row['audience'],staff)):
        raise APIError(404,'Файл не найден.','not_found')
    if not admin:
        # A guessed asset ID cannot reveal a draft or archived material.
        found=False
        for material in db.execute('SELECT blocks,audience FROM materials WHERE published=1 AND archived=0'):
            if visible(material['audience'],staff) and any(block.get('mediaId')==media_id for block in json.loads(material['blocks'])):
                found=True;break
        if not found: raise APIError(404,'Файл не найден.','not_found')
    return {'content':bytes(row['content']),'mimeType':row['mime_type'],'filename':media_id+'.'+MIMES[row['mime_type']]}


def admin(db,method,path,body):
    if method=='GET' and path=='/api/admin/media':
        return {'media':[{'id':r['id'],'filename':r['filename'],'mimeType':r['mime_type'],'audience':r['audience'],'size':r['size'],'created':r['created']} for r in db.execute('SELECT id,filename,mime_type,audience,size,created FROM material_media ORDER BY created DESC')]}
    match=re.fullmatch(r'/api/admin/media/([A-Za-z0-9_-]+)',path)
    if match and method=='GET': return read(db,match[1],admin=True)
    raise APIError(404,'Маршрут не найден.','not_found')
