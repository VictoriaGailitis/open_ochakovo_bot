"""Create local-only PostgreSQL credentials and start the named Docker database."""
import os,secrets,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
os.chdir(ROOT)
(ROOT/'.data').mkdir(exist_ok=True)
path=ROOT/'.data/postgres.env'
if not path.exists():
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write('POSTGRES_DB=ochakovo\nPOSTGRES_USER=ochakovo\nPOSTGRES_PASSWORD='+secrets.token_urlsafe(32)+'\n')
values=dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line)
if not (ROOT/'.env').exists():
    fd=os.open(ROOT/'.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write('DATABASE_URL=postgresql://ochakovo:'+values['POSTGRES_PASSWORD']+'@127.0.0.1:55432/ochakovo\nDEV_AUTH=1\nDJANGO_DEBUG=1\nDJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver\n')
try:
    existing=subprocess.run(['docker','inspect','--format','{{.State.Running}}','open_ochakovo_postgres'],capture_output=True,text=True)
    if existing.returncode:subprocess.run(['docker','run','-d','--name','open_ochakovo_postgres','--env-file',str(path),'-p','127.0.0.1:55432:5432','-v','open_ochakovo_pgdata:/var/lib/postgresql/data','postgres:16-alpine'],check=True,stdout=subprocess.DEVNULL)
    elif existing.stdout.strip()!='true':subprocess.run(['docker','start','open_ochakovo_postgres'],check=True,stdout=subprocess.DEVNULL)
    for attempt in range(40):
        if subprocess.run(['docker','exec','open_ochakovo_postgres','pg_isready','-U','ochakovo','-d','ochakovo'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
        time.sleep(.25)
    else:raise RuntimeError('PostgreSQL не успел запуститься.')
except (OSError,subprocess.CalledProcessError,RuntimeError) as error:
    raise SystemExit('Запустите Docker и повторите setup-local.py. Существующие данные и настройки не удалены.') from error
print('PostgreSQL готов на 127.0.0.1:55432. Секреты только в игнорируемых .env и .data/postgres.env.')
