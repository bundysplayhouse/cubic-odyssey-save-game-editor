"""Folder captures, decoded comparisons, world entities and validated cloning."""
from pathlib import Path
from collections import Counter
import json,os,struct,math,uuid,datetime
import save_schema as schema
from save_transactions import sha,durable,save_manifest

EXCLUDED={'.cubic_editor_history','.editor_data','__pycache__','.git'}

def comparison_path(value,label):
    text=str(value).strip()
    if len(text)>1 and text[0]==text[-1]=='"':text=text[1:-1]
    if not text:raise ValueError(f'Choose a file or folder for {label}.')
    path=Path(text).expanduser().resolve()
    if not path.exists():raise ValueError(f'Comparison input {label} was not found:\n{path}\nChoose an existing save file or folder.')
    if path.is_file() and path.name=='snapshot.json':return path.parent
    if not path.is_file() and not path.is_dir():raise ValueError(f'{label} is not a regular file or directory: {path}')
    return path

def file_comparison_name(a,b):
    """Use one shared key so renamed before/after files form a single comparison."""
    def recognized(path):
        name=path.name
        if path.suffix.lower() in ('.bak','.prev'):name=path.stem
        return next((key for key in schema.REGISTRY if key.casefold()==name.casefold()),None)
    left,right=recognized(a),recognized(b)
    if left and right and left!=right:raise ValueError(f'These are different known save types ({a.name} and {b.name}). Choose before/after copies of the same save file.')
    return left or right or a.name

def import_file(path,storage,name,progress=None):
    raw=path.read_bytes();digest=sha(raw)
    if progress:progress(1,2,'Copying',path.name)
    folder=Path(storage)/('file_'+uuid.uuid4().hex)
    durable(folder/'blobs'/digest,raw)
    if path.read_bytes()!=raw:raise ValueError(f'{path} changed during comparison. Retry using a stable copy.')
    record={'version':1,'source':str(path),'date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input_kind':'file',
            'files':{name:{'sha256':digest,'size':len(raw)}}}
    save_manifest(folder/'snapshot.json',record)
    if progress:progress(2,2,'Verifying',path.name)
    return folder.resolve()

def compare_inputs(api,a,b,storage,progress=None):
    """Accept ordinary saves, ordinary folders, editor snapshots or their manifests."""
    left=comparison_path(a,'A');right=comparison_path(b,'B')
    if left.is_file()!=right.is_file():raise ValueError('Choose two save files, or two folders/snapshots. A file and a folder cannot be paired.')
    if left==right and (left.is_file() or not (left/'snapshot.json').is_file()):
        raise ValueError('A and B point to the same live file or folder. Select separate before/after copies, or capture Snapshot A before changing the game.')
    storage=Path(storage).resolve()
    if left.is_file():
        name=file_comparison_name(left,right)
        sa=import_file(left,storage,name,progress);sb=import_file(right,storage,name,progress)
    else:
        def prepare(path):
            if (path/'snapshot.json').is_file():return path
            return capture(path,storage/('folder_'+uuid.uuid4().hex),progress)
        sa=prepare(left);sb=prepare(right)
    report=compare(api,sa,sb,progress)
    report.update(input_a=str(left),input_b=str(right),input_mode='files' if left.is_file() else 'folders / snapshots')
    return report
def source_files(root):
    root=Path(root).resolve();out={}
    for p in root.rglob('*'):
        if any(part in EXCLUDED for part in p.relative_to(root).parts):continue
        if p.is_symlink():raise ValueError(f'Symlink not supported in capture: {p}')
        if not p.is_file() or p.name.endswith(('.bak','.prev','.undo_swap_tmp')):continue
        if not p.resolve().is_relative_to(root):raise ValueError('Capture path escapes source')
        out[p.relative_to(root).as_posix()]=p
    return out

