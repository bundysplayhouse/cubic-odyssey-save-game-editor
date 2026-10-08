"""Read/validation registry. Writer bindings are explicit, never inferred from notes."""
from dataclasses import dataclass
from pathlib import Path
import math,struct

@dataclass(frozen=True)
class Field:
    name:str
    type:int
    decoder:str
    validation:str='serializer framing'
    editable:bool=False

@dataclass(frozen=True)
class Schema:
    name:str
    validator:str
    names:dict

REGISTRY={
 '93_client_state.sav':Schema('Player / inventory / ships','validate_serialized_save',{6:'Player'}),
 '93_meta.sav':Schema('Slot metadata','parse_slot_meta',{1:'Playtime seconds',12:'Character name',13:'Character level snapshot',21:'Location'}),
 '93_stats.sav':Schema('Global account stats','parse_player_stats',{1:'Characters',6:'Deleted characters',7:'Miner level',8:'Crafter level',9:'Pilot level',10:'Knight level'}),
 '93_quests.sav':Schema('Generated quests','validate_serialized_save',{}),
 '93_blueprints.sav':Schema('Player blueprint collection','parse_player_blueprints',{}),
 '93_economy.sav':Schema('Economy collection (currency not mapped)','validate_serialized_save',{}),
}
# Declarative top-level definitions. Nested semantic bindings use proven parser
# offsets below, rather than duplicating those parsers' structural assumptions.
for filename,spec in list(REGISTRY.items()):
    definitions={}
    for fid,name in spec.names.items():
        typ=22 if filename=='93_client_state.sav' else 10 if filename=='93_meta.sav' and fid==1 else 32 if filename=='93_meta.sav' and fid==12 else 13 if filename=='93_meta.sav' and fid==21 else 4
        definitions[fid]=Field(name,typ,{4:'uint32',10:'float32',13:'counted_utf8',32:'counted_utf16',22:'object'}[typ])
    REGISTRY[filename]=Schema(spec.name,spec.validator,definitions)

def fields(api,data,filename=''):
    """Stable structural paths, types, offsets and values; array indices are positional."""
    records=[];warnings=[];schema=REGISTRY.get(filename)
    def walk(fs,prefix=''):
        seen=set()
        for off,fid,typ,length,start,end in fs:
            path=f'{prefix}/{fid}';definition=schema.names.get(fid) if schema and not prefix else None
            name=definition.name if definition else ''
            if definition and definition.type!=typ:warnings.append(f'Unexpected type for {name}: {typ}, expected {definition.type}')
            if fid in seen:warnings.append(f'Duplicate field ID at {path}')
            seen.add(fid);payload=data[start:end]
            value=f'{length} bytes';row={'path':path,'name':name,'type':typ,'offset':start,'length':length,'value':value}
            records.append(row)
            if len(records)>200000:raise ValueError('Field count exceeds inspection limit')
            if typ==4 and length==4:row['value']=struct.unpack_from('<I',data,start)[0]
            elif typ==8 and length==4:row['value']=struct.unpack_from('<I',data,start)[0]
            elif typ==10 and length==4:row['value']=struct.unpack_from('<f',data,start)[0]
            elif typ==16 and length==12:row['value']=struct.unpack_from('<fff',data,start)
            elif typ==12:
                try:row['value']=api._decode_type12_string(data,(off,fid,typ,length,start,end))
                except Exception:row['value']=repr(payload[:300])
            elif typ in (13,32):
                try:row['value']=(api._decode_counted_utf8 if typ==13 else api._decode_counted_utf16)(payload)
                except Exception:row['value']=repr(payload[:300])
            elif typ==6 and length==1:row['value']=payload[0]
            elif typ==21:
                try:_,children=api._parse_type21(data,off)
                except Exception:warnings.append(f'Custom/unmapped object at {path}');continue
                walk(children,path)
            elif typ==22:
                tag,_,children=api._parse_type22(data,off);row['value']=f'Object tag {tag}';walk(children,path)
            elif typ==23:
                count,elements=api._parse_type23(data,off);row['value']=f'Array count {count}'
                for i,el in enumerate(elements):
                    records.append({'path':f'{path}[{i}]','name':'Object','type':'object','offset':el[0],'length':el[1]-el[0],'value':str(el[2])})
                    walk(el[4],f'{path}[{i}]')
            else:row['value']=payload[:64].hex()+('…' if length>64 else '')
    top,end=api._parse_fields(data,6,struct.unpack_from('<H',data,4)[0],len(data))
    if end!=len(data):raise ValueError('Trailing bytes outside serializer tree')
    walk(top)
    # Bind known semantic names to the same byte offsets used by proven writers.
    if filename=='93_client_state.sav':
        bindings={}
        try:
            values,offsets,mirror=api.parse_character_skills(data)
            for name,(lo,po) in offsets.items():
                bindings[lo]=(f'Skill {name} level','skill',name,'level')
                bindings[po]=(f'Skill {name} progress','skill',name,'progress')
            bindings[mirror]=('Character runtime level','','','')
        except Exception:pass
        try:
            values,offsets=api.parse_player_vitals(data)
            for name,offset in offsets.items():bindings[offset]=(f'Vital {name}','vital',name,'')
        except Exception:pass
        for row in records:
            if row['offset'] in bindings:
                label,kind,name,part=bindings[row['offset']];row.update(name=label,binding=(kind,name,part) if kind else None)
    return records,warnings

