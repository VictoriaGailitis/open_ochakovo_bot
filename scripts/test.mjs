import { existsSync, readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const tests=['src','src/games','src/community','src/referrals'].flatMap(dir=>readdirSync(dir).filter(name=>name.endsWith('.test.ts')).sort().map(name=>dir+'/'+name));
const python=process.env.PYTHON??(existsSync('.venv/bin/python')?'.venv/bin/python':'python3');
for(const [command,args] of [[python,['-m','unittest','discover','-s','server/tests','-v']],[python,['manage.py','test','backoffice','--noinput']],[process.execPath,['node_modules/tsx/dist/cli.mjs','--test',...tests]]]){
 const result=spawnSync(command,args,{stdio:'inherit',env:process.env});
 if(result.status!==0)process.exit(result.status??1);
}
