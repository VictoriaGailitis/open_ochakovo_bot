"""PostgreSQL transaction boundary for the existing parameterized domain services.

Django owns connections and migrations. This adapter preserves the small execute /
row interface used by the domain; it never creates a SQLite database or schema.
"""
import re
from contextlib import contextmanager

from django.db import connection as django_connection, transaction as django_transaction
from .legacy_columns import LEGACY_COLUMNS


class Record(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, rows=(), rowcount=0):
        self.rows=list(rows)
        self.rowcount=rowcount
        self.position=0

    def fetchone(self):
        if self.position >= len(self.rows): return None
        row=self.rows[self.position];self.position+=1;return row

    def fetchall(self):
        result=self.rows[self.position:];self.position=len(self.rows);return result

    def __iter__(self): return iter(self.fetchall())


def translate(sql):
    """Translate only the legacy parameter / insert syntax, never data values."""
    sql=sql.strip().rstrip(';')
    ignore=bool(re.match(r'INSERT\s+OR\s+IGNORE\b',sql,re.I))
    if ignore: sql=re.sub(r'^INSERT\s+OR\s+IGNORE\b','INSERT',sql,flags=re.I)
    # New ORM surrogate keys must not shift positional legacy INSERT values.
    match=re.match(r'INSERT\s+INTO\s+(\w+)\s+VALUES\b',sql,re.I)
    if match and match[1] in LEGACY_COLUMNS:
        columns=','.join('"'+column+'"' for column in LEGACY_COLUMNS[match[1]])
        sql=sql[:match.end(1)]+' ('+columns+')'+sql[match.end(1):]
    if ignore: sql+=' ON CONFLICT DO NOTHING'
    sql=re.sub(r'\browid\b','id',sql,flags=re.I)
    result=[];quote=None;i=0
    while i<len(sql):
        char=sql[i]
        if char in ("'",'"'):
            if quote==char:
                if i+1<len(sql) and sql[i+1]==char:
                    result.extend((char,char));i+=2;continue
                quote=None
            elif quote is None:quote=char
        if char=='?' and quote is None:result.append('%s')
        elif char=='%':result.append('%%')
        else:result.append(char)
        i+=1
    return ''.join(result)


class Connection:
    is_postgres=True

    def execute(self, sql, params=()):
        with django_connection.cursor() as cursor:
            cursor.execute(translate(sql),tuple(params))
            rows=[Record(zip((c[0] for c in cursor.description),row)) for row in cursor.fetchall()] if cursor.description else []
            return Result(rows,cursor.rowcount)

    def close(self):
        # Django's request lifecycle owns the connection; do not close outer atomics.
        pass

    def lock(self, namespace, identifier):
        self.execute('SELECT pg_advisory_xact_lock(hashtextextended(?,0))',(namespace+':'+str(identifier),))


def connect():
    if django_connection.vendor!='postgresql':
        raise RuntimeError('The runtime database must be PostgreSQL.')
    return Connection()


@contextmanager
def transaction():
    with django_transaction.atomic():
        yield connect()


def runtime_store():
    # Import lazily so historical domain tests can still import their SQLite oracle.
    from .app import Store as LegacyDataHelpers, CATALOG
    from . import community

    class PostgreSQLStore(LegacyDataHelpers):
        def __init__(self): self.path='postgresql'
        def connect(self):return connect()
        def transaction(self):return transaction()

        @staticmethod
        def catalog(db,uid=None):
            from .catalog_store import catalog
            result=catalog(db)
            result['events']=community.events(db,community.is_staff(db,uid))
            for event in result['events']:
                count=db.execute("SELECT COUNT(*) FROM registrations WHERE event=? AND status='registered'",(event['id'],)).fetchone()[0]
                event['remaining']=max(0,event['capacity']-count)
                event['activities']=[LegacyDataHelpers.activity(row) for row in db.execute('SELECT * FROM event_activities WHERE event_id=? ORDER BY id',(event['id'],))]
            for reward in result['rewards']:
                count=db.execute('SELECT COUNT(*) FROM exchanges WHERE reward=?',(reward['id'],)).fetchone()[0]
                reward['remaining']=max(0,reward['stock']-count)
            return result
    return PostgreSQLStore()
