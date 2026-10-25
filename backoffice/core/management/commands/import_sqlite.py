"""Explicit one-way import of the retired prototype; source is opened read-only."""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction
from server.legacy_columns import LEGACY_COLUMNS


class Command(BaseCommand):
    help='Импортировать данные SQLite-прототипа в пустые PostgreSQL-таблицы с резервной копией.'

    def add_arguments(self,parser):
        parser.add_argument('--source',required=True)
        parser.add_argument('--dry-run',action='store_true')
        parser.add_argument('--backup-dir',default='.data/migration-backups')

    def handle(self,*args,**options):
        if connection.vendor!='postgresql':raise CommandError('Целевая БД должна быть PostgreSQL.')
        source=Path(options['source']).resolve()
        if not source.is_file():raise CommandError('Исходная SQLite-база не найдена.')
        db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        db.row_factory=sqlite3.Row
        try:
            db.execute('BEGIN')
            available={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing=set(LEGACY_COLUMNS)-available
            if missing:raise CommandError('Сначала обновите исходную схему прототипа; отсутствуют: '+', '.join(sorted(missing)))
            for table,columns in LEGACY_COLUMNS.items():
                actual={row['name'] for row in db.execute('PRAGMA table_info("'+table+'")')}
                if set(columns)-actual:
                    raise CommandError('Несовместимая исходная схема '+table+': отсутствуют обязательные столбцы. Импорт отменён.')
            if db.execute('PRAGMA foreign_key_check').fetchone():raise CommandError('Исходная база содержит нарушенные внешние ключи; импорт отменён.')
            models={model._meta.db_table:model for model in apps.get_app_config('core').get_models()}
            counts={table:db.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0] for table in LEGACY_COLUMNS}
            defined_events={row[0] for row in db.execute('SELECT id FROM career_events')}
            referenced_events={row[0] for row in db.execute('SELECT event FROM registrations UNION SELECT event_id FROM event_activities') if row[0]}
            archived_events=referenced_events-defined_events
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('ochakovo:sqlite-import',0))")
                    for table in LEGACY_COLUMNS:
                        cursor.execute('SELECT COUNT(*) FROM '+connection.ops.quote_name(table))
                        if cursor.fetchone()[0]:raise CommandError('Таблица '+table+' уже содержит данные. Импорт не перезаписывает PostgreSQL.')
                    if not options['dry_run']:
                        backup_dir=Path(options['backup_dir']);backup_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
                        backup=backup_dir/('sqlite-before-postgresql-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
                        descriptor=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                        os.close(descriptor)
                        # backup() includes committed WAL data and yields a consistent source snapshot.
                        with sqlite3.connect(backup) as snapshot:db.backup(snapshot)
                        backup.chmod(0o600)
                        checksum=backup.with_suffix('.sha256')
                        descriptor=os.open(checksum,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                        with os.fdopen(descriptor,'w') as output:output.write(hashlib.sha256(backup.read_bytes()).hexdigest()+'\n')
                    cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                    for table,columns in LEGACY_COLUMNS.items():
                        quoted=','.join(connection.ops.quote_name(c) for c in columns)
                        placeholders=','.join(['%s']*len(columns))
                        rows=db.execute('SELECT '+quoted+' FROM "'+table+'"').fetchall()
                        if rows:
                            cursor.executemany('INSERT INTO '+connection.ops.quote_name(table)+' ('+quoted+') VALUES ('+placeholders+')',[tuple(row) for row in rows])
                        cursor.execute('SELECT COUNT(*) FROM '+connection.ops.quote_name(table))
                        if cursor.fetchone()[0]!=counts[table]:raise CommandError('Проверка количества строк не прошла: '+table)
                    # Earlier prototypes used logical event references without an FK.
                    # Preserve those IDs and registrations as unpublished archival
                    # definitions rather than dropping history or disabling the FK.
                    for event_id in sorted(archived_events):
                        definition={'id':event_id,'title':'Архивное мероприятие','description':'Историческая ссылка из прототипа. Первоначальное описание не сохранилось.','missingDefinition':True}
                        cursor.execute('INSERT INTO career_events(id,definition,audience,published) VALUES(%s,%s,%s,0)',(event_id,json.dumps(definition,ensure_ascii=False),'candidate'))
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
                    for statement in connection.ops.sequence_reset_sql(no_style(),list(models.values())):cursor.execute(statement)
                    if options['dry_run']:transaction.set_rollback(True)
            self.stdout.write(json.dumps({'dryRun':options['dry_run'],'sourceUnchanged':True,'tables':counts,'totalRows':sum(counts.values()),'restoredArchivedEventDefinitions':len(archived_events)},ensure_ascii=False))
        except sqlite3.Error as error:raise CommandError('Не удалось прочитать исходную SQLite-базу; PostgreSQL не изменён.') from error
        finally:db.close()
