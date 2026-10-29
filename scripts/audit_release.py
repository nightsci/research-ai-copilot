"""扫描部署候选及 Git 历史；只输出路径和状态，不输出匹配内容。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','venv','__pycache__','.pytest_cache','artifacts'}
PATTERNS=[rb'\bsk-[A-Za-z0-9_-]{20,}',rb'\bgh[pousr]_[A-Za-z0-9]{30,}',
          rb'\bgithub_pat_[A-Za-z0-9_]{30,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
          rb'\bAKIA[A-Z0-9]{16}\b']


def git(*args):
    return subprocess.run(['git','-C',str(ROOT),*args],capture_output=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--known-secrets-env',type=Path,help='可选，读取外部 .env 仅作内存匹配；不复制或输出值')
    args=parser.parse_args()
    secrets=[]
    if args.known_secrets_env:
        secrets=[v.encode() for k,v in dotenv_values(args.known_secrets_env).items()
                 if v and len(v)>=8 and re.search(r'(?:API_KEY|SECRET|TOKEN|PASSWORD)$', k.upper())]
    def sensitive(data):
        return any(re.search(p,data) for p in PATTERNS) or any(s in data for s in secrets)
    paths=[];issues=[];manifest=[]
    for p in ROOT.rglob('*'):
        rel=p.relative_to(ROOT)
        if not p.is_file() or any(part in EXCLUDED for part in rel.parts): continue
        paths.append(rel.as_posix())
        if p.name=='.env' or p.name=='secrets.toml' or p.suffix.lower() in ('.pdf','.pem','.key','.docx','.xlsx','.csv'):
            issues.append({'path':rel.as_posix(),'reason':'forbidden_file'})
        data=p.read_bytes()
        if sensitive(data):issues.append({'path':rel.as_posix(),'reason':'credential_pattern_or_known_secret'})
        manifest.append({'file':rel.as_posix(),'sha256':hashlib.sha256(data).hexdigest()})
    has_git=git('rev-parse','--show-toplevel').returncode==0
    history='not_applicable_no_git_repository'
    if has_git:
        for name in git('ls-files','-z').stdout.decode().split('\0'):
            if name and (Path(name).name in ('.env','secrets.toml') or Path(name).suffix.lower()=='.pdf'):
                issues.append({'path':name,'reason':'forbidden_tracked_file'})
        revisions=git('rev-list','--objects','--all').stdout.decode().splitlines()
        for entry in revisions:
            oid=entry.split(' ',1)[0]
            if git('cat-file','-t',oid).stdout.strip()==b'blob' and sensitive(git('cat-file','blob',oid).stdout):
                issues.append({'object':oid,'reason':'credential_in_history'})
        history='scanned_reachable_git_blobs'
    report={'candidate_file_count':len(paths),'git_history':history,'issues':issues,
            'limitations':'Pattern and known-value checks cannot guarantee absence of every possible credential; excluded local artifacts are not upload candidates.'}
    out=ROOT/'artifacts';out.mkdir(exist_ok=True)
    (out/'security-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (out/'upload-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
