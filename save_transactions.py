"""Durable write-ahead journals and conservative interrupted-batch recovery."""
from pathlib import Path
import os,json,uuid,hashlib,datetime

def sha(data):return hashlib.sha256(data).hexdigest()
def durable(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
def atomic(path,data):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        durable(temp,data)
        if os.name=='nt':
            import ctypes
            move=ctypes.WinDLL('kernel32',use_last_error=True).MoveFileExW
            move.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_ulong];move.restype=ctypes.c_int
            if not move(str(temp.resolve()),str(path.resolve()),0x9):raise ctypes.WinError(ctypes.get_last_error())
        else:os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
def save_manifest(path,record):atomic(path,json.dumps(record,indent=2,ensure_ascii=False).encode('utf-8'))
def pending(root):
    result=[]
    for path in Path(root).glob('*/journal.json'):
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('status') not in ('complete','rolled_back'):result.append(path)
        except Exception:result.append(path)
    return result

def recover(manifest):
    manifest=Path(manifest);record=json.loads(manifest.read_text(encoding='utf-8'));prepared=[]
    if record.get('version')!=1:raise ValueError('Unsupported journal version')
    for i,entry in enumerate(record['files']):
        path=Path(entry['path'])
        if not path.is_absolute() or path.suffix.lower() not in ('.sav','.cfg'):raise ValueError('Invalid journal target')
        before=(manifest.parent/f'{i}.before').read_bytes()
        if sha(before)!=entry['before']:raise ValueError('Journal original failed integrity check')
        current=path.read_bytes()
        if sha(current) not in (entry['before'],entry['after']):raise ValueError(f'Outside changes at {path}; automatic recovery refused')
        prepared.append((path,before))
    record['status']='recovering';save_manifest(manifest,record)
    for path,before in prepared:
        atomic(path,before)
        if path.read_bytes()!=before:raise OSError(f'Recovery verification failed: {path}')
    record['status']='rolled_back';save_manifest(manifest,record)
    return len(prepared)

def apply(entries,root,validate,changes):
    if not entries:return 0
    if pending(root):raise ValueError('Resolve interrupted transactions on Save Health before applying another batch')
    for key,entry in entries.items():
        if Path(key).read_bytes()!=entry['before']:raise ValueError(f'Outside changes detected: {key}')
        status,detail=validate(Path(key),entry['after'])
        if status=='Failed':raise ValueError(f'{key}: {detail}')
    token=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:8]
    folder=Path(root)/token;folder.mkdir(parents=True)
    record={'version':1,'status':'preparing','date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[]}
    manifest=folder/'journal.json'
    for i,(key,entry) in enumerate(entries.items()):
        durable(folder/f'{i}.before',entry['before'])
        record['files'].append({'path':str(Path(key).resolve()),'before':sha(entry['before']),'after':sha(entry['after']),'replaced':False})
    record['status']='prepared';save_manifest(manifest,record)
    try:
        for i,(key,entry) in enumerate(entries.items()):
            path=Path(key)
            if path.read_bytes()!=entry['before']:raise ValueError(f'File changed during transaction: {path}')
            history=path.parent/'.cubic_editor_history';history.mkdir(exist_ok=True)
            blob=f'{token}_{i}.bin';durable(history/blob,entry['before'])
            save_manifest(history/f'{token}_{i}.json',{'version':1,'file':path.name,'date':record['date'],'blob':blob,'sha256':sha(entry['before']),'changes':changes(path,entry['before'],entry['after'])})
            bak=Path(key+'.bak')
            if not bak.exists():durable(bak,entry['before'])
            atomic(Path(key+'.prev'),entry['before'])
            record['status']='replacing';save_manifest(manifest,record)
            # Recovery recognizes both hashes even if power fails before the marker.
            atomic(path,entry['after'])
            if sha(path.read_bytes())!=record['files'][i]['after']:raise OSError('Replacement verification failed')
            record['files'][i]['replaced']=True;save_manifest(manifest,record)
        record['status']='complete';save_manifest(manifest,record)
    except Exception as exc:
        try:recover(manifest)
        except Exception as recovery_error:raise RuntimeError(f'Batch interrupted: {exc}. Recovery required: {recovery_error}. Journal: {manifest}') from exc
        raise
    return len(entries)
