import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { setTimeout } from "node:timers/promises";

const python=process.env.PYTHON ?? (existsSync('.venv/bin/python')?'.venv/bin/python':'python3');
const env={...process.env,DEV_AUTH:process.env.DEV_AUTH??'1',DJANGO_DEBUG:process.env.DJANGO_DEBUG??'1',ALLOWED_ORIGINS:[process.env.ALLOWED_ORIGINS,'http://127.0.0.1:5188','http://localhost:5188'].filter(Boolean).join(',')};
const prepare=spawnSync(python,['scripts/prepare_dev.py'],{stdio:'inherit',env});
if(prepare.status!==0)process.exit(prepare.status??1);
const api=spawn(python,['-m','server','--host','127.0.0.1','--port','3001'],{stdio:'inherit',env});
let stopping=false,frontend;
function stop(code=0){if(stopping)return;stopping=true;frontend?.kill('SIGTERM');api.kill('SIGTERM');process.exitCode=code;}
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
api.on('exit',code=>stop(code??1));api.on('error',()=>stop(1));
let ready=false;
for(let attempt=0;attempt<60&&!stopping;attempt++){
  try{if((await fetch('http://127.0.0.1:3001/api/health')).ok){ready=true;break;}}catch{}
  await setTimeout(150);
}
if(!ready){stop(1);}
else if(!stopping){frontend=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1'],{stdio:'inherit'});frontend.on('exit',code=>stop(code??1));frontend.on('error',()=>stop(1));}
