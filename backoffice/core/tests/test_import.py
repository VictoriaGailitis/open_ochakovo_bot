"""Real PostgreSQL import tests; SQLite is used solely as the retired source."""
import hashlib
import io
import sqlite3
import tempfile
from pathlib import Path
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from backoffice.core.models import MiniUser,LedgerEntry,CareerEvent,EventRegistration,EventActivity
from server.app import Store as SQLitePrototype


class ImportTest(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'source.sqlite3';self.backups=Path(self.temp.name)/'backups'
        self.source=SQLitePrototype(self.path)
        with self.source.transaction() as db:
            db.execute("INSERT INTO users(id,profile) VALUES('demo:source',NULL)")
            db.execute("INSERT INTO ledger VALUES('original-ledger','demo:source','task:signal-1',50,'2026-10-25T00:00:00Z')")
            db.execute("INSERT INTO registrations VALUES('original-registration','demo:source','historical-tour','cancelled','2026-10-25T00:00:00Z')")
            self.tokens={r['id']:r['qr_token'] for r in db.execute('SELECT id,qr_token FROM event_activities')}
        self.original=hashlib.sha256(self.path.read_bytes()).hexdigest()
    def run_import(self,**kwargs):
        output=io.StringIO()
        call_command('import_sqlite',source=str(self.path),backup_dir=str(self.backups),stdout=output,**kwargs)
        return output.getvalue()
    def test_import_preserves_identifiers_tokens_awards_and_archives_missing_definitions(self):
        self.run_import()
        self.assertTrue(MiniUser.objects.filter(pk='demo:source').exists())
        self.assertEqual(LedgerEntry.objects.get(pk='original-ledger').delta,50)
        self.assertEqual(EventRegistration.objects.get(pk='original-registration').event_id,'historical-tour')
        self.assertEqual(CareerEvent.objects.get(pk='historical-tour').published,0)
        self.assertEqual(dict(EventActivity.objects.values_list('id','qr_token')),self.tokens)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.original)
        self.assertEqual(len(list(self.backups.glob('*.sqlite3'))),1)
        self.assertEqual(next(self.backups.glob('*.sqlite3')).stat().st_mode&0o777,0o600)
        self.assertEqual(self.backups.stat().st_mode&0o777,0o700)
        self.assertEqual(next(self.backups.glob('*.sha256')).stat().st_mode&0o777,0o600)
    def test_dry_run_rolls_back_and_does_not_write_backup_or_source(self):
        self.run_import(dry_run=True)
        self.assertEqual(MiniUser.objects.count(),0)
        self.assertEqual(CareerEvent.objects.count(),0)
        self.assertFalse(self.backups.exists())
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.original)
    def test_nonempty_postgres_is_rejected_without_overwriting(self):
        MiniUser.objects.create(id='existing')
        with self.assertRaises(CommandError):self.run_import()
        self.assertEqual(list(MiniUser.objects.values_list('id',flat=True)),['existing'])
        self.assertFalse(self.backups.exists())
    def test_broken_legacy_foreign_key_cannot_partially_import(self):
        with sqlite3.connect(self.path) as db:db.execute("INSERT INTO ledger VALUES('broken','missing-user','task:signal-2',50,'2026-10-25T00:00:00Z')")
        with self.assertRaises(CommandError):self.run_import()
        self.assertEqual(MiniUser.objects.count(),0)
        self.assertEqual(LedgerEntry.objects.count(),0)
    def test_missing_source_column_cannot_be_imported_as_quoted_literal(self):
        with sqlite3.connect(self.path) as db:db.execute('ALTER TABLE material_versions DROP COLUMN snapshot')
        with self.assertRaises(CommandError):self.run_import()
        self.assertEqual(MiniUser.objects.count(),0)
        self.assertFalse(self.backups.exists())
