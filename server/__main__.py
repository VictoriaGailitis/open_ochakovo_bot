import argparse
import os
from pathlib import Path
from .app import create_server, ROOT

def main():
    parser=argparse.ArgumentParser(description='Ochakovo VK Mini App API')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=3001)
    parser.add_argument('--db',default=str(ROOT/'.data/ochakovo.sqlite3'))
    args=parser.parse_args()
    config=dict(os.environ)
    # Existing ignored local credential is reused without ever printing it.
    token_path=ROOT/'.data/admin-token'
    if not config.get('ADMIN_TOKEN') and token_path.is_file(): config['ADMIN_TOKEN']=token_path.read_text().strip()
    if not config.get('ADMIN_TOKEN'):
        import secrets
        token_path.parent.mkdir(parents=True,exist_ok=True)
        token_path.write_text(secrets.token_urlsafe(32)+'\n')
        token_path.chmod(0o600)
        config['ADMIN_TOKEN']=token_path.read_text().strip()
    server=create_server(args.host,args.port,args.db,config)
    print(f'Ochakovo API http://{args.host}:{server.server_port} | DEV_AUTH={config.get("DEV_AUTH")=="1"}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__': main()