def health(api,path,raw):
    path=Path(path)
    try:
        if path.suffix.lower()=='.cfg':api.validate_item_config(api.decode_config(raw));return 'Healthy','ItemCfg syntax validated'
        if len(raw)>=8 and raw[4:8]==api.MAGIC:data=api.unpack_blob(raw)
        elif path.suffix.lower()=='.sav':raise ValueError('Missing supported Zstd header')
        else:return 'Warning','Opaque file: byte integrity only; format not mapped'
        if path.suffix.lower()!='.sav':return 'Warning',f'Zstd / decoded size valid ({len(data)} bytes); payload format not mapped'
        schema=REGISTRY.get(path.name)
        if schema:getattr(api,schema.validator)(data)
        else:api.validate_world_save_envelope(data)
        rows,warnings=fields(api,data,path.name)
        for row in rows:
            if row['type']==10 and not math.isfinite(row['value']):warnings.append(f'Non-finite float at {row["path"]}')
        for ident,*_ in api.item_records(data):
            if not ident or any(ord(c)<32 for c in ident):warnings.append('Empty or broken inventory identifier')
        if path.name=='93_client_state.sav':
            skills=api.parse_character_skills(data)[0];vitals=api.parse_player_vitals(data)[0]
            for name,(level,progress) in skills.items():
                if not 1<=level<=api.SKILL_LEVEL_CAP or not 0<=progress<1:warnings.append(f'Unusual {name} level/progress')
            for name in ('stamina','shield'):
                if vitals[name]<0 or vitals[name]>vitals[name+'_max']:warnings.append(f'{name} outside saved maximum; may reflect runtime effects')
        if warnings:return 'Warning','; '.join(warnings[:8])
        if not schema:return 'Warning',f'Framing valid; {len(rows)} fields; full semantics not mapped'
        return 'Healthy',f'{schema.name}: {len(data)} decoded bytes, {len(rows)} fields validated'
    except Exception as exc:return 'Failed',str(exc)

def write_known(api,data,row,value):
    binding=row.get('binding')
    if not binding:raise ValueError('No validated writer binding for this field')
    kind,name,part=binding
    if kind=='skill':
        old=api.parse_character_skills(data)[0][name]
        change=(int(value),old[1]) if part=='level' else (old[0],float(value))
        return api.set_character_skills(data,{name:change})
    if kind=='vital':return api.set_player_vitals(data,{name:float(value)})
    raise ValueError('Unsupported binding')