def capture(root,destination,progress=None):
    root=Path(root).resolve();destination=Path(destination).resolve()
    if destination==root or destination.is_relative_to(root):raise ValueError('Snapshot must be stored outside the save folder')
    if destination.exists():raise ValueError('Choose a new snapshot directory')
    files=source_files(root)
    if not files:raise ValueError('Source folder has no files')
    destination.mkdir(parents=True);record={'version':1,'source':str(root),'date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{}}
    # An incomplete capture has no manifest and cannot be compared.
    for i,(name,p) in enumerate(files.items()):
        raw=p.read_bytes();key=sha(raw);durable(destination/'blobs'/key,raw)
        record['files'][name]={'sha256':key,'size':len(raw)}
        if progress:progress(i+1,len(files)*2,'Capturing',name)
    if set(source_files(root))!=set(files):raise ValueError('Files appeared/disappeared during capture; repeat with the game closed')
    for i,(name,p) in enumerate(files.items()):
        if sha(p.read_bytes())!=record['files'][name]['sha256']:raise ValueError(f'{name} changed during capture; repeat with the game closed')
        if progress:progress(len(files)+i+1,len(files)*2,'Verifying',name)
    save_manifest(destination/'snapshot.json',record);return destination

def load_snapshot(path,progress=None):
    path=Path(path);record=json.loads((path/'snapshot.json').read_text(encoding='utf-8'))
    if record.get('version')!=1 or not isinstance(record.get('files'),dict):raise ValueError('Unsupported snapshot')
    for i,(name,info) in enumerate(record['files'].items()):
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or ':' in name:raise ValueError('Invalid snapshot filename')
        digest=info.get('sha256','')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Invalid blob key')
        raw=(path/'blobs'/digest).read_bytes()
        if len(raw)!=info['size'] or sha(raw)!=digest:raise ValueError(f'Snapshot integrity failed: {name}')
        if progress:progress(i+1,len(record['files']),'Verifying',name)
    return record

def decoded(api,raw):
    if len(raw)>=8 and raw[4:8]==api.MAGIC:return api.unpack_blob(raw),'Game Zstd'
    if raw[:4]==api.MAGIC:
        if api.zstd is None:raise ValueError('Standard Zstd needs the Python zstandard package')
        return api.zstd.ZstdDecompressor().decompress(raw),'Standard Zstd'
    return raw,'Opaque/raw'

def compare(api,a,b,progress=None):
    a=Path(a);b=Path(b);left=load_snapshot(a,progress);right=load_snapshot(b,progress);result=[]
    names=sorted(set(left['files'])|set(right['files']))
    for index,name in enumerate(names):
        if progress:progress(index+1,len(names),'Comparing',name)
        x=left['files'].get(name);y=right['files'].get(name)
        row={'file':name,'status':'Added' if x is None else 'Removed' if y is None else 'Unchanged' if x['sha256']==y['sha256'] else 'Changed',
             'before_bytes':x['size'] if x else 0,'after_bytes':y['size'] if y else 0,'changes':[]}
        if row['status']=='Unchanged':result.append(row);continue
        raw_a=(a/'blobs'/x['sha256']).read_bytes() if x else b'';raw_b=(b/'blobs'/y['sha256']).read_bytes() if y else b''
        try:
            def decode_or_raw(raw):
                try:return decoded(api,raw)
                except Exception as exc:
                    row.setdefault('notes',[]).append('Decode failed; comparing original bytes: '+str(exc));return raw,'Decode failed / raw'
            da,fa=decode_or_raw(raw_a);db,fb=decode_or_raw(raw_b)
            row.update(before_decoded=len(da),after_decoded=len(db),format=fa+' / '+fb)
            before_fields={};after_fields={}
            if name.lower().endswith('.sav'):
                for data,target in [(da,before_fields),(db,after_fields)]:
                    if data:
                        try:
                            records,warnings=schema.fields(api,data,Path(name).name)
                            target.update({r['path']:r for r in records})
                            row.setdefault('notes',[]).extend(warnings[:8])
                        except Exception as exc:row.setdefault('notes',[]).append('Serializer unavailable; byte comparison retained: '+str(exc))
                for path in sorted(set(before_fields)|set(after_fields)):
                    old=before_fields.get(path);new=after_fields.get(path)
                    if old is None or new is None or (old['type'],old['value'],old['length'])!=(new['type'],new['value'],new['length']):
                        r=new or old;row['changes'].append({'kind':'Added object/field' if old is None else 'Removed object/field' if new is None else 'Field','path':path,'name':r['name'],'type':r['type'],'before':old['value'] if old else None,'after':new['value'] if new else None,'offset_a':old['offset'] if old else None,'offset_b':new['offset'] if new else None})
                if da and db:
                    for label,old,new in api.change_rows(Path(name),raw_a,raw_b):
                        if str(label).startswith(('Skill','Vital','Item')):row['changes'].append({'kind':'Semantic','path':label,'before':old,'after':new})
            # Byte evidence is retained even when serializers miss custom payloads.
            ranges=api.diff_ranges(da,db);row['byte_range_count']=len(ranges)
            for lo,hi in ranges[:1000]:
                row['changes'].append({'kind':'Bytes','path':f'{lo:#x}–{hi:#x}','before':da[lo:min(hi,lo+64)].hex(),'after':db[lo:min(hi,lo+64)].hex()})
                start=(lo//4)*4
                if start+4<=min(len(da),len(db)):
                    ai,bi=struct.unpack_from('<I',da,start)[0],struct.unpack_from('<I',db,start)[0]
                    af,bf=struct.unpack_from('<f',da,start)[0],struct.unpack_from('<f',db,start)[0]
                    row['changes'].append({'kind':'Numeric candidate (unproven)','path':hex(start),'before':f'uint={ai}; float={af}' if math.isfinite(af) else f'uint={ai}','after':f'uint={bi}; float={bf}' if math.isfinite(bf) else f'uint={bi}'})
            sa=Counter(api.strings(da));sb=Counter(api.strings(db))
            for string,n in list((sb-sa).items())[:300]:row['changes'].append({'kind':'Added string candidate','path':str(n),'before':None,'after':string[:1000]})
            for string,n in list((sa-sb).items())[:300]:row['changes'].append({'kind':'Removed string candidate','path':str(n),'before':string[:1000],'after':None})
            row['total_changes']=len(row['changes']);row['changes']=row['changes'][:4000]
            if row['total_changes']>4000 or len(ranges)>1000:row.setdefault('notes',[]).append('Report display bounded; original complete files remain in snapshots')
        except Exception as exc:row['error']=str(exc)
        result.append(row)
    return {'version':1,'snapshot_a':str(a),'snapshot_b':str(b),'source_a':left['source'],'source_b':right['source'],'files':result,'note':'Array paths are positional. Added/removed fields are structural evidence, not proof of persistent object identity. Opaque file semantics and numeric/string candidates are unproven.'}

def entities(api,data):
    api.validate_world_save_envelope(data)
    top,_=api._parse_fields(data,6,struct.unpack_from('<H',data,4)[0],len(data))
    array=next((r for r in top if r[1]==4 and r[2]==23),None)
    if array is None:return []
    _,objects=api._parse_type23(data,array[0]);items=api.world_item_records(data);result=[]
    for i,obj in enumerate(objects):
        fs={f[1]:f for f in obj[4]};kind=f'Tag {obj[2]}';ident='';position=''
        f=fs.get(8)
        if f and f[2]==12:kind=api._decode_type12_string(data,f) or kind
        f=fs.get(1)
        if f and f[2] in (4,8) and f[3]==4:ident=str(struct.unpack_from('<I',data,f[4])[0])
        for fid in (3,2):
            f=fs.get(fid)
            if f and f[2]==16 and f[3]==12:position=', '.join(f'{x:.3f}' for x in struct.unpack_from('<fff',data,f[4]));break
        owned=[r for r in items if obj[0]<=r['offset']<obj[1]]
        text=kind.casefold();category=next((label for token,label in [('chest','Chest'),('portal','Portal'),('barrier','Barrier'),('npc','NPC'),('deploy','Deployable')] if token in text),'Inventory owner' if owned else 'Other / unclassified')
        result.append({'index':i,'id':ident,'kind':kind,'category':category,'position':position,'offset':obj[0],'items':owned})
    return result

def clone_slot(api,source,parent,progress=None):
    source=Path(source).resolve();parent=Path(parent).resolve()
    if not (source/'93_client_state.sav').is_file():raise ValueError('Select a complete numbered slot')
    if parent==source or parent.is_relative_to(source):raise ValueError('Clone destination cannot be inside the source slot')
    parent.mkdir(parents=True,exist_ok=True)
    number=next(i for i in range(10000) if not (parent/str(i)).exists());target=parent/str(number)
    stage=parent/('.clone-'+uuid.uuid4().hex);stage.mkdir()
    files=source_files(source)
    for i,(name,path) in enumerate(files.items()):
        raw=path.read_bytes()
        if path.suffix=='.sav':
            status,detail=schema.health(api,path,raw)
            if status=='Failed':raise ValueError(f'{name}: {detail}')
        durable(stage/name,raw)
        if progress:progress(i+1,len(files)*2,'Copying',name)
    for i,(name,path) in enumerate(files.items()):
        if sha(path.read_bytes())!=sha((stage/name).read_bytes()):raise ValueError('Source changed during clone; incomplete hidden copy retained')
        if progress:progress(len(files)+i+1,len(files)*2,'Verifying',name)
    if set(source_files(source))!=set(files):raise ValueError('Source file list changed during clone')
    if target.exists():raise ValueError('Destination slot was claimed during copy')
    os.rename(stage,target)
    return target

def add_from_template(api,data,header,identifier,quantity,catalog):
    record=api._inventory_record_by_header(data,header);old=record[0]
    source=catalog.get(old,{});target=catalog.get(identifier,{})
    if not source.get('type') or target.get('type')!=source['type']:raise ValueError('Choose a config with the same known item class as the template')
    if not 1<=quantity<=4294967295:raise ValueError('Quantity outside uint32 range')
    path,owner,count,elements,element=api.owner_array_for_offset(data,header)
    # Only a simple item record is allowed; nested mods/state must not be copied blindly.
    for field in element[4]:
        if field[2] in (21,22):raise ValueError('Template has nested state; use a simple item without mods')
        if field[2]==23 and api._parse_type23(data,field[0])[0]!=0:raise ValueError('Template has installed mods/nested items; choose an unmodified template')
    location=api.inventory_record_location(data,header)
    if location not in ('Player inventory','Ship inventory','Other inventory'):raise ValueError('Select a cargo inventory template, not equipment or quickslots')
    result,_,_,delta=api.duplicate_serialized_item(data,header);new_header=header+delta
    result,_,_=api.replace_identifier_structural(result,new_header,old,identifier)
    new_record=api._inventory_record_by_header(result,new_header);buf=bytearray(result)
    struct.pack_into('<I',buf,new_record[3][3][1],quantity)
    # Keep the validated template's condition: config durability is not necessarily its saved unit.
    api.validate_serialized_save(bytes(buf));return bytes(buf)
