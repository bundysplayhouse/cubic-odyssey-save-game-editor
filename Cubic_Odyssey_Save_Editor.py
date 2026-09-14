#!/usr/bin/env python3
"""
Cubic Odyssey Save Editor / Reverse Engineering Lab v1.20

Focus of this build:
- Controlled save-slot experiments.
- Per-file binary diffs.
- Candidate integer/float changes around each changed byte range.
- String/identifier changes.
- Inventory record inspection.
- Config database lookup.
- Safe editing of proven inventory quantity/durability and currency.
- Structural quickslot move/swap, copy/replace, and clear operations.
- Baseline .bak plus one-step .prev undo backups.
- Global player-stat/class-level inspection and editing.
- Per-slot metadata inspection and safe variable-length display-name editing.
- Global saved-blueprint collection inspection plus built-in blueprint config catalog.
- Player ship/vehicle inspection, component-role mapping, and structurally safe component-ID replacement.
- Per-slot side-quest inspection, raw reward editing, structural quest abandonment, and story-task config mapping.
- Fixed-size world item quantity and condition edits with local validation and recovery copies.

Use copies of saves and disable Steam Cloud while experimenting.
"""

from pathlib import Path
import bisect, math, re, struct, subprocess, shutil, json, tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

try:
    import zstandard as zstd
except ImportError:
    zstd = None

MAGIC=b"\x28\xb5\x2f\xfd"

def dec(p):
    p=Path(p)
    r=p.read_bytes()
    if len(r)<8 or r[4:8]!=MAGIC:
        raise ValueError(f"Not a Cubic Odyssey zstd save: {p.name}")
    expected=struct.unpack_from("<I",r,0)[0]
    if zstd is not None:
        try:
            raw=zstd.ZstdDecompressor().decompress(r[4:])
        except Exception as e:
            raise RuntimeError(f"Zstandard decompression failed for {p.name}: {e}")
    else:
        try:
            q=subprocess.run(["zstd","-d","-q","-c"],input=r[4:],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        except FileNotFoundError:
            raise RuntimeError("Zstandard support is missing. Install it with: py -3.13 -m pip install zstandard")
        if q.returncode:
            raise RuntimeError(q.stderr.decode(errors="replace"))
        raw=q.stdout
    if expected and len(raw)!=expected:
        raise RuntimeError(f"Decoded-size mismatch in {p.name}: header={expected:,}, decoded={len(raw):,}")
    return raw

def enc(d):
    raw=bytes(d)
    if zstd is not None:
        try:
            packed=zstd.ZstdCompressor(level=3).compress(raw)
        except Exception as e:
            raise RuntimeError(f"Zstandard compression failed: {e}")
    else:
        try:
            q=subprocess.run(["zstd","-q","-c","-3","-"],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        except FileNotFoundError:
            raise RuntimeError("Zstandard support is missing. Install it with: py -3.13 -m pip install zstandard")
        if q.returncode:
            raise RuntimeError(q.stderr.decode(errors="replace"))
        packed=q.stdout
    return struct.pack("<I",len(raw))+packed

def write(p,d):
    p=Path(p)
    b=Path(str(p)+".bak")
    prev=Path(str(p)+".prev")
    if not b.exists():
        shutil.copy2(p,b)
    # v1.11 keeps the immediately previous compressed save as well as the
    # original baseline .bak.  This makes a one-step undo possible even after
    # several edits in the same session.
    shutil.copy2(p,prev)
    p.write_bytes(enc(d))

def strings(d):
    return [x.decode("utf8","replace") for x in re.findall(rb"[ -~]{4,}",d)]

def candidates(a,b,lo,hi):
    out=[]
    st=max(0,lo-16); en=min(max(len(a),len(b)),hi+16)
    for off in range(st,en-3,4):
        aa=struct.unpack_from("<I",a+bytes(max(0,off+4-len(a))),off)[0] if off+4<=len(a) else None
        bb=struct.unpack_from("<I",b+bytes(max(0,off+4-len(b))),off)[0] if off+4<=len(b) else None
        if aa!=bb and aa is not None and bb is not None:
            af=struct.unpack_from("<f",a,off)[0]; bf=struct.unpack_from("<f",b,off)[0]
            if abs(af)<1e12 and abs(bf)<1e12:
                out.append((off,aa,bb,af,bf))
    return out

def diff_ranges(a,b):
    n=max(len(a),len(b)); runs=[]; s=None
    for i in range(n):
        x=a[i] if i<len(a) else None; y=b[i] if i<len(b) else None
        if x!=y and s is None:s=i
        if x==y and s is not None:runs.append((s,i));s=None
    if s is not None:runs.append((s,n))
    return runs

def item_records(d):
    out=[]; marker=b"\x06\x00\x0c\x00"; pos=0
    while True:
        h=d.find(marker,pos)
        if h<0:break
        if h+8>len(d):break
        n=struct.unpack_from("<I",d,h+4)[0]
        p=d[h+8:h+8+n]
        try: ident=p[2:].rstrip(b"\0").decode("utf8")
        except: pos=h+4; continue
        # InventoryItem scalar fields are 12 bytes each:
        #   field id (2) + type (2) + payload length (4) + payload (4)
        # The previous v1.3 parser incorrectly treated these as 8-byte fields,
        # which caused the inventory tree to remain empty.
        cur=h; fields={}; ok=True
        # Fields 2-5 are the fixed InventoryItem scalar fields.
        # Field 1 is a variable/nested structure and is NOT contiguous with
        # these fields, so requiring it was the reason v1.5 still showed no
        # items for many saves.
        for fid in range(5,1,-1):
            if cur<12:ok=False;break
            got,typ=struct.unpack_from("<HH",d,cur-12)
            plen=struct.unpack_from("<I",d,cur-8)[0]
            if got!=fid or plen!=4:ok=False;break
            fields[fid]=(typ,cur-4);cur-=12
        if ok and all(fields[x][0] in (4,10,23) for x in range(2,6)):
            vals={}
            for fid,(typ,off) in fields.items():
                if typ==10:
                    vals[fid]=struct.unpack_from("<f",d,off)[0]
                elif typ==4:
                    vals[fid]=struct.unpack_from("<I",d,off)[0]
                else:
                    vals[fid]=struct.unpack_from("<I",d,off)[0]
            out.append((ident,cur,h+8+n,fields,vals))
        pos=h+8+n
    return out

def world_item_records(d):
    """Inspect plausible InventoryItem records without claiming world ownership."""
    rows=[]
    for ident,start,end,fields,values in item_records(d):
        if fields[3][0]!=4 or not ident or len(ident)>256 or end>len(d):
            continue
        if not all(32<=ord(ch)<127 for ch in ident):
            continue
        rows.append({
            'identifier':ident, 'quantity':int(values[3]),
            'condition':values[5], 'condition_type':fields[5][0],
            'offset':start, 'end':end,
            'quantity_offset':fields[3][1],
            'condition_offset':fields[5][1],
        })
    return rows

def world_item_locations(d,rows):
    """Attach the owning world entity's type, ID, and saved position."""
    validate_world_save_envelope(d)
    top,_=_parse_fields(d,6,struct.unpack_from('<H',d,4)[0],len(d))
    entity_array=next((f for f in top if f[1]==4 and f[2]==23),None)
    if entity_array is None:
        for row in rows:
            row['location']='Unknown world object'
        return rows
    _,entities=_parse_type23(d,entity_array[0])
    starts=[entity[0] for entity in entities]
    labels={}
    for row in rows:
        index=bisect.bisect_right(starts,row['offset'])-1
        if index<0 or row['offset']>=entities[index][1]:
            row['location']='Unknown world object'
            continue
        if index not in labels:
            entity=entities[index]
            fields={f[1]:f for f in entity[4]}
            kind=_decode_type12_string(d,fields[8]) if 8 in fields else None
            if not kind:
                kind=f'World entity (tag {entity[2]})'
            id_field=fields.get(1)
            entity_id=(struct.unpack_from('<I',d,id_field[4])[0]
                       if id_field and id_field[2] in (4,8) and id_field[3]==4 else None)
            position=None
            for fid in (3,2):
                field=fields.get(fid)
                if field and field[2]==16 and field[3]==12:
                    xyz=struct.unpack_from('<fff',d,field[4])
                    if all(math.isfinite(x) and abs(x)<1e8 for x in xyz):
                        position=xyz
                        break
            label=kind
            if entity_id is not None:
                label+=f' #{entity_id}'
            if position is not None:
                label+=' @ ('+', '.join(f'{x:.1f}' for x in position)+')'
            labels[index]=label
        row['location']=labels[index]
    return rows

def validate_world_save_envelope(d):
    """Validate the world save's complete top-level field framing."""
    if len(d)<6:
        raise ValueError('World save is too short.')
    count=struct.unpack_from('<H',d,4)[0]
    _,end=_parse_fields(d,6,count,len(d))
    if end!=len(d):
        raise ValueError('World save has trailing bytes outside top-level fields.')
    return True

def set_world_item_scalar(d,record_offset,identifier,field,expected,new_value):
    """Change only one four-byte item scalar after verifying its exact record."""
    validate_world_save_envelope(d)
    matching=[r for r in world_item_records(d)
              if r['offset']==record_offset and r['identifier']==identifier]
    if len(matching)!=1:
        raise ValueError('Selected world item moved or changed. Reload the slot and select it again.')
    row=matching[0]
    if field=='quantity':
        offset=row['quantity_offset']
        old=row['quantity']
        value=int(new_value)
        if value<0 or value>0xffffffff or value!=new_value:
            raise ValueError('Quantity must be a whole number from 0 to 4294967295.')
        replacement=struct.pack('<I',value)
    elif field=='condition':
        if row['condition_type']!=10:
            raise ValueError('This item does not have a 32-bit condition/charge field.')
        offset=row['condition_offset']
        old=row['condition']
        value=float(new_value)
        if not (0.0<=value<=1000000.0):
            raise ValueError('Condition/charge must be between 0 and 1000000.')
        replacement=struct.pack('<f',value)
        value=struct.unpack('<f',replacement)[0]
    else:
        raise ValueError('Unsupported world item field.')
    if old!=expected:
        raise ValueError('Selected world item value changed. Reload the slot and try again.')
    if not (row['offset']<=offset and offset+4<=row['end']):
        raise ValueError('World item scalar is outside its record.')
    changed=d[:offset]+replacement+d[offset+4:]
    if len(changed)!=len(d) or changed[:offset]!=d[:offset] or changed[offset+4:]!=d[offset+4:]:
        raise RuntimeError('World item edit changed bytes outside the selected scalar.')
    validate_world_save_envelope(changed)
    check=[r for r in world_item_records(changed)
           if r['offset']==record_offset and r['identifier']==identifier]
    if len(check)!=1 or check[0][field]!=value:
        raise RuntimeError('World item did not reparse with the requested value.')
    return changed,old,value

def write_world_verified(p,changed,expected_compressed=None):
    """Use the normal backups and verify the compressed file after writing."""
    p=Path(p)
    validate_world_save_envelope(changed)
    original=p.read_bytes()
    if expected_compressed is not None and original!=expected_compressed:
        raise ValueError('World save changed while the edit was open. Reload the slot and try again.')
    try:
        write(p,changed)
        if dec(p)!=changed:
            raise RuntimeError('World save failed the compression round-trip check.')
    except Exception:
        p.write_bytes(original)
        raise

def _parse_fields(d,pos,nfields,end):
    fields=[]
    for _ in range(nfields):
        if pos+8>end:
            raise ValueError("Serialized field header exceeds its container.")
        fid,typ=struct.unpack_from("<HH",d,pos)
        ln=struct.unpack_from("<I",d,pos+4)[0]
        fend=pos+8+ln
        if fend>end:
            raise ValueError("Serialized field payload exceeds its container.")
        fields.append((pos,fid,typ,ln,pos+8,fend))
        pos=fend
    return fields,pos

def _parse_type21(d,h):
    """Parse serializer type 0x15: field-count + fields."""
    fid,typ=struct.unpack_from("<HH",d,h)
    ln=struct.unpack_from("<I",d,h+4)[0]
    if typ!=21:
        raise ValueError("Not a type-0x15 container.")
    ps=h+8; pe=ps+ln
    if ps+2>pe:
        raise ValueError("Truncated type-0x15 container.")
    nfields=struct.unpack_from("<H",d,ps)[0]
    fields,pos=_parse_fields(d,ps+2,nfields,pe)
    if pos!=pe:
        raise ValueError("Type-0x15 container has trailing bytes.")
    return nfields,fields

def _parse_type22(d,h):
    """Parse serializer type 0x16: object tag + field-count + fields."""
    fid,typ=struct.unpack_from("<HH",d,h)
    ln=struct.unpack_from("<I",d,h+4)[0]
    if typ!=22:
        raise ValueError("Not a type-0x16 container.")
    ps=h+8; pe=ps+ln
    if ps+4>pe:
        raise ValueError("Truncated type-0x16 container.")
    tag,nfields=struct.unpack_from("<HH",d,ps)
    fields,pos=_parse_fields(d,ps+4,nfields,pe)
    if pos!=pe:
        raise ValueError("Type-0x16 container has trailing bytes.")
    return tag,nfields,fields

def _parse_type23(d,h):
    """Parse serializer type 0x17: element-count + tagged field objects."""
    fid,typ=struct.unpack_from("<HH",d,h)
    ln=struct.unpack_from("<I",d,h+4)[0]
    if typ!=23:
        raise ValueError("Not a type-0x17 array.")
    ps=h+8; pe=ps+ln
    if ps+4>pe:
        raise ValueError("Truncated type-0x17 array.")
    count=struct.unpack_from("<I",d,ps)[0]
    pos=ps+4; elements=[]
    for _ in range(count):
        if pos+4>pe:
            raise ValueError("Array element header exceeds its container.")
        tag,nfields=struct.unpack_from("<HH",d,pos)
        estart=pos; pos+=4
        fields,pos=_parse_fields(d,pos,nfields,pe)
        elements.append((estart,pos,tag,nfields,fields))
    if pos!=pe:
        raise ValueError("Type-0x17 array has trailing bytes.")
    return count,elements

def validate_serialized_save(d):
    """Validate the known Cubic Odyssey save-container grammar.

    This intentionally treats unknown scalar/blob types as opaque payloads,
    while recursively validating the length-delimited 0x15/0x16/0x17
    structures used around inventory records.
    """
    if len(d)<6:
        raise ValueError("Decoded save is too short.")
    nfields=struct.unpack_from("<H",d,4)[0]
    fields,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError("Top-level save fields do not end at EOF.")

    def walk(field):
        off,fid,typ,ln,ps,pe=field
        if typ==21:
            _,children=_parse_type21(d,off)
            for child in children: walk(child)
        elif typ==22:
            _,_,children=_parse_type22(d,off)
            for child in children: walk(child)
        elif typ==23:
            _,elements=_parse_type23(d,off)
            for element in elements:
                for child in element[4]: walk(child)

    for field in fields:
        walk(field)
    return True

def container_path_for_offset(d,target):
    """Return nested 0x15/0x16/0x17 field headers containing target."""
    nfields=struct.unpack_from("<H",d,4)[0]
    fields,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError("Top-level save structure is invalid.")
    path=[]

    def descend(field_list):
        for field in field_list:
            off,fid,typ,ln,ps,pe=field
            if typ not in (21,22,23) or not (ps<=target<pe):
                continue
            path.append(field)
            if typ==21:
                _,children=_parse_type21(d,off)
                descend(children)
            elif typ==22:
                _,_,children=_parse_type22(d,off)
                descend(children)
            else:
                _,elements=_parse_type23(d,off)
                for element in elements:
                    if element[0]<=target<element[1]:
                        descend(element[4])
                        break
            return True
        return False

    descend(fields)
    return path

def owner_array_for_offset(d,target):
    """Find the innermost serialized array element containing target."""
    path=container_path_for_offset(d,target)
    arrays=[field for field in path if field[2]==23]
    if not arrays:
        raise ValueError("The selected record is not inside a recognized serialized array.")
    owner=arrays[-1]
    count,elements=_parse_type23(d,owner[0])
    element=next((e for e in elements if e[0]<=target<e[1]),None)
    if element is None:
        raise ValueError("Could not resolve the selected array element.")
    return path,owner,count,elements,element

def _decode_type12_string(d,field):
    off,fid,typ,ln,ps,pe=field
    if typ!=12 or ln<3:
        return None
    inner=struct.unpack_from("<H",d,ps)[0]
    payload=d[ps+2:pe]
    if payload.endswith(b"\0"):
        payload=payload[:-1]
    try:
        return payload.decode("utf-8")
    except Exception:
        return None

def inventory_record_location(d,identifier_header):
    """Return a conservative structural label for an InventoryItem record."""
    path=container_path_for_offset(d,identifier_header)
    arrays=[field for field in path if field[2]==23]
    if not arrays:
        return "Unknown"
    owner=arrays[-1]
    if owner[1]==7:
        return "Item mods"

    previous=None
    for field in path:
        if field[0]==owner[0]:
            break
        if field[2]==23:
            previous=field
    if previous is not None:
        _,elements=_parse_type23(d,previous[0])
        parent=next((e for e in elements if e[0]<=identifier_header<e[1]),None)
        if parent is not None:
            for field in parent[4]:
                if field[1]==1 and field[2]==12:
                    label=_decode_type12_string(d,field)
                    if label=="__quickslots":
                        return "Quickslots"
                    if label=="inventory":
                        # Field 14 is the player inventory/quickslot group in
                        # all supplied saves. Inventory arrays nested under the
                        # field-19 PlayerShipCollection path are ship cargo.
                        if any(f[1]==14 and f[2]==21 for f in path):
                            return "Player inventory"
                        if any(f[1]==19 and f[2]==21 for f in path):
                            return "Ship inventory"
                        return "Other inventory"
                    if label:
                        return label
    return "Item array" if owner[1]==4 else f"Array field {owner[1]}"

def replace_identifier_structural(d,identifier_header,old_ident,new_ident):
    """Resize one identifier string and update every enclosing container length."""
    data=bytearray(d)
    oldb=old_ident.encode("utf-8"); newb=new_ident.encode("utf-8")
    h=int(identifier_header)
    if h<0 or h+10+len(oldb)>=len(data):
        raise ValueError("Identifier offset is outside the decoded save.")
    fid,typ=struct.unpack_from("<HH",data,h)
    old_outer=struct.unpack_from("<I",data,h+4)[0]
    if fid!=6 or typ!=12:
        raise ValueError("Selected record does not have the expected field-6 string header.")
    ident_off=h+10
    if bytes(data[ident_off:ident_off+len(oldb)])!=oldb:
        raise ValueError("Selected identifier no longer matches the save. Rescan and try again.")
    if data[ident_off+len(oldb)]!=0:
        raise ValueError("Identifier terminator is missing.")
    if len(newb)+1>65535:
        raise ValueError("Replacement identifier is too long for this string encoding.")

    path=container_path_for_offset(d,h)
    delta=len(newb)-len(oldb)
    data[ident_off:ident_off+len(oldb)]=newb
    struct.pack_into("<I",data,h+4,old_outer+delta)
    struct.pack_into("<H",data,h+8,len(newb)+1)
    for field in path:
        struct.pack_into("<I",data,field[0]+4,field[3]+delta)

    validate_serialized_save(bytes(data))
    return bytes(data),delta,len(path)

def duplicate_serialized_item(d,identifier_header):
    """Duplicate the exact array element containing the selected item record."""
    data=bytearray(d)
    path,owner,count,elements,element=owner_array_for_offset(d,identifier_header)
    if count>=1000000:
        raise ValueError("Array count is implausibly large; refusing to modify it.")
    element_bytes=d[element[0]:element[1]]
    delta=len(element_bytes)
    if not delta:
        raise ValueError("Selected array element is empty.")
    insert_at=element[1]
    data[insert_at:insert_at]=element_bytes
    struct.pack_into("<I",data,owner[0]+8,count+1)
    struct.pack_into("<I",data,owner[0]+4,owner[3]+delta)
    for field in path:
        if field[0]==owner[0]:
            break
        struct.pack_into("<I",data,field[0]+4,field[3]+delta)
    validate_serialized_save(bytes(data))
    return bytes(data),count,count+1,delta

def remove_serialized_item(d,identifier_header):
    """Remove the exact array element containing the selected item record."""
    data=bytearray(d)
    path,owner,count,elements,element=owner_array_for_offset(d,identifier_header)
    if count<=0:
        raise ValueError("Owning array has no elements.")
    delta=element[1]-element[0]
    del data[element[0]:element[1]]
    struct.pack_into("<I",data,owner[0]+8,count-1)
    struct.pack_into("<I",data,owner[0]+4,owner[3]-delta)
    for field in path:
        if field[0]==owner[0]:
            break
        struct.pack_into("<I",data,field[0]+4,field[3]-delta)
    validate_serialized_save(bytes(data))
    return bytes(data),count,count-1,delta

def _inventory_record_by_header(d,identifier_header):
    """Return the parsed InventoryItem record whose field-6 header matches."""
    target=int(identifier_header)
    for rec in item_records(d):
        ident,rec_start,rec_end,fields,vals=rec
        h=fields[5][1]+4
        if h==target:
            return rec
    raise ValueError("The selected inventory record could not be found after rescanning the decoded save.")

def quickslot_records(d):
    """Return structurally identified quickslot InventoryItem records."""
    out=[]
    for rec in item_records(d):
        ident,rec_start,rec_end,fields,vals=rec
        h=fields[5][1]+4
        try:
            loc=inventory_record_location(d,h)
        except Exception:
            continue
        if loc=="Quickslots" and fields.get(2,(None,None))[0]==4:
            out.append((h,rec))
    return out

def move_quickslot_structural(d,identifier_header,new_index):
    """Move one quickslot to index 0..9; swap with an occupied destination."""
    if not 0<=int(new_index)<=9:
        raise ValueError("Quickslot index must be between 0 and 9.")
    selected=_inventory_record_by_header(d,identifier_header)
    ident,_,_,fields,vals=selected
    if inventory_record_location(d,identifier_header)!="Quickslots":
        raise ValueError("The selected record is not a quickslot item.")
    if fields[2][0]!=4:
        raise ValueError("Quickslot field 2 is not a 32-bit integer.")
    old_index=int(vals[2])
    new_index=int(new_index)
    if old_index==new_index:
        return bytes(d),old_index,new_index,None

    matches=[]
    for h,rec in quickslot_records(d):
        if h==int(identifier_header):
            continue
        if int(rec[4][2])==new_index:
            matches.append((h,rec))
    if len(matches)>1:
        raise ValueError("More than one quickslot already uses the requested destination index; refusing to guess.")

    data=bytearray(d)
    struct.pack_into("<I",data,fields[2][1],new_index)
    swapped=None
    if matches:
        _,other=matches[0]
        other_ident,_,_,other_fields,_=other
        if other_fields[2][0]!=4:
            raise ValueError("Destination quickslot field 2 is not a 32-bit integer.")
        struct.pack_into("<I",data,other_fields[2][1],old_index)
        swapped=other_ident

    validate_serialized_save(bytes(data))
    # Ensure the edited slot map is unique and contains the selected item.
    seen={}
    selected_ok=False
    for h,rec in quickslot_records(bytes(data)):
        idx=int(rec[4][2]); rid=rec[0]
        if idx in seen:
            raise ValueError(f"Quickslot validation found duplicate slot index {idx}.")
        seen[idx]=rid
        if rid==ident and idx==new_index:
            selected_ok=True
    if not selected_ok:
        raise ValueError("Quickslot move validation could not find the selected item at its new slot.")
    return bytes(data),old_index,new_index,swapped

def copy_item_to_quickslot_structural(d,source_identifier_header,target_index):
    """Copy a complete InventoryItem array element into quickslot index 0..9.

    If the target slot is occupied, its entire serialized array element is
    replaced. If empty, a new element is appended and the quickslot array count
    is incremented. All enclosing length fields are updated and validated.
    """
    target_index=int(target_index)
    if not 0<=target_index<=9:
        raise ValueError("Quickslot index must be between 0 and 9.")

    source=_inventory_record_by_header(d,source_identifier_header)
    source_ident,_,_,source_fields,source_vals=source
    source_location=inventory_record_location(d,source_identifier_header)
    if source_location=="Item mods":
        raise ValueError("Nested item-mod records cannot be copied directly to a quickslot.")
    if source_fields[2][0]!=4:
        raise ValueError("The source item's field 2 is not a 32-bit integer.")

    source_path,source_owner,source_count,source_elements,source_element=owner_array_for_offset(d,source_identifier_header)
    clone=bytearray(d[source_element[0]:source_element[1]])
    field2_rel=source_fields[2][1]-source_element[0]
    if not (0<=field2_rel<=len(clone)-4):
        raise ValueError("Could not resolve the source item's slot field inside its serialized element.")
    struct.pack_into("<I",clone,field2_rel,target_index)

    qrecords=quickslot_records(d)
    if not qrecords:
        raise ValueError("No existing quickslot array could be identified in this save.")

    # Every current quickslot should live in the same owning array. Resolve it
    # from the first record, then verify the rest before modifying anything.
    qh0,qrec0=qrecords[0]
    target_path,target_owner,target_count,target_elements,_=owner_array_for_offset(d,qh0)
    for qh,_ in qrecords[1:]:
        _,owner,_,_,_=owner_array_for_offset(d,qh)
        if owner[0]!=target_owner[0]:
            raise ValueError("Quickslot records span more than one owning array; refusing to modify an ambiguous save.")

    occupied=[]
    for qh,qrec in qrecords:
        if int(qrec[4][2])==target_index:
            occupied.append((qh,qrec))
    if len(occupied)>1:
        raise ValueError("More than one quickslot already uses the requested target slot.")

    data=bytearray(d)
    replaced_ident=None
    old_count=target_count
    new_count=target_count
    if occupied:
        target_h,target_rec=occupied[0]
        replaced_ident=target_rec[0]
        _,owner,_,_,target_element=owner_array_for_offset(d,target_h)
        if owner[0]!=target_owner[0]:
            raise ValueError("Target quickslot resolved to an unexpected array.")
        old_len=target_element[1]-target_element[0]
        delta=len(clone)-old_len
        data[target_element[0]:target_element[1]]=clone
        struct.pack_into("<I",data,target_owner[0]+4,target_owner[3]+delta)
        for field in target_path:
            if field[0]==target_owner[0]:
                break
            struct.pack_into("<I",data,field[0]+4,field[3]+delta)
    else:
        delta=len(clone)
        insert_at=target_owner[5]
        data[insert_at:insert_at]=clone
        new_count=target_count+1
        struct.pack_into("<I",data,target_owner[0]+8,new_count)
        struct.pack_into("<I",data,target_owner[0]+4,target_owner[3]+delta)
        for field in target_path:
            if field[0]==target_owner[0]:
                break
            struct.pack_into("<I",data,field[0]+4,field[3]+delta)

    out=bytes(data)
    validate_serialized_save(out)
    # Validate that exactly one record now owns the requested slot and that its
    # identifier matches the copied source item.
    matches=[]
    for h,rec in quickslot_records(out):
        if int(rec[4][2])==target_index:
            matches.append(rec[0])
    if matches!=[source_ident]:
        raise ValueError(f"Quickslot copy validation failed for slot {target_index+1}: {matches!r}")
    return out,old_count,new_count,delta,replaced_ident,source_ident

def _cfg_scalar(text,name):
    m=re.search(rf'(?m)^\s*{re.escape(name)}\s+([^\r\n]+)',text)
    if not m:
        return None
    v=m.group(1).strip()
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    return v

def load_item_catalog(cfgroot):
    """Load ItemCfg metadata from the optional game configs directory."""
    if not cfgroot:
        return {}
    root=Path(cfgroot)
    if not root.exists():
        return {}

    search_root=root
    for candidate in (root/'items', root/'configs'/'items'):
        if candidate.is_dir():
            search_root=candidate
            break

    catalog={}
    for p in search_root.rglob('*.cfg'):
        try:
            text=p.read_text(encoding='utf-8',errors='replace')
        except Exception:
            continue
        if not re.search(r'(?m)^\s*ItemCfg\s*$',text):
            continue
        ident=_cfg_scalar(text,'identifier')
        if not ident:
            continue

        def as_int(name):
            v=_cfg_scalar(text,name)
            if v is None:
                return None
            try:return int(float(v))
            except Exception:return None

        def as_float(name):
            v=_cfg_scalar(text,name)
            if v is None:
                return None
            try:return float(v)
            except Exception:return None

        catalog[ident]={
            'identifier':ident,
            'type':_cfg_scalar(text,'type') or '',
            'tier':as_int('tier'),
            'stack_size':as_int('stack_size'),
            'base_price':as_float('base_price'),
            'durability':as_float('durability'),
            'title_string':_cfg_scalar(text,'title_string') or '',
            'config':str(p)
        }
    return catalog

def load_blueprint_catalog(cfgroot):
    """Load built-in VehicleBlueprintCfg definitions from the optional configs tree.

    These files describe game blueprint templates.  They are deliberately kept
    separate from 93_blueprints.sav because the latter is a PlayerBlueprintCollection
    and is not proven to be a simple unlock list.
    """
    if not cfgroot:
        return {}
    root=Path(cfgroot)
    if not root.exists():
        return {}

    search_root=root
    for candidate in (root/'blueprints', root/'configs'/'blueprints'):
        if candidate.is_dir():
            search_root=candidate
            break

    catalog={}
    for p in search_root.rglob('*.cfg'):
        try:
            text=p.read_text(encoding='utf-8',errors='replace')
        except Exception:
            continue
        if not re.search(r'(?m)^\s*VehicleBlueprintCfg\s*$',text):
            continue

        def as_int(name):
            v=_cfg_scalar(text,name)
            if v is None:return None
            try:return int(float(v))
            except Exception:return None

        key=p.stem
        catalog[key]={
            'name':key,
            'class':_cfg_scalar(text,'m_class') or '',
            'title':_cfg_scalar(text,'m_title') or '',
            'starting_weapon':_cfg_scalar(text,'m_startingWeapon') or '',
            'max_weapon_mounts':as_int('m_maxWeaponMounts'),
            'config':str(p),
        }
    return catalog



def load_vehicle_component_catalog(cfgroot,item_catalog=None):
    """Map ItemCfg identifiers to VehicleComponentCfg role/class metadata.

    Cubic Odyssey keeps the buyable ItemCfg and the component behavior config in
    separate folders but normally uses the same config filename stem.  We join
    them by that stem rather than guessing from the identifier text.
    """
    if not cfgroot:
        return {}
    root=Path(cfgroot)
    if not root.exists():
        return {}

    search_root=root
    for candidate in (root/'components', root/'configs'/'components'):
        if candidate.is_dir():
            search_root=candidate
            break

    item_catalog=item_catalog or load_item_catalog(cfgroot)
    by_stem={}
    for ident,cfg in item_catalog.items():
        try:
            by_stem[Path(cfg.get('config','')).stem]=(ident,cfg)
        except Exception:
            pass

    catalog={}
    for p in search_root.rglob('*.cfg'):
        try:
            text=p.read_text(encoding='utf-8',errors='replace')
        except Exception:
            continue
        if not re.search(r'(?m)^\s*VehicleComponentCfg\s*$',text):
            continue
        pair=by_stem.get(p.stem)
        if not pair:
            continue
        ident,item_cfg=pair
        role=_cfg_scalar(text,'m_type') or ''
        vehicle_class=_cfg_scalar(text,'m_class') or ''
        attrs=[]
        for m in re.finditer(
            r'AttributeOperation\s*\{(?:(?!AttributeOperation\s*\{).)*?'
            r'm_attribute\s+([^\s\r\n]+)(?:(?!AttributeOperation\s*\{).)*?'
            r'm_value\s+([^\s\r\n\}]+)',
            text,re.S
        ):
            attrs.append((m.group(1).strip(),m.group(2).strip()))
        catalog[ident]={
            'identifier':ident,
            'component_type':role,
            'component_class':vehicle_class,
            'attributes':attrs,
            'attributes_text':', '.join(f'{a}={v}' for a,v in attrs),
            'component_config':str(p),
            'item_config':item_cfg.get('config',''),
            'tier':item_cfg.get('tier'),
            'base_price':item_cfg.get('base_price'),
            'title_string':item_cfg.get('title_string',''),
        }
    return catalog


def _field_by_id(fields,fid,typ=None):
    for f in fields:
        if f[1]==fid and (typ is None or f[2]==typ):
            return f
    return None


def _field_u32(d,f,default=None):
    if f is None or f[3]!=4 or f[2] not in (4,8):
        return default
    return struct.unpack_from('<I',d,f[4])[0]


def _field_float(d,f,default=None):
    if f is None or f[2]!=10 or f[3]!=4:
        return default
    return struct.unpack_from('<f',d,f[4])[0]


def replace_counted_utf8_field_structural(d,string_header,old_text,new_text,expected_fid=None):
    """Resize one type-0x0C counted UTF-8 field and fix all parent lengths."""
    data=bytearray(d);h=int(string_header)
    if h<0 or h+10>len(data):
        raise ValueError('String field offset is outside the decoded save.')
    fid,typ=struct.unpack_from('<HH',data,h)
    old_outer=struct.unpack_from('<I',data,h+4)[0]
    if typ!=12:
        raise ValueError('Selected field is not a counted UTF-8 string.')
    if expected_fid is not None and fid!=int(expected_fid):
        raise ValueError(f'Selected string has field id {fid}, expected {expected_fid}.')
    field=(h,fid,typ,old_outer,h+8,h+8+old_outer)
    current=_decode_type12_string(d,field)
    if current!=old_text:
        raise ValueError('Selected string no longer matches the decoded save. Reload and try again.')
    newb=str(new_text).encode('utf-8')
    if len(newb)+1>0xFFFF:
        raise ValueError('Replacement string is too long for the save format.')
    payload=struct.pack('<H',len(newb)+1)+newb+b'\0'
    delta=len(payload)-old_outer
    path=container_path_for_offset(d,h)
    data[h+8:h+8+old_outer]=payload
    struct.pack_into('<I',data,h+4,len(payload))
    for parent in path:
        struct.pack_into('<I',data,parent[0]+4,parent[3]+delta)
    out=bytes(data)
    validate_serialized_save(out)
    return out,delta,len(path)


def parse_player_ships(d):
    """Parse the PlayerShipCollection embedded in 93_client_state.sav.

    The supplied saves consistently place it at:
      top field 6 (player object) -> field 19 -> field 9 -> field 1 array.
    Component item records are ship field 6 -> field 3 array.
    Deployables are ship field 21.
    """
    validate_serialized_save(d)
    nfields=struct.unpack_from('<H',d,4)[0]
    top,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError('93_client_state.sav has trailing bytes.')
    player=_field_by_id(top,6,22)
    if not player:
        return []
    _,_,player_fields=_parse_type22(d,player[0])
    ship_root=_field_by_id(player_fields,19,21)
    if not ship_root:
        return []
    _,root_fields=_parse_type21(d,ship_root[0])
    ship_group=_field_by_id(root_fields,9,21)
    if not ship_group:
        return []
    _,group_fields=_parse_type21(d,ship_group[0])
    ship_array=_field_by_id(group_fields,1,23)
    if not ship_array:
        return []
    count,elements=_parse_type23(d,ship_array[0])

    all_items=item_records(d)
    ships=[]
    for index,element in enumerate(elements):
        fields=element[4]
        components=[]
        comp_group=_field_by_id(fields,6,21)
        if comp_group:
            _,comp_fields=_parse_type21(d,comp_group[0])
            comp_array=_field_by_id(comp_fields,3,23)
            if comp_array:
                _,comp_elements=_parse_type23(d,comp_array[0])
                for ci,ce in enumerate(comp_elements):
                    ef=ce[4]
                    ident_f=_field_by_id(ef,1,12)
                    if not ident_f:
                        continue
                    ident=_decode_type12_string(d,ident_f)
                    components.append({
                        'index':ci,
                        'identifier':ident or '',
                        'identifier_header':ident_f[0],
                        'slot':_field_u32(d,_field_by_id(ef,4,4)),
                        'quantity':_field_u32(d,_field_by_id(ef,3,4)),
                        'field2':_field_float(d,_field_by_id(ef,2,10)),
                        'element_start':ce[0],
                        'element_end':ce[1],
                    })

        deployables=[]
        dep_array=_field_by_id(fields,21,23)
        if dep_array:
            _,dep_elements=_parse_type23(d,dep_array[0])
            for di,de in enumerate(dep_elements):
                ef=de[4]
                ident_f=_field_by_id(ef,8,12)
                deployables.append({
                    'index':di,
                    'identifier':_decode_type12_string(d,ident_f) if ident_f else '',
                    'identifier_header':ident_f[0] if ident_f else None,
                    'entity_id':_field_u32(d,_field_by_id(ef,1,8)),
                    'condition':_field_float(d,_field_by_id(ef,5,10)),
                    'tag':de[2],
                })

        cargo=[]
        for rec in all_items:
            ident,_,_,rfields,vals=rec
            h=rfields[5][1]+4
            if element[0] <= h < element[1]:
                try:loc=inventory_record_location(d,h)
                except Exception:loc=''
                if loc=='Ship inventory':
                    cargo.append({'identifier':ident,'quantity':int(vals[3]),'header':h})

        energy_pair=None
        energy=_field_by_id(fields,22,21)
        if energy:
            _,energy_fields=_parse_type21(d,energy[0])
            a=_field_float(d,_field_by_id(energy_fields,1,10))
            b=_field_float(d,_field_by_id(energy_fields,2,10))
            energy_pair=(a,b)

        ships.append({
            'index':index,
            'tag':element[2],
            'element_start':element[0],
            'element_end':element[1],
            'components':components,
            'deployables':deployables,
            'cargo':cargo,
            'field1':_field_u32(d,_field_by_id(fields,1,8)),
            'entity_value':_field_u32(d,_field_by_id(fields,9,4)),
            'field12':_field_float(d,_field_by_id(fields,12,10)),
            'field24':_field_float(d,_field_by_id(fields,24,10)),
            'energy_pair':energy_pair,
        })
    if len(ships)!=count:
        raise ValueError('PlayerShipCollection count changed while parsing.')
    return ships

def _decode_counted_utf16(payload):
    if len(payload)<2:
        raise ValueError('Counted UTF-16 payload is too short.')
    count=struct.unpack_from('<H',payload,0)[0]
    expected=2+count*2
    if expected!=len(payload):
        raise ValueError(f'Counted UTF-16 length mismatch: count={count}, payload={len(payload)} bytes.')
    raw=payload[2:]
    if raw.endswith(b'\x00\x00'):
        raw=raw[:-2]
    return raw.decode('utf-16-le','strict')


def _encode_counted_utf16(text):
    raw=str(text).encode('utf-16-le')
    units=len(raw)//2+1
    if units>0xFFFF:
        raise ValueError('Display name is too long for the save string format.')
    return struct.pack('<H',units)+raw+b'\x00\x00'


def _decode_counted_utf8(payload):
    if len(payload)<2:
        raise ValueError('Counted string payload is too short.')
    count=struct.unpack_from('<H',payload,0)[0]
    if 2+count!=len(payload):
        raise ValueError(f'Counted string length mismatch: count={count}, payload={len(payload)} bytes.')
    raw=payload[2:]
    if raw.endswith(b'\x00'):
        raw=raw[:-1]
    return raw.decode('utf-8','replace')


def parse_slot_meta(d):
    """Parse the stable fields used by the supplied build's 93_meta.sav.

    Proven by all supplied slots:
      field 1  : float play-time counter (seconds)
      fields 5-10: day, month, year, hour, minute, second
      field 12 : counted UTF-16 display name
      field 21 : counted UTF-8 location/system text

    Field 13 is the character-level snapshot (SaveMetaInfo::update calls
    AtyCharacter::getLevel). It is not a story TaskCfg ID.
    """
    validate_serialized_save(d)
    nfields=struct.unpack_from('<H',d,4)[0]
    fields,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError('93_meta.sav has trailing bytes.')
    fmap={field[1]:field for field in fields}

    def require(fid,typ,ln=None):
        f=fmap.get(fid)
        if not f:
            raise ValueError(f'93_meta.sav is missing field {fid}.')
        if f[2]!=typ or (ln is not None and f[3]!=ln):
            raise ValueError(f'93_meta.sav field {fid} has unexpected type/size (type={f[2]}, length={f[3]}).')
        return f

    f1=require(1,10,4)
    playtime=struct.unpack_from('<f',d,f1[4])[0]

    stamp=[]
    for fid in range(5,11):
        f=require(fid,4,4)
        stamp.append(struct.unpack_from('<I',d,f[4])[0])

    f12=require(12,32)
    name=_decode_counted_utf16(d[f12[4]:f12[5]])

    location=''
    f21=fmap.get(21)
    if f21 and f21[2]==13:
        location=_decode_counted_utf8(d[f21[4]:f21[5]])

    progression=None
    f13=fmap.get(13)
    if f13 and f13[2]==4 and f13[3]==4:
        progression=struct.unpack_from('<I',d,f13[4])[0]

    return {
        'field_count':nfields,
        'playtime_seconds':float(playtime),
        'timestamp':tuple(stamp),
        'display_name':name,
        'location':location,
        'character_level':progression,
        'progression_value':progression,  # Legacy API alias; not story progression.
        'fields':fmap,
    }


def replace_top_level_field_payload(d,fid,expected_type,new_payload):
    """Resize one top-level field and validate the complete serialized file."""
    raw=bytes(d)
    nfields=struct.unpack_from('<H',raw,4)[0]
    fields,pos=_parse_fields(raw,6,nfields,len(raw))
    if pos!=len(raw):
        raise ValueError('Top-level save structure is invalid.')
    target=next((f for f in fields if f[1]==fid),None)
    if not target:
        raise ValueError(f'Top-level field {fid} was not found.')
    off,gotfid,typ,ln,ps,pe=target
    if typ!=expected_type:
        raise ValueError(f'Field {fid} has serializer type {typ}, expected {expected_type}.')
    payload=bytes(new_payload)
    changed=raw[:off]+struct.pack('<HHI',gotfid,typ,len(payload))+payload+raw[pe:]
    validate_serialized_save(changed)
    return changed


def set_slot_meta_display_name(d,new_name):
    changed=replace_top_level_field_payload(d,12,32,_encode_counted_utf16(new_name))
    check=parse_slot_meta(changed)
    if check['display_name']!=new_name:
        raise RuntimeError('Display-name validation failed after resize.')
    return changed


def parse_player_blueprints(d):
    """Parse global 93_blueprints.sav without assuming BlueprintEntry semantics."""
    validate_serialized_save(d)
    nfields=struct.unpack_from('<H',d,4)[0]
    fields,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError('93_blueprints.sav has trailing bytes.')
    fmap={f[1]:f for f in fields}
    f1=fmap.get(1);f2=fmap.get(2)
    if not f1 or f1[2]!=4 or f1[3]!=4:
        raise ValueError('93_blueprints.sav field 1 is not the expected uint32.')
    if not f2 or f2[2]!=23:
        raise ValueError('93_blueprints.sav field 2 is not the expected BlueprintEntry array.')
    raw_value=struct.unpack_from('<I',d,f1[4])[0]
    count,elements=_parse_type23(d,f2[0])
    rows=[]
    for idx,e in enumerate(elements,1):
        estart,eend,tag,nfields,efields=e
        blob=d[estart:eend]
        printable=[]
        for x in strings(blob):
            if x not in printable:printable.append(x)
        rows.append({
            'index':idx,'tag':tag,'field_count':nfields,
            'size':eend-estart,'strings':printable,
            'start':estart,'end':eend,
        })
    return {'raw_field1':raw_value,'count':count,'rows':rows,'fields':fmap}


def discover_slot_dirs(root):
    """Return [(display_label, Path), ...] for likely save-slot folders.

    Cubic Odyssey save layouts seen in the wild include both:
      save/<slot>/*.sav
      save/0/<slot>/*.sav
    and users may also select one slot folder directly.
    """
    root=Path(root)
    found=[]

    def has_saves(p):
        try:
            return any(p.glob("*.sav"))
        except Exception:
            return False

    # If the selected folder itself is a slot, support it directly.
    if has_saves(root) and (root/"93_client_state.sav").exists():
        found.append(("Current folder", root))

    # Direct numeric slot folders.
    try:
        direct=[p for p in root.iterdir() if p.is_dir() and p.name.isdigit() and has_saves(p)]
    except Exception:
        direct=[]
    for p in sorted(direct, key=lambda x:int(x.name)):
        found.append((p.name,p))

    # Nested numeric container/slot folders, e.g. save/0/0, save/0/1 ...
    try:
        parents=[p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    except Exception:
        parents=[]
    nested=[]
    for parent in parents:
        try:
            kids=[q for q in parent.iterdir() if q.is_dir() and q.name.isdigit() and has_saves(q)]
        except Exception:
            kids=[]
        for q in kids:
            nested.append((parent,q))

    nested.sort(key=lambda pair:(int(pair[0].name),int(pair[1].name)))
    for parent,q in nested:
        # For the common save/0/<slot> layout, show only the actual slot number.
        # Otherwise include both levels so labels stay unambiguous.
        label=q.name if len(parents)==1 and parent.name=="0" else f"{parent.name}/{q.name}"
        found.append((label,q))

    # Deduplicate by resolved/absolute path while preserving order.
    out=[]; seen=set()
    for label,p in found:
        try:key=str(p.resolve())
        except Exception:key=str(p.absolute())
        if key in seen: continue
        seen.add(key); out.append((label,p))
    return out

PLAYER_STATS_LABELS={
    1:"Characters",
    2:"Miner characters",
    3:"Crafter characters",
    4:"Pilot characters",
    5:"Knight characters",
    6:"Deleted characters",
    7:"Miner level",
    8:"Crafter level",
    9:"Pilot level",
    10:"Knight level",
}

CLASS_LEVEL_FIELDS={
    "Miner":7,
    "Crafter":8,
    "Pilot":9,
    "Knight":10,
}

PLAYER_VITAL_LABELS={
    'health':'Current health',
    'stamina':'Current stamina / energy',
    'stamina_max':'Saved maximum stamina / energy',
    'shield':'Current shield',
    'shield_max':'Saved maximum shield',
}

def parse_player_vitals(d):
    """Player field 9 is life; 25/37 are stamina/shield current,max pairs.

    Verified against AtyCharacter registration at VA 0x140226ce0 and the
    ObjectStaminaLogic / ObjectShieldLogic serializers in the supplied EXE.
    Both resource classes serialize member +0x50 as current, +0x54 as maximum.
    """
    validate_serialized_save(d)
    top,_=_parse_fields(d,6,struct.unpack_from('<H',d,4)[0],len(d))
    player=_field_by_id(top,6,22)
    if not player:
        raise ValueError('The save has no recognized player object.')
    _,_,fields=_parse_type22(d,player[0])
    values={};offsets={}
    def scalar(fs,fid,key):
        matches=[f for f in fs if f[1]==fid]
        if len(matches)!=1 or matches[0][2:4]!=(10,4):
            raise ValueError(f'{PLAYER_VITAL_LABELS[key]} has an unsupported save format.')
        f=matches[0];value=struct.unpack_from('<f',d,f[4])[0]
        if not math.isfinite(value):
            raise ValueError(f'{PLAYER_VITAL_LABELS[key]} is not a finite number.')
        values[key]=value;offsets[key]=f[4]
    scalar(fields,9,'health')
    for fid,key in ((25,'stamina'),(37,'shield')):
        matches=[f for f in fields if f[1]==fid and f[2]==21]
        if len(matches)!=1:
            raise ValueError(f'The save has no recognized {key} resource.')
        _,children=_parse_type21(d,matches[0][0])
        scalar(children,1,key);scalar(children,2,key+'_max')
    return values,offsets

def set_player_vitals(d,changes):
    values,offsets=parse_player_vitals(d)
    result=bytearray(d);expected=dict(values)
    if not changes or any(key not in values for key in changes):
        raise ValueError('Choose recognized character vitals to edit.')
    for key,value in changes.items():
        value=float(value)
        if not math.isfinite(value) or not 0<=value<=1000000:
            raise ValueError(f'{PLAYER_VITAL_LABELS[key]} must be between 0 and 1000000.')
        packed=struct.pack('<f',value)
        expected[key]=struct.unpack('<f',packed)[0]
        result[offsets[key]:offsets[key]+4]=packed
    for key in ('stamina','shield'):
        if (key in changes or key+'_max' in changes) and expected[key]>expected[key+'_max']:
            raise ValueError(f'Current {key} cannot exceed its saved maximum.')
    changed=bytes(result)
    actual,_=parse_player_vitals(changed)
    if actual!=expected or len(changed)!=len(d):
        raise RuntimeError('Character vitals did not reparse as expected.')
    return changed

def commit_player_vitals(path,baseline,changes):
    """Reject stale UI state and preserve both recovery generations."""
    path=Path(path)
    if path.read_bytes()!=baseline:
        raise ValueError('Client-state save changed. Reload Character Vitals before editing.')
    before=dec(path)
    changed=set_player_vitals(before,changes)
    if changed==before:
        return False
    if path.read_bytes()!=baseline:
        raise ValueError('Client-state save changed while loading. Reload and try again.')
    try:
        write(path,changed)
        if dec(path)!=changed:
            raise RuntimeError('Written character save failed verification.')
    except Exception:
        path.write_bytes(baseline)
        raise
    return True

SKILL_NAMES=('Character','Knighthood','Building','Mining','Crafting','Melee',
             'Ranged','Corruption','Trading','Space Combat')
SKILL_LEVEL_CAP=30  # GameParams +0x248; supplied EXE default and gameconfig.

def parse_character_skills(d):
    """Client 6/19 is PlayerInformation; its field 4 is CharacterSkills.

    Serializers: 0x140269aa0, 0x1404273a0, 0x140385210, 0x1403841b0.
    Skill enum table: 0x14136a4c0. Progress +0x48 rolls over at 1.0 in
    0x140384620. Character level is mirrored in player field 40.
    """
    validate_serialized_save(d)
    def require(fs,fid,typ,length=None):
        matches=[f for f in fs if f[1]==fid]
        if len(matches)!=1 or matches[0][2]!=typ or (length is not None and matches[0][3]!=length):
            raise ValueError(f'Unsupported character skill structure at field {fid}.')
        return matches[0]
    top,_=_parse_fields(d,6,struct.unpack_from('<H',d,4)[0],len(d))
    _,_,player=_parse_type22(d,require(top,6,22)[0])
    mirror=require(player,40,4,4)[4]
    _,info=_parse_type21(d,require(player,19,21)[0])
    _,skills=_parse_type21(d,require(info,4,21)[0])
    if len(skills)!=10:raise ValueError('Expected ten character skill records.')
    values={};offsets={}
    for i,name in enumerate(SKILL_NAMES):
        _,fields=_parse_type21(d,require(skills,i+3,21)[0])
        lo=require(fields,1,4,4)[4];po=require(fields,2,10,4)[4]
        level=struct.unpack_from('<I',d,lo)[0];progress=struct.unpack_from('<f',d,po)[0]
        if not math.isfinite(progress):raise ValueError(f'{name} progress is not finite.')
        values[name]=(level,progress);offsets[name]=(lo,po)
    return values,offsets,mirror

def set_character_skills(d,changes):
    values,offsets,mirror=parse_character_skills(d)
    if not changes or any(name not in values for name in changes):
        raise ValueError('Choose a recognized character skill.')
    result=bytearray(d);expected=dict(values)
    for name,(level,progress) in changes.items():
        if isinstance(level,bool) or not isinstance(level,int) or not 1<=level<=SKILL_LEVEL_CAP:
            raise ValueError(f'{name} level must be a whole number from 1 to {SKILL_LEVEL_CAP}.')
        progress=float(progress)
        if not math.isfinite(progress) or not 0<=progress<1:
            raise ValueError(f'{name} progress must be at least 0% and below 100%.')
        if level==SKILL_LEVEL_CAP:progress=0.0
        packed=struct.pack('<f',progress);progress=struct.unpack('<f',packed)[0]
        if progress>=1:raise ValueError('Progress rounds to 100%; enter a smaller percentage.')
        lo,po=offsets[name]
        struct.pack_into('<I',result,lo,level);result[po:po+4]=packed
        expected[name]=(level,progress)
        if name=='Character':struct.pack_into('<I',result,mirror,level)
    changed=bytes(result)
    actual,_,_=parse_character_skills(changed)
    if actual!=expected or len(changed)!=len(d):raise RuntimeError('Skill edit verification failed.')
    return changed

def commit_character_skills(path,baseline,changes):
    path=Path(path)
    if path.read_bytes()!=baseline:raise ValueError('Save changed. Reload Character Skills before editing.')
    before=dec(path);changed=set_character_skills(before,changes)
    if changed==before:return False
    if path.read_bytes()!=baseline:raise ValueError('Save changed while loading. Reload and try again.')
    try:
        write(path,changed)
        if dec(path)!=changed:raise RuntimeError('Written character skills failed verification.')
    except Exception:
        path.write_bytes(baseline)
        raise
    return True

def parse_player_stats(d):
    """Parse global 93_stats.sav.

    Reverse-engineered from the game's PlayerStats serializer.  The supplied
    game build serializes exactly ten uint32 fields.  Fields 7-10 are the four
    class levels; fields 1-6 are the account counters also displayed by the
    game's player-account UI.
    """
    validate_serialized_save(d)
    if len(d)<6:
        raise ValueError("93_stats.sav is too short.")
    nfields=struct.unpack_from("<H",d,4)[0]
    if nfields!=10:
        raise ValueError(f"Expected 10 PlayerStats fields, found {nfields}.")
    fields,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError("93_stats.sav has trailing bytes.")
    values={}; offsets={}
    for off,fid,typ,ln,ps,pe in fields:
        if fid not in PLAYER_STATS_LABELS:
            raise ValueError(f"Unexpected PlayerStats field id {fid}.")
        if typ!=4 or ln!=4:
            raise ValueError(
                f"PlayerStats field {fid} has unexpected type/size "
                f"(type={typ}, length={ln})."
            )
        values[fid]=struct.unpack_from("<I",d,ps)[0]
        offsets[fid]=ps
    if set(values)!=set(range(1,11)):
        raise ValueError("93_stats.sav is missing one or more expected fields.")
    return values,offsets


QUEST_TYPE_NAMES={
    0:'RESOURCE_REQUEST',
    1:'PLANET_CHART',
    2:'SYSTEM_CHART',
    3:'NPC_PIRATE_BOUNTY',
    4:'NPC_PIRATE_SHIP_BOUNTY',
    5:'HUNT_DARKNESS_CREATURE',
    6:'DARKNESS_CLEANUP',
    7:'PROPS_REQUEST',
    8:'FRUIT_REQUEST',
    9:'HUNT_CREATURE',
}


def load_progression_catalog(cfgroot):
    """Load TaskCfg story/progression definitions from the optional configs tree."""
    if not cfgroot:
        return {}
    root=Path(cfgroot)
    if not root.exists():
        return {}
    search_root=None
    for candidate in (root/'progression',root/'configs'/'progression'):
        if candidate.is_dir():
            search_root=candidate;break
    if search_root is None:
        return {}

    catalog={}
    for p in search_root.glob('*.cfg'):
        try:text=p.read_text(encoding='utf-8',errors='replace')
        except Exception:continue
        if not re.search(r'(?m)^\s*TaskCfg\s*$',text):
            continue

        def val(name):
            m=re.search(rf'(?m)^\s*{re.escape(name)}\s+([^\r\n]+)',text)
            if not m:return ''
            x=m.group(1).strip()
            if len(x)>=2 and x[0]=='"' and x[-1]=='"':x=x[1:-1]
            return x
        try:
            tid=int(val('id') or p.stem)
        except Exception:
            continue
        def as_int(name):
            x=val(name)
            try:return int(float(x)) if x!='' else None
            except Exception:return None

        needed=[]
        for block in re.findall(r'NeededTaskItem\s*\{(.*?)\}',text,re.S):
            mi=re.search(r'(?m)^\s*m_itemStr\s+"([^"]+)"',block)
            mq=re.search(r'(?m)^\s*m_needeQuantity\s+(-?\d+)',block)
            if mi:
                needed.append((mi.group(1),int(mq.group(1)) if mq else None))

        catalog[tid]={
            'id':tid,
            'story_step':val('storyStep'),
            'chapter':as_int('chapter'),
            'description':val('description'),
            'long_text':val('long_text'),
            'category':val('category'),
            'argtype':val('argtype'),
            'arg':val('arg'),
            'reward_item':val('rewardItem'),
            'reward_quantity':as_int('rewardQuantity'),
            'needed_items':needed,
            'config':str(p),
        }
    return catalog


def _quest_u32(d,fmap,fid):
    f=fmap.get(fid)
    if not f or f[2] not in (4,8) or f[3]!=4:
        return None
    return struct.unpack_from('<I',d,f[4])[0]


def _quest_pair(d,fmap,fid):
    f=fmap.get(fid)
    if not f or f[2]!=9 or f[3]!=8:
        return None
    return struct.unpack_from('<II',d,f[4])


def _quest_vec3(d,fmap,fid):
    f=fmap.get(fid)
    if not f or f[2]!=16 or f[3]!=12:
        return None
    return struct.unpack_from('<fff',d,f[4])


def parse_player_quests(d):
    """Parse the per-slot PlayerQuest array in 93_quests.sav.

    Field 1 quest-type values map directly to the ten generated quest types in
    QuestsDistributionConfig. Fields 9 and 10 are intentionally exposed as
    raw reward values until their exact Qbits/XP ordering is runtime-confirmed.
    """
    validate_serialized_save(d)
    nfields=struct.unpack_from('<H',d,4)[0]
    fields,pos=_parse_fields(d,6,nfields,len(d))
    if pos!=len(d):
        raise ValueError('93_quests.sav has trailing bytes.')
    fmap_top={f[1]:f for f in fields}
    top=fmap_top.get(1)
    if not top or top[2]!=23:
        raise ValueError('93_quests.sav field 1 is not the expected PlayerQuest array.')
    count,elements=_parse_type23(d,top[0])
    rows=[]
    for index,e in enumerate(elements,1):
        estart,eend,tag,nf,efs=e
        fmap={f[1]:f for f in efs}
        qtype=_quest_u32(d,fmap,1)
        tasks=[]
        tf=fmap.get(12)
        if tf and tf[2]==23:
            task_count,task_elements=_parse_type23(d,tf[0])
            for ti,te in enumerate(task_elements,1):
                tm={f[1]:f for f in te[4]}
                ttype=_quest_u32(d,tm,1)
                target=''
                sf=tm.get(2)
                if sf and sf[2]==12:
                    target=_decode_type12_string(d,sf) or ''
                tasks.append({
                    'index':ti,
                    'type':ttype,
                    'target':target,
                    'value':_quest_u32(d,tm,3),
                    'field_count':te[3],
                })
        else:
            task_count=0
        target_offset=fmap.get(1,(estart,None,None,None,estart,None))[0]
        rows.append({
            'index':index,'tag':tag,'field_count':nf,
            'type_id':qtype,'type_name':QUEST_TYPE_NAMES.get(qtype,f'UNKNOWN_{qtype}'),
            'reward_a':_quest_u32(d,fmap,9),'reward_b':_quest_u32(d,fmap,10),
            'tasks':tasks,'task_count':task_count,
            'position':_quest_vec3(d,fmap,13),
            'pair3':_quest_pair(d,fmap,3),'pair4':_quest_pair(d,fmap,4),
            'pair14':_quest_pair(d,fmap,14),'pair15':_quest_pair(d,fmap,15),
            'raw5':_quest_u32(d,fmap,5),'raw6':_quest_u32(d,fmap,6),
            'raw7':_quest_u32(d,fmap,7),'raw16':_quest_u32(d,fmap,16),
            'raw17':_quest_u32(d,fmap,17),'raw18':_quest_u32(d,fmap,18),
            'target_offset':target_offset,'element_start':estart,'element_end':eend,
            'field_map':fmap,
        })
    return {'count':count,'rows':rows,'top_field':top}


def set_quest_reward_values(d,target_offset,reward_a,reward_b):
    """Set fixed-size PlayerQuest fields 9 and 10 and validate the full save."""
    reward_a=int(reward_a);reward_b=int(reward_b)
    if not (0<=reward_a<=0xffffffff and 0<=reward_b<=0xffffffff):
        raise ValueError('Quest reward values must fit in an unsigned 32-bit integer.')
    info=parse_player_quests(d)
    row=next((r for r in info['rows'] if r['target_offset']==int(target_offset)),None)
    if row is None:
        raise ValueError('The selected quest could not be found after rescanning the save.')
    f9=row['field_map'].get(9);f10=row['field_map'].get(10)
    if not f9 or f9[2]!=4 or f9[3]!=4 or not f10 or f10[2]!=4 or f10[3]!=4:
        raise ValueError('The selected quest does not have the expected uint32 reward fields 9 and 10.')
    data=bytearray(d)
    struct.pack_into('<I',data,f9[4],reward_a)
    struct.pack_into('<I',data,f10[4],reward_b)
    out=bytes(data)
    validate_serialized_save(out)
    check=parse_player_quests(out)
    verify=next((r for r in check['rows'] if r['target_offset']==int(target_offset)),None)
    if not verify or verify['reward_a']!=reward_a or verify['reward_b']!=reward_b:
        raise RuntimeError('Quest reward validation failed after editing.')
    return out


def remove_quest_structural(d,target_offset):
    """Remove one complete PlayerQuest array element and validate the result."""
    before=parse_player_quests(d)
    row=next((r for r in before['rows'] if r['target_offset']==int(target_offset)),None)
    if row is None:
        raise ValueError('The selected quest could not be found after rescanning the save.')
    out,old_count,new_count,delta=remove_serialized_item(d,int(target_offset))
    after=parse_player_quests(out)
    if old_count!=before['count'] or new_count!=after['count'] or new_count!=old_count-1:
        raise RuntimeError('Quest-array count validation failed after removal.')
    return out,old_count,new_count,delta,row


def find_global_save_file(root,name="93_stats.sav"):
    """Find a top-level/global save when root may be save, save/0, or save/0/slot."""
    p=Path(root)
    candidates=[]
    cur=p
    for _ in range(5):
        candidates.append(cur)
        parent=cur.parent
        if parent==cur:
            break
        cur=parent
    seen=set()
    for folder in candidates:
        try:key=str(folder.resolve())
        except Exception:key=str(folder.absolute())
        if key in seen:continue
        seen.add(key)
        candidate=folder/name
        if candidate.is_file():
            return candidate
    return None

class App:
    def __init__(self,root,cfg=None):
        self.root=Path(root); self.cfgroot=Path(cfg) if cfg else None
        self.item_catalog=load_item_catalog(self.cfgroot)
        self.vehicle_component_catalog=load_vehicle_component_catalog(self.cfgroot,self.item_catalog)
        self.blueprint_catalog=load_blueprint_catalog(self.cfgroot)
        self.progression_catalog=load_progression_catalog(self.cfgroot)
        self.cache={}
        self.slot_paths={}
        self.w=tk.Tk(); self.w.title("Cubic Odyssey Save Editor v1.20"); self.w.geometry("1760x980")
        nb=ttk.Notebook(self.w);nb.pack(fill="both",expand=True,padx=8,pady=8)
        self.lab=ttk.Frame(nb);nb.add(self.lab,text="Experiment Lab")
        self.inv=ttk.Frame(nb);nb.add(self.inv,text="Inventory / Equipment")
        self.stats=ttk.Frame(nb);nb.add(self.stats,text="Player Stats / Classes")
        self.vitals=ttk.Frame(nb);nb.add(self.vitals,text="Character Vitals")
        self.skills=ttk.Frame(nb);nb.add(self.skills,text="Character Skills")
        self.meta=ttk.Frame(nb);nb.add(self.meta,text="Save Slot Details")
        self.quests=ttk.Frame(nb);nb.add(self.quests,text="Quests / Story")
        self.ships=ttk.Frame(nb);nb.add(self.ships,text="Ships / Vehicle")
        self.world=ttk.Frame(nb);nb.add(self.world,text="World Items")
        self.blueprints=ttk.Frame(nb);nb.add(self.blueprints,text="Blueprints")
        self.edit=ttk.Frame(nb);nb.add(self.edit,text="Safe Editors")
        self.cfg=ttk.Frame(nb);nb.add(self.cfg,text="Config Lookup")
        self.build_lab();self.build_inv();self.build_stats();self.build_vitals();self.build_skills();self.build_meta();self.build_quests();self.build_ships();self.build_world();self.build_blueprints();self.build_edit();self.build_cfg()
        self.refresh()

    def build_lab(self):
        f=ttk.Frame(self.lab,padding=8);f.pack(fill="both",expand=True)
        r=ttk.Frame(f);r.pack(fill="x")
        self.sa=tk.StringVar()
        self.fn=tk.StringVar()

        ttk.Label(r,text="Save Slot").pack(side="left")
        self.ca=ttk.Combobox(r,textvariable=self.sa,width=10,state="readonly")
        self.ca.pack(side="left",padx=5)
        self.ca.bind("<<ComboboxSelected>>",lambda e:self.refresh())

        ttk.Label(r,text="File").pack(side="left")
        self.cf=ttk.Combobox(r,textvariable=self.fn,width=48,state="readonly")
        self.cf.pack(side="left",padx=5)

        ttk.Button(r,text="Analyze Save",command=self.analyze).pack(side="left",padx=5)
        ttk.Button(r,text="Scan All Files",command=self.scan_slot).pack(side="left",padx=5)
        ttk.Button(r,text="Refresh",command=self.refresh).pack(side="left",padx=5)
        ttk.Button(r,text="Export JSON",command=self.export).pack(side="left")

        self.labtree=ttk.Treeview(
            f,
            columns=("item","value1","value2","value3","details"),
            show="headings"
        )
        for c,w in [
            ("item",220),("value1",180),("value2",220),
            ("value3",220),("details",600)
        ]:
            self.labtree.heading(c,text=c.title())
            self.labtree.column(c,width=w)
        self.labtree.pack(fill="both",expand=True,pady=8)

        self.status=tk.StringVar(value="Select one save slot.")
        ttk.Label(f,textvariable=self.status,anchor="w").pack(fill="x")
        self.report=[]
    def build_inv(self):
        f=ttk.Frame(self.inv,padding=8);f.pack(fill="both",expand=True)

        bar=ttk.Frame(f);bar.pack(fill="x",pady=(0,4))
        ttk.Label(
            bar,
            text=(
                "Inventory records from 93_client_state.sav. v1.14 adds ship/vehicle inspection and component-role mapping while retaining structural inventory and quickslot tools."
            )
        ).pack(side="left")

        ttk.Button(bar,text="Remove Item",command=self.remove_item).pack(side="right",padx=3)
        ttk.Button(bar,text="Duplicate Item",command=self.duplicate_item).pack(side="right",padx=3)
        ttk.Button(bar,text="Replace Item ID",command=self.replace_item_identifier).pack(side="right",padx=3)
        ttk.Button(bar,text="Set Max Stack",command=self.set_max_stack).pack(side="right",padx=3)
        ttk.Button(bar,text="Edit Condition / Charge",command=self.edit_condition).pack(side="right",padx=3)
        ttk.Button(bar,text="Edit Quantity",command=self.edit_quantity).pack(side="right",padx=3)
        ttk.Button(bar,text="Rescan",command=self.refresh).pack(side="right",padx=3)

        qbar=ttk.Frame(f);qbar.pack(fill="x",pady=(0,6))
        ttk.Label(
            qbar,
            text="Quickslots: internal indices 0–9 are displayed as slots 1–10. Move swaps occupied slots; Copy replaces an occupied slot or appends to an empty one."
        ).pack(side="left")
        ttk.Button(qbar,text="Clear Quickslot",command=self.clear_quickslot).pack(side="right",padx=3)
        ttk.Button(qbar,text="Copy to Quickslot",command=self.copy_to_quickslot).pack(side="right",padx=3)
        ttk.Button(qbar,text="Move / Swap Quickslot",command=self.move_quickslot).pack(side="right",padx=3)

        self.inv_status=tk.StringVar(value="Inventory not scanned yet.")
        ttk.Label(f,textvariable=self.inv_status,anchor="w").pack(fill="x",pady=(0,6))

        self.it=ttk.Treeview(
            f,
            columns=("slot","location","quickslot","identifier","type","tier","qty","maxstack","condition","file"),
            show="headings"
        )
        headings={
            "slot":"Save", "location":"Location", "quickslot":"Quickslot", "identifier":"Identifier", "type":"Config Type",
            "tier":"Tier", "qty":"Quantity", "maxstack":"Max Stack",
            "condition":"Condition / Charge", "file":"File"
        }
        for c,w in [
            ("slot",50),("location",120),("quickslot",70),("identifier",315),("type",135),("tier",45),
            ("qty",70),("maxstack",75),("condition",120),("file",165)
        ]:
            self.it.heading(c,text=headings[c])
            self.it.column(c,width=w)
        self.it.pack(fill="both",expand=True)
        self.it.bind("<Double-1>",lambda e:self.edit_quantity())

    def edit_quantity(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Edit Quantity","Select an inventory item first.")
                return

            iid=selected[0]
            meta=getattr(self,"inventory_meta",{}).get(iid)
            if not meta:
                raise RuntimeError("Could not identify the selected inventory record.")

            p=Path(meta["path"])
            data=bytearray(dec(p))
            offset=meta["quantity_offset"]
            old=struct.unpack_from("<I",data,offset)[0]

            value=tk.simpledialog.askinteger(
                "Edit Quantity",
                f"{meta['identifier']}\n\nCurrent quantity: {old}\n\nNew quantity:",
                parent=self.w,
                minvalue=0,
                maxvalue=4294967295,
                initialvalue=old
            )
            if value is None or value==old:
                return

            # Field 3 is the proven 32-bit unsigned quantity field in the
            # InventoryItem records identified by the reverse-engineering work.
            struct.pack_into("<I",data,offset,int(value))
            write(p,data)

            self.refresh()
            messagebox.showinfo(
                "Quantity Updated",
                f"{meta['identifier']}\n\n"
                f"{old} → {value}\n\n"
                f"Backup created alongside the save if one did not already exist."
            )
        except Exception as e:
            messagebox.showerror("Edit Quantity error",str(e))

    def set_max_stack(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Set Max Stack","Select an inventory item first.")
                return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta:
                raise RuntimeError("Could not identify the selected inventory record.")

            cfg=self.item_catalog.get(meta['identifier'])
            if not cfg or cfg.get('stack_size') is None:
                messagebox.showinfo(
                    "Set Max Stack",
                    "No stack_size was found for this identifier. Load the game's configs folder to enable config-aware stack editing."
                )
                return
            target=int(cfg['stack_size'])
            if target < 0:
                raise RuntimeError("The config contains an invalid negative stack size.")

            p=Path(meta['path'])
            data=bytearray(dec(p))
            offset=meta['quantity_offset']
            old=struct.unpack_from('<I',data,offset)[0]
            if old==target:
                messagebox.showinfo("Set Max Stack",f"{meta['identifier']} is already at its configured max stack ({target}).")
                return

            struct.pack_into('<I',data,offset,target)
            write(p,data)
            self.refresh()
            messagebox.showinfo(
                "Max Stack Applied",
                f"{meta['identifier']}\n\n{old} → {target}\n\nConfigured stack_size was read from the item config."
            )
        except Exception as e:
            messagebox.showerror("Set Max Stack error",str(e))

    def _pick_replacement_identifier(self,current):
        current_bytes=current.encode('utf-8')
        current_cfg=self.item_catalog.get(current,{})
        current_type=current_cfg.get('type','')
        candidates=[(ident,cfg) for ident,cfg in self.item_catalog.items() if ident!=current]
        if not candidates:
            messagebox.showinfo("Replace Item ID","No replacement identifiers were found in the loaded item configs.")
            return None

        top=tk.Toplevel(self.w)
        top.title(f"Replace {current}")
        top.geometry("1060x650")
        top.transient(self.w); top.grab_set()
        result={'value':None}
        outer=ttk.Frame(top,padding=10);outer.pack(fill='both',expand=True)
        ttk.Label(
            outer,
            text=(
                f"Current: {current} ({len(current_bytes)} UTF-8 bytes). v1.12 can resize the identifier and updates every enclosing "
                "0x15/0x16/0x17 container length. Same-type replacements are safest because item-specific nested state is copied unchanged."
            ),wraplength=1010
        ).pack(anchor='w',pady=(0,8))

        controls=ttk.Frame(outer);controls.pack(fill='x',pady=(0,8))
        query=tk.StringVar(); ttk.Label(controls,text='Filter').pack(side='left')
        entry=ttk.Entry(controls,textvariable=query,width=42);entry.pack(side='left',padx=6)
        same_type=tk.BooleanVar(value=bool(current_type))
        ttk.Checkbutton(
            controls,text=f"Same config type only{(' ('+current_type+')') if current_type else ''}",variable=same_type
        ).pack(side='left',padx=8)

        tree=ttk.Treeview(
            outer,columns=('identifier','bytes','delta','type','tier','stack','price'),show='headings'
        )
        for c,title,w in [
            ('identifier','Identifier',360),('bytes','Bytes',60),('delta','Size Δ',60),
            ('type','Type',170),('tier','Tier',55),('stack','Stack',65),('price','Base Price',90)
        ]:
            tree.heading(c,text=title);tree.column(c,width=w)
        tree.pack(fill='both',expand=True)
        status=tk.StringVar();ttk.Label(outer,textvariable=status,anchor='w').pack(fill='x',pady=(6,0))
        buttons=ttk.Frame(outer);buttons.pack(fill='x',pady=(8,0))

        def refill(*_):
            q=query.get().strip().lower();tree.delete(*tree.get_children());shown=0
            for ident,cfg in sorted(candidates,key=lambda x:x[0]):
                if same_type.get() and current_type and cfg.get('type','')!=current_type:
                    continue
                hay=' '.join([ident,cfg.get('type',''),cfg.get('title_string','')]).lower()
                if q and q not in hay: continue
                n=len(ident.encode('utf-8'));delta=n-len(current_bytes)
                tree.insert('', 'end', iid=f'c{shown}', values=(
                    ident,n,f"{delta:+d}",cfg.get('type',''),
                    '' if cfg.get('tier') is None else cfg.get('tier'),
                    '' if cfg.get('stack_size') is None else cfg.get('stack_size'),
                    '' if cfg.get('base_price') is None else f"{cfg.get('base_price'):g}"
                ))
                shown+=1
            status.set(f"{shown} identifiers shown | different-length replacements are structurally supported")

        def choose(*_):
            sel=tree.selection()
            if not sel:return
            result['value']=tree.item(sel[0],'values')[0];top.destroy()

        ttk.Button(buttons,text='Use Selected Item',command=choose).pack(side='right',padx=4)
        ttk.Button(buttons,text='Cancel',command=top.destroy).pack(side='right',padx=4)
        query.trace_add('write',refill);same_type.trace_add('write',refill);tree.bind('<Double-1>',choose)
        refill();entry.focus_set();self.w.wait_window(top)
        return result['value']

    def replace_item_identifier(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Replace Item ID","Select an inventory item first.");return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta: raise RuntimeError("Could not identify the selected inventory record.")
            if not self.item_catalog:
                messagebox.showinfo(
                    "Replace Item ID",
                    "Load/select the game's configs folder when starting the editor. The config catalog is required for item replacement."
                );return

            old_ident=meta['identifier'];new_ident=self._pick_replacement_identifier(old_ident)
            if not new_ident or new_ident==old_ident:return
            old_cfg=self.item_catalog.get(old_ident,{});new_cfg=self.item_catalog.get(new_ident,{})
            old_type=old_cfg.get('type','');new_type=new_cfg.get('type','')
            old_n=len(old_ident.encode('utf-8'));new_n=len(new_ident.encode('utf-8'));delta=new_n-old_n
            type_note=("same config type" if old_type and old_type==new_type else "DIFFERENT config type")
            if not messagebox.askyesno(
                "Confirm Item Replacement",
                f"Replace:\n\n{old_ident}\n\nwith:\n\n{new_ident}\n\n"
                f"Identifier size: {old_n} → {new_n} bytes ({delta:+d})\nType: {old_type or '?'} → {new_type or '?'} ({type_note})\n\n"
                "v1.12 will resize the string, update every enclosing serialized container length, then validate the full known container tree before writing. "
                "Same-type replacements are safest because nested item state is not regenerated. Continue?"
            ):return

            p=Path(meta['path']);before=dec(p)
            data,delta,path_depth=replace_identifier_structural(
                before,meta['identifier_header'],old_ident,new_ident
            )
            before_count=len(item_records(before));after_records=item_records(data)
            if len(after_records)!=before_count:
                raise RuntimeError("Inventory-record count changed during identifier replacement. No data was written.")
            if not any(r[0]==new_ident for r in after_records):
                raise RuntimeError("Replacement identifier was not found after structural validation. No data was written.")
            write(p,data);self.refresh()
            messagebox.showinfo(
                "Item ID Replaced",
                f"{old_ident}\n→ {new_ident}\n\nSize change: {delta:+d} decoded bytes.\n"
                f"Updated {path_depth} enclosing container length(s).\nFull known-container validation passed."
            )
        except Exception as e:
            messagebox.showerror("Replace Item ID error",str(e))

    def duplicate_item(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Duplicate Item","Select an inventory item first.");return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta: raise RuntimeError("Could not identify the selected inventory record.")
            if meta.get('location') not in ('Player inventory','Ship inventory','Other inventory'):
                messagebox.showinfo(
                    "Duplicate Item",
                    f"The selected record is in {meta.get('location','an unsupported container')}.\n\n"
                    "v1.12 only duplicates records from serialized inventory arrays, not quickslots or nested mod arrays."
                );return
            if not messagebox.askyesno(
                "Confirm Duplicate Item",
                f"Duplicate this complete serialized item entry?\n\n{meta['identifier']}\nLocation: {meta.get('location','')}\n\n"
                "The entire array element is cloned, including any item-specific nested state. The owning array count and all enclosing lengths will be updated and validated."
            ):return
            p=Path(meta['path']);before=dec(p);before_records=len(item_records(before))
            data,old_count,new_count,delta=duplicate_serialized_item(before,meta['identifier_header'])
            after_records=item_records(data)
            if len(after_records)<=before_records:
                raise RuntimeError("Duplicate verification failed: no additional inventory record was detected.")
            write(p,data);self.refresh()
            messagebox.showinfo(
                "Item Duplicated",
                f"{meta['identifier']}\n\nOwning array count: {old_count} → {new_count}\n"
                f"Decoded save grew by {delta:,} bytes.\nFull known-container validation passed."
            )
        except Exception as e:
            messagebox.showerror("Duplicate Item error",str(e))

    def remove_item(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Remove Item","Select an inventory item first.");return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta: raise RuntimeError("Could not identify the selected inventory record.")
            if meta.get('location') not in ('Player inventory','Ship inventory','Other inventory'):
                messagebox.showinfo(
                    "Remove Item",
                    f"The selected record is in {meta.get('location','an unsupported container')}.\n\n"
                    "v1.12 only removes complete entries from serialized inventory arrays, not quickslots or nested mod arrays."
                );return
            if not messagebox.askyesno(
                "Confirm Remove Item",
                f"Permanently remove this complete serialized item entry from the selected save?\n\n"
                f"{meta['identifier']}\nLocation: {meta.get('location','')}\nQuantity: {meta.get('quantity','?')}\n\n"
                "A .bak backup is retained. The owning array count and all enclosing lengths will be updated and validated before writing."
            ):return
            p=Path(meta['path']);before=dec(p);before_records=len(item_records(before))
            data,old_count,new_count,removed=remove_serialized_item(before,meta['identifier_header'])
            after_records=item_records(data)
            if len(after_records)>=before_records:
                raise RuntimeError("Removal verification failed: inventory-record count did not decrease.")
            write(p,data);self.refresh()
            messagebox.showinfo(
                "Item Removed",
                f"{meta['identifier']}\n\nOwning array count: {old_count} → {new_count}\n"
                f"Removed {removed:,} decoded bytes.\nFull known-container validation passed."
            )
        except Exception as e:
            messagebox.showerror("Remove Item error",str(e))

    def move_quickslot(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Move / Swap Quickslot","Select a quickslot item first.");return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta: raise RuntimeError("Could not identify the selected inventory record.")
            if meta.get("location")!="Quickslots":
                messagebox.showinfo("Move / Swap Quickslot","The selected row is not in Quickslots.");return
            old_internal=int(meta.get("field2",-1))
            if not 0<=old_internal<=9:
                raise RuntimeError(f"The selected quickslot has an unexpected internal index: {old_internal}")
            choice=simpledialog.askinteger(
                "Move / Swap Quickslot",
                f"{meta['identifier']}\n\nCurrent quickslot: {old_internal+1}\n\nMove to quickslot (1-10):",
                parent=self.w,minvalue=1,maxvalue=10,initialvalue=old_internal+1
            )
            if choice is None:return
            target=int(choice)-1
            if target==old_internal:return
            p=Path(meta['path']);before=dec(p)
            data,old_idx,new_idx,swapped=move_quickslot_structural(before,meta['identifier_header'],target)
            if not messagebox.askyesno(
                "Confirm Quickslot Move",
                f"Move {meta['identifier']} from quickslot {old_idx+1} to {new_idx+1}?\n\n"+
                (f"Quickslot {new_idx+1} is occupied by {swapped}; the two items will swap positions." if swapped else f"Quickslot {new_idx+1} is empty; the item will move there.")
            ):return
            write(p,data);self.refresh()
            messagebox.showinfo(
                "Quickslot Updated",
                f"{meta['identifier']}\nQuickslot {old_idx+1} → {new_idx+1}"+
                (f"\n{swapped}\nQuickslot {new_idx+1} → {old_idx+1}" if swapped else "")+
                "\n\nSerialized structure validation passed."
            )
        except Exception as e:
            messagebox.showerror("Move / Swap Quickslot error",str(e))

    def copy_to_quickslot(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Copy to Quickslot","Select an inventory or quickslot item first.");return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta: raise RuntimeError("Could not identify the selected inventory record.")
            if meta.get("location") not in ("Player inventory","Quickslots"):
                messagebox.showinfo(
                    "Copy to Quickslot",
                    f"The selected record is in {meta.get('location','an unsupported container')}.\n\n"
                    "v1.12 only copies Player inventory or existing Quickslot items into the quickslot array."
                );return
            initial=(int(meta.get("field2",0))+1) if meta.get("location")=="Quickslots" and 0<=int(meta.get("field2",-1))<=9 else 1
            choice=simpledialog.askinteger(
                "Copy to Quickslot",
                f"{meta['identifier']}\n\nCopy the complete serialized item into quickslot (1-10):",
                parent=self.w,minvalue=1,maxvalue=10,initialvalue=initial
            )
            if choice is None:return
            target=int(choice)-1
            if meta.get("location")=="Quickslots" and int(meta.get("field2",-1))==target:
                messagebox.showinfo("Copy to Quickslot","That item is already in the selected quickslot.");return
            p=Path(meta['path']);before=dec(p)
            data,old_count,new_count,delta,replaced,source_ident=copy_item_to_quickslot_structural(
                before,meta['identifier_header'],target
            )
            action=(f"replace {replaced}" if replaced else "fill an empty slot")
            if not messagebox.askyesno(
                "Confirm Copy to Quickslot",
                f"Copy this complete serialized item to quickslot {target+1}?\n\n{source_ident}\n\n"
                f"This will {action}. The original source item is left unchanged.\n"
                "All enclosing container lengths and the quickslot array count will be validated before the save is written."
            ):return
            write(p,data);self.refresh()
            messagebox.showinfo(
                "Quickslot Copied",
                f"{source_ident}\n→ Quickslot {target+1}\n\n"
                f"Quickslot array count: {old_count} → {new_count}\nDecoded size change: {delta:+,} bytes\n"
                "Full known-container validation passed."
            )
        except Exception as e:
            messagebox.showerror("Copy to Quickslot error",str(e))

    def clear_quickslot(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo("Clear Quickslot","Select a quickslot item first.");return
            meta=getattr(self,"inventory_meta",{}).get(selected[0])
            if not meta: raise RuntimeError("Could not identify the selected inventory record.")
            if meta.get("location")!="Quickslots":
                messagebox.showinfo("Clear Quickslot","The selected row is not in Quickslots.");return
            idx=int(meta.get("field2",-1))
            label=str(idx+1) if 0<=idx<=9 else "?"
            if not messagebox.askyesno(
                "Confirm Clear Quickslot",
                f"Remove this complete serialized entry from quickslot {label}?\n\n{meta['identifier']}\n\n"
                "This does not delete a separate copy from Player inventory. A .bak baseline and .prev one-step undo are retained."
            ):return
            p=Path(meta['path']);before=dec(p)
            data,old_count,new_count,removed=remove_serialized_item(before,meta['identifier_header'])
            # Make sure the removed record is no longer present at its exact slot.
            for _,rec in quickslot_records(data):
                if rec[0]==meta['identifier'] and int(rec[4][2])==idx:
                    raise RuntimeError("Quickslot clear verification still found the removed entry.")
            write(p,data);self.refresh()
            messagebox.showinfo(
                "Quickslot Cleared",
                f"Quickslot {label}: {meta['identifier']} removed\n\n"
                f"Quickslot array count: {old_count} → {new_count}\nRemoved {removed:,} decoded bytes.\n"
                "Full known-container validation passed."
            )
        except Exception as e:
            messagebox.showerror("Clear Quickslot error",str(e))

    def edit_condition(self):
        try:
            selected=self.it.selection()
            if not selected:
                messagebox.showinfo(
                    "Edit Condition / Charge",
                    "Select an inventory item first."
                )
                return

            iid=selected[0]
            meta=getattr(self,"inventory_meta",{}).get(iid)
            if not meta:
                raise RuntimeError("Could not identify the selected inventory record.")

            if meta.get("condition_type") != 10:
                messagebox.showinfo(
                    "Edit Condition / Charge",
                    "This item's field 5 is not stored as a 32-bit float, so v1.12 will not modify it."
                )
                return

            p=Path(meta["path"])
            data=bytearray(dec(p))
            offset=meta["condition_offset"]
            old=struct.unpack_from("<f",data,offset)[0]

            value=tk.simpledialog.askfloat(
                "Edit Condition / Charge",
                f"{meta['identifier']}\n\n"
                f"Current field-5 value: {old:g}\n\n"
                "For weapons this is typically durability (often 100). "
                "For batteries or similar items it may represent charge/capacity.\n\n"
                "New value:",
                parent=self.w,
                minvalue=0.0,
                maxvalue=1000000.0,
                initialvalue=float(old)
            )
            if value is None or float(value)==float(old):
                return

            # Field 5 is a 32-bit float in the validated inventory records.
            # Its observed use is item condition/durability/charge. We do not
            # alter records where field 5 uses any other serializer type.
            struct.pack_into("<f",data,offset,float(value))
            write(p,data)

            self.refresh()
            messagebox.showinfo(
                "Condition / Charge Updated",
                f"{meta['identifier']}\n\n"
                f"{old:g} → {float(value):g}\n\n"
                "A .bak backup is kept alongside the save."
            )
        except Exception as e:
            messagebox.showerror("Edit Condition / Charge error",str(e))

    def build_vitals(self):
        f=ttk.Frame(self.vitals,padding=16);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Edit the selected character\'s health, stamina/energy, and shield.',
                  wraplength=1200).pack(anchor='w',pady=(0,10))
        self.vitals_status=tk.StringVar()
        ttk.Label(f,textvariable=self.vitals_status,wraplength=1400).pack(anchor='w',pady=(0,14))
        grid=ttk.Frame(f);grid.pack(anchor='w')
        self.vital_vars={}
        for index,(key,label) in enumerate(PLAYER_VITAL_LABELS.items()):
            ttk.Label(grid,text=label,width=38).grid(row=index,column=0,sticky='w',pady=7)
            var=tk.StringVar();self.vital_vars[key]=var
            ttk.Entry(grid,textvariable=var,width=24).grid(row=index,column=1,padx=12,pady=7)
        actions=ttk.Frame(f);actions.pack(anchor='w',pady=18)
        ttk.Button(actions,text='Apply Character Vitals',command=self.apply_vitals).pack(side='left',padx=(0,8))
        ttk.Button(actions,text='Fill Stamina and Shield',command=self.fill_vitals).pack(side='left',padx=(0,8))
        ttk.Button(actions,text='Reload Character Vitals',command=self.refresh_vitals).pack(side='left')
        ttk.Label(f,text='Fill copies the displayed saved maximums into the current-value boxes; click Apply to save. '
                  'Maximums may be recalculated by the game from equipment or other bonuses. '
                  'A saved maximum-health field has not been identified.',wraplength=1200).pack(anchor='w',pady=(0,18))
        recovery=ttk.Frame(f);recovery.pack(anchor='w')
        ttk.Button(recovery,text='Undo Last Client-state Edit (.prev)',command=lambda:self.recover_vitals(False)).pack(side='left',padx=(0,8))
        ttk.Button(recovery,text='Restore Original Client-state (.bak)',command=lambda:self.recover_vitals(True)).pack(side='left')
        ttk.Label(f,text='Recovery restores the entire 93_client_state.sav, including inventory and ships. '
                  'The .bak baseline and .prev previous save are shared with those editors.',
                  wraplength=1200).pack(anchor='w',pady=10)
        self.vitals_path=None;self.vitals_baseline=None;self.vitals_values={}

    def refresh_vitals(self):
        self.vitals_path=None;self.vitals_baseline=None;self.vitals_values={}
        for var in self.vital_vars.values():var.set('')
        try:
            slot=self.slot_paths.get(str(self.sa.get()).strip())
            if not slot:raise ValueError('Select a save slot in Experiment Lab.')
            path=slot/'93_client_state.sav'
            baseline=path.read_bytes()
            values,_=parse_player_vitals(dec(path))
            if path.read_bytes()!=baseline:raise ValueError('Save changed while loading; reload it.')
            self.vitals_path=path;self.vitals_baseline=baseline;self.vitals_values=values
            for key,value in values.items():self.vital_vars[key].set(str(value))
            self.vitals_status.set(f'Slot {self.sa.get()} | {path}')
        except Exception as exc:self.vitals_status.set(f'Character vitals unavailable: {exc}')

    def fill_vitals(self):
        if self.vitals_path is None:return
        for key in ('stamina','shield'):self.vital_vars[key].set(self.vital_vars[key+'_max'].get())

    def apply_vitals(self):
        try:
            if self.vitals_path is None:raise ValueError('Load a supported character save first.')
            values={key:float(var.get()) for key,var in self.vital_vars.items()}
            changes={key:value for key,value in values.items() if value!=self.vitals_values[key]}
            if not changes:return
            # Validate the whole proposed edit before showing the confirmation.
            set_player_vitals(dec(self.vitals_path),changes)
            summary='\n'.join(f'{PLAYER_VITAL_LABELS[key]}: {self.vitals_values[key]:g} → {value:g}'
                              for key,value in changes.items())
            if not messagebox.askyesno('Apply Character Vitals',f'Slot {self.sa.get()}\n\n{summary}\n\nSave these changes with .bak/.prev recovery copies?'):return
            commit_player_vitals(self.vitals_path,self.vitals_baseline,changes)
            self.refresh()
            messagebox.showinfo('Character Vitals Saved',summary)
        except Exception as exc:messagebox.showerror('Character Vitals error',str(exc))

    def recover_vitals(self,original):
        try:
            if self.vitals_path is None:raise ValueError('Load a supported character save first.')
            path=self.vitals_path;backup=Path(str(path)+('.bak' if original else '.prev'))
            restored=backup.read_bytes();parse_player_vitals(dec(backup))
            if not messagebox.askyesno('Restore Client-state Save',
                f'Restore {backup.name}? This replaces the entire client-state save, including inventory and ships.'):return
            current=path.read_bytes();previous=Path(str(path)+'.prev')
            previous.write_bytes(current);path.write_bytes(restored)
            self.refresh()
        except Exception as exc:messagebox.showerror('Character Vitals recovery error',str(exc))

    def build_skills(self):
        f=ttk.Frame(self.skills,padding=16);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Edit character level and individual skills in the selected save slot.').pack(anchor='w')
        self.skills_status=tk.StringVar()
        ttk.Label(f,textvariable=self.skills_status,wraplength=1300).pack(anchor='w',pady=10)
        grid=ttk.Frame(f);grid.pack(anchor='w')
        for col,text in enumerate(('Skill','Level (1–30)','Progress to next level (%)')):
            ttk.Label(grid,text=text).grid(row=0,column=col,sticky='w',padx=10,pady=6)
        self.skill_vars={}
        for row,name in enumerate(SKILL_NAMES,1):
            ttk.Label(grid,text=name,width=22).grid(row=row,column=0,sticky='w',padx=10,pady=4)
            lv=tk.StringVar();pv=tk.StringVar();self.skill_vars[name]=(lv,pv)
            ttk.Entry(grid,textvariable=lv,width=16).grid(row=row,column=1,padx=10,pady=4)
            ttk.Entry(grid,textvariable=pv,width=24).grid(row=row,column=2,padx=10,pady=4)
        actions=ttk.Frame(f);actions.pack(anchor='w',pady=14)
        ttk.Button(actions,text='Apply Character Skills',command=self.apply_skills).pack(side='left',padx=8)
        ttk.Button(actions,text='Reload Character Skills',command=self.refresh_skills).pack(side='left',padx=8)
        ttk.Label(f,text='Progress is a percentage, not total XP: 50 means halfway to the next level. '
                  'Level 30 edits set progress to zero, matching the supplied game build. '
                  'Character level edits also update its saved runtime copy. '
                  'The save-selection metadata level refreshes when the game next saves.',wraplength=1200).pack(anchor='w',pady=8)
        ttk.Label(f,text='Edits share .bak/.prev backups with Character Vitals, inventory and ships. '
                  'Use the recovery buttons below to restore the entire client-state file. '
                  'Level-up rewards, achievements and account records may require gameplay events.',wraplength=1200).pack(anchor='w',pady=8)
        actions=ttk.Frame(f);actions.pack(anchor='w',pady=8)
        ttk.Button(actions,text='Undo Last Client-state Edit (.prev)',command=lambda:self.recover_vitals(False)).pack(side='left',padx=8)
        ttk.Button(actions,text='Restore Original Client-state (.bak)',command=lambda:self.recover_vitals(True)).pack(side='left',padx=8)
        self.skills_path=None;self.skills_baseline=None;self.skills_values={}

    def refresh_skills(self):
        self.skills_path=None;self.skills_baseline=None;self.skills_values={}
        for pair in self.skill_vars.values():
            for var in pair:var.set('')
        try:
            slot=self.slot_paths.get(str(self.sa.get()).strip())
            if not slot:raise ValueError('Select a save slot in Experiment Lab.')
            path=slot/'93_client_state.sav';baseline=path.read_bytes()
            data=dec(path);values,_,mirror=parse_character_skills(data)
            if path.read_bytes()!=baseline:raise ValueError('Save changed while loading; reload it.')
            self.skills_path=path;self.skills_baseline=baseline;self.skills_values=values
            for name,(level,progress) in values.items():
                lv,pv=self.skill_vars[name];lv.set(str(level));pv.set(f'{progress*100:.6f}'.rstrip('0').rstrip('.') or '0')
            saved_level=struct.unpack_from('<I',data,mirror)[0]
            self.skills_status.set(f'Slot {self.sa.get()} | Character level {values["Character"][0]} | Runtime copy {saved_level} | {path}')
        except Exception as exc:self.skills_status.set(f'Character skills unavailable: {exc}')

    def apply_skills(self):
        try:
            if self.skills_path is None:raise ValueError('Load a supported character save first.')
            changes={}
            for name,(lv,pv) in self.skill_vars.items():
                old_level,old_progress=self.skills_values[name]
                old_display=f'{old_progress*100:.6f}'.rstrip('0').rstrip('.') or '0'
                level=int(lv.get())
                progress=old_progress if pv.get().strip()==old_display else float(pv.get())/100
                # Compare the stored float32 to avoid changing untouched percentages.
                if level!=old_level or struct.pack('<f',progress)!=struct.pack('<f',old_progress):
                    changes[name]=(level,progress)
            if not changes:return
            changed=set_character_skills(dec(self.skills_path),changes)
            actual,_,_=parse_character_skills(changed)
            summary='\n'.join(f'{name}: level {self.skills_values[name][0]} → {actual[name][0]}, progress {self.skills_values[name][1]*100:.4g}% → {actual[name][1]*100:.4g}%' for name in changes)
            if not messagebox.askyesno('Apply Character Skills',f'Slot {self.sa.get()}\n\n{summary}\n\nSave with .bak/.prev recovery copies?'):return
            commit_character_skills(self.skills_path,self.skills_baseline,changes)
            self.refresh();messagebox.showinfo('Character Skills Saved',summary)
        except Exception as exc:messagebox.showerror('Character Skills error',str(exc))

    def build_stats(self):
        f=ttk.Frame(self.stats,padding=12);f.pack(fill="both",expand=True)

        ttk.Label(
            f,
            text=(
                "Global 93_stats.sav account data. The first six values are the game's own account counters; "
                "the four class-level fields were mapped from the PlayerStats serializer and class enum. "
                "This file is global/shared rather than tied to the currently selected numbered save slot."
            ),
            wraplength=1280
        ).pack(anchor="w",pady=(0,8))

        self.stats_status=tk.StringVar(value="Player stats not loaded yet.")
        ttk.Label(f,textvariable=self.stats_status,anchor="w").pack(fill="x",pady=(0,10))

        body=ttk.Frame(f);body.pack(fill="both",expand=True)
        left=ttk.LabelFrame(body,text="Account Counters (read-only)",padding=8)
        left.pack(side="left",fill="both",expand=True,padx=(0,8))
        self.stats_tree=ttk.Treeview(left,columns=("field","name","value"),show="headings",height=12)
        for c,title,w in [("field","Field",70),("name","Game counter",260),("value","Value",150)]:
            self.stats_tree.heading(c,text=title);self.stats_tree.column(c,width=w,anchor="w")
        self.stats_tree.pack(fill="both",expand=True)

        right=ttk.LabelFrame(body,text="Class Levels",padding=10)
        right.pack(side="left",fill="both",expand=True)
        ttk.Label(
            right,
            text=(
                "Edit one or more class levels and click Apply Class Levels. Values are stored as unsigned 32-bit integers; "
                "the editor does not assume level 10 is a maximum."
            ),
            wraplength=620
        ).pack(anchor="w",pady=(0,10))

        self.class_level_vars={}
        grid=ttk.Frame(right);grid.pack(anchor="w",fill="x")
        for row,name in enumerate(("Miner","Crafter","Pilot","Knight")):
            ttk.Label(grid,text=f"{name} level",width=18).grid(row=row,column=0,sticky="w",pady=4)
            var=tk.StringVar();self.class_level_vars[name]=var
            ttk.Entry(grid,textvariable=var,width=18).grid(row=row,column=1,sticky="w",padx=(6,12),pady=4)
            ttk.Label(grid,text=f"save field {CLASS_LEVEL_FIELDS[name]}").grid(row=row,column=2,sticky="w",pady=4)

        actions=ttk.Frame(right);actions.pack(fill="x",pady=(14,6))
        ttk.Button(actions,text="Apply Class Levels",command=self.apply_class_levels).pack(side="left")
        ttk.Button(actions,text="Reload Stats",command=self.refresh_stats).pack(side="left",padx=6)

        backup=ttk.Frame(right);backup.pack(fill="x",pady=(10,4))
        ttk.Button(backup,text="Undo Last Stats Edit (.prev)",command=self.undo_stats_edit).pack(side="left")
        ttk.Button(backup,text="Restore Original Stats (.bak)",command=self.restore_stats_backup).pack(side="left",padx=6)

        ttk.Label(
            right,
            text=(
                "Safety: the first editor write preserves the original 93_stats.sav as .bak. Every later write also refreshes .prev, "
                "so the immediately preceding stats file can be restored."
            ),
            wraplength=620
        ).pack(anchor="w",pady=(8,0))

        self.stats_path=None
        self.stats_values={}
        self.stats_offsets={}

    def refresh_stats(self):
        try:
            p=find_global_save_file(self.root,"93_stats.sav")
            self.stats_path=p
            self.stats_values={};self.stats_offsets={}
            if hasattr(self,"stats_tree"):
                self.stats_tree.delete(*self.stats_tree.get_children())
            if not p:
                self.stats_status.set(
                    "93_stats.sav was not found. Select the normal save folder, its nested '0' folder, or a numbered slot folder."
                )
                for var in getattr(self,"class_level_vars",{}).values():var.set("")
                return

            d=dec(p)
            values,offsets=parse_player_stats(d)
            self.stats_values=values;self.stats_offsets=offsets

            for fid in range(1,7):
                self.stats_tree.insert("","end",values=(fid,PLAYER_STATS_LABELS[fid],f"{values[fid]:,}"))
            for name,fid in CLASS_LEVEL_FIELDS.items():
                self.class_level_vars[name].set(str(values[fid]))

            self.stats_status.set(
                f"Loaded {p} | Characters: {values[1]:,} | Deleted: {values[6]:,} | "
                f"Class levels — Miner {values[7]}, Crafter {values[8]}, Pilot {values[9]}, Knight {values[10]}"
            )
        except Exception as e:
            self.stats_path=None
            self.stats_values={};self.stats_offsets={}
            self.stats_status.set(f"Player stats error: {e}")

    def apply_class_levels(self):
        try:
            p=self.stats_path or find_global_save_file(self.root,"93_stats.sav")
            if not p:
                raise RuntimeError("93_stats.sav was not found from the selected save location.")

            requested={}
            for name,fid in CLASS_LEVEL_FIELDS.items():
                raw=self.class_level_vars[name].get().strip()
                if raw=="":
                    raise ValueError(f"Enter a level for {name}.")
                try:value=int(raw,10)
                except Exception:raise ValueError(f"{name} level must be a whole number.")
                if not (0<=value<=4294967295):
                    raise ValueError(f"{name} level must be between 0 and 4,294,967,295.")
                requested[fid]=value

            data=bytearray(dec(p))
            old,offsets=parse_player_stats(data)
            changed=[]
            for fid,value in requested.items():
                if old[fid]!=value:
                    struct.pack_into("<I",data,offsets[fid],value)
                    changed.append((fid,old[fid],value))

            if not changed:
                messagebox.showinfo("Apply Class Levels","No class levels changed.")
                return

            # Reparse the complete file before writing and verify the requested
            # values landed in the serializer fields we expect.
            validate_serialized_save(data)
            check,_=parse_player_stats(data)
            for fid,value in requested.items():
                if check[fid]!=value:
                    raise RuntimeError(f"Validation failed for PlayerStats field {fid}.")

            summary="\n".join(
                f"{PLAYER_STATS_LABELS[fid]}: {before} → {after}"
                for fid,before,after in changed
            )
            if not messagebox.askyesno(
                "Apply Class Levels",
                "Write these global class-level changes?\n\n"+summary+"\n\nThe current file will be preserved in .prev and the original baseline in .bak."
            ):
                return

            write(p,data)
            self.refresh_stats()
            messagebox.showinfo("Class Levels Updated",summary)
        except Exception as e:
            messagebox.showerror("Class Level error",str(e))

    def undo_stats_edit(self):
        try:
            p=self.stats_path or find_global_save_file(self.root,"93_stats.sav")
            if not p:raise RuntimeError("93_stats.sav was not found.")
            prev=Path(str(p)+".prev")
            if not prev.is_file():
                messagebox.showinfo("Undo Stats Edit","No .prev backup exists yet for 93_stats.sav.");return
            parse_player_stats(dec(prev))
            if not messagebox.askyesno(
                "Undo Stats Edit",
                "Swap the current 93_stats.sav with its .prev backup?\n\nRunning this again will redo the same change."
            ):return
            current=p.read_bytes();oldprev=prev.read_bytes()
            p.write_bytes(oldprev);prev.write_bytes(current)
            self.refresh_stats()
            messagebox.showinfo("Undo Stats Edit","Restored the previous 93_stats.sav. The replaced version is now in .prev.")
        except Exception as e:
            messagebox.showerror("Undo Stats Edit error",str(e))

    def restore_stats_backup(self):
        try:
            p=self.stats_path or find_global_save_file(self.root,"93_stats.sav")
            if not p:raise RuntimeError("93_stats.sav was not found.")
            bak=Path(str(p)+".bak");prev=Path(str(p)+".prev")
            if not bak.is_file():
                messagebox.showinfo("Restore Original Stats","No .bak baseline exists yet for 93_stats.sav.");return
            parse_player_stats(dec(bak))
            if not messagebox.askyesno(
                "Restore Original Stats",
                "Restore 93_stats.sav from its original .bak baseline?\n\nThe current stats file will first be copied to .prev."
            ):return
            shutil.copy2(p,prev);shutil.copy2(bak,p)
            self.refresh_stats()
            messagebox.showinfo("Restore Original Stats","Restored 93_stats.sav from .bak. The pre-restore version is in .prev.")
        except Exception as e:
            messagebox.showerror("Restore Original Stats error",str(e))

    def build_meta(self):
        f=ttk.Frame(self.meta,padding=12);f.pack(fill='both',expand=True)
        ttk.Label(
            f,
            text=(
                'Per-slot 93_meta.sav details. v1.14 maps the play-time counter, save timestamp, '
                'counted UTF-16 display name, and location/system text. Only the display name is editable; '
                'unknown metadata fields remain untouched.'
            ),wraplength=1280
        ).pack(anchor='w',pady=(0,8))

        self.meta_status=tk.StringVar(value='Slot metadata not loaded yet.')
        ttk.Label(f,textvariable=self.meta_status,anchor='w').pack(fill='x',pady=(0,12))

        details=ttk.LabelFrame(f,text='Selected slot metadata',padding=10)
        details.pack(fill='x')
        self.meta_detail_vars={}
        labels=[
            ('playtime','Play time'),('timestamp','Last-save timestamp'),
            ('location','Location / system text'),('progression','Character level at last game save'),
            ('path','File')
        ]
        for row,(key,label) in enumerate(labels):
            ttk.Label(details,text=label,width=30).grid(row=row,column=0,sticky='w',pady=3)
            var=tk.StringVar();self.meta_detail_vars[key]=var
            ttk.Label(details,textvariable=var).grid(row=row,column=1,sticky='w',pady=3)

        namebox=ttk.LabelFrame(f,text='Display name (93_meta.sav field 12)',padding=10)
        namebox.pack(fill='x',pady=(12,0))
        ttk.Label(
            namebox,
            text='Variable-length UTF-16 editing is supported; the field length is rebuilt and the whole save is structurally validated before writing.',
            wraplength=1100
        ).pack(anchor='w',pady=(0,6))
        row=ttk.Frame(namebox);row.pack(fill='x')
        self.meta_name=tk.StringVar()
        ttk.Entry(row,textvariable=self.meta_name,width=60).pack(side='left')
        ttk.Button(row,text='Apply Display Name',command=self.apply_meta_name).pack(side='left',padx=6)
        ttk.Button(row,text='Reload Slot Details',command=self.refresh_meta).pack(side='left')

        backup=ttk.Frame(namebox);backup.pack(fill='x',pady=(10,0))
        ttk.Button(backup,text='Undo Last Metadata Edit (.prev)',command=self.undo_meta_edit).pack(side='left')
        ttk.Button(backup,text='Restore Original Metadata (.bak)',command=self.restore_meta_backup).pack(side='left',padx=6)
        self.meta_path=None

    def refresh_meta(self):
        try:
            slot=str(self.sa.get()).strip()
            slot_dir=self.slot_paths.get(slot)
            self.meta_path=None
            self.meta_name.set('')
            for var in self.meta_detail_vars.values():var.set('')
            if not slot_dir:
                self.meta_status.set('No save slot selected.')
                return
            p=slot_dir/'93_meta.sav'
            if not p.is_file():
                self.meta_status.set(f'93_meta.sav was not found in slot {slot}.')
                return
            info=parse_slot_meta(dec(p));self.meta_path=p
            seconds=max(0.0,info['playtime_seconds'])
            total=int(seconds)
            hours,rem=divmod(total,3600);minutes,secs=divmod(rem,60)
            frac=seconds-total
            self.meta_detail_vars['playtime'].set(f'{seconds:,.3f} seconds  ({hours}:{minutes:02d}:{secs+frac:06.3f})')
            day,month,year,hour,minute,second=info['timestamp']
            self.meta_detail_vars['timestamp'].set(f'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}')
            self.meta_detail_vars['location'].set(info['location'] or '(empty)')
            self.meta_detail_vars['progression'].set('' if info['progression_value'] is None else str(info['progression_value']))
            self.meta_detail_vars['path'].set(str(p))
            self.meta_name.set(info['display_name'])
            self.meta_status.set(f'Slot {slot} | {info["field_count"]} metadata fields | Display name: {info["display_name"]!r}')
        except Exception as e:
            self.meta_path=None
            self.meta_status.set(f'Slot metadata error: {e}')

    def apply_meta_name(self):
        try:
            p=self.meta_path
            if not p or not Path(p).is_file():
                raise RuntimeError('93_meta.sav is not loaded for the selected slot.')
            name=self.meta_name.get()
            if '\x00' in name:
                raise ValueError('The display name cannot contain a NUL character.')
            if not name.strip():
                if not messagebox.askyesno('Empty Display Name','The new display name is empty. Write it anyway?'):
                    return
            raw=dec(p);before=parse_slot_meta(raw)['display_name']
            if name==before:
                messagebox.showinfo('Display Name','No display-name change was requested.');return
            changed=set_slot_meta_display_name(raw,name)
            after=parse_slot_meta(changed)['display_name']
            if after!=name:raise RuntimeError('Display-name verification failed.')
            if not messagebox.askyesno(
                'Apply Display Name',
                f'Change slot display name?\n\n{before!r} → {name!r}\n\nThe original baseline remains in .bak and the previous file is stored in .prev.'
            ):return
            write(p,changed);self.refresh_meta()
            messagebox.showinfo('Display Name Updated',f'{before!r} → {name!r}')
        except Exception as e:
            messagebox.showerror('Display Name error',str(e))

    def undo_meta_edit(self):
        try:
            p=self.meta_path
            if not p:raise RuntimeError('93_meta.sav is not loaded.')
            p=Path(p);prev=Path(str(p)+'.prev')
            if not prev.is_file():
                messagebox.showinfo('Undo Metadata Edit','No .prev backup exists yet for 93_meta.sav.');return
            parse_slot_meta(dec(prev))
            if not messagebox.askyesno('Undo Metadata Edit','Swap the current 93_meta.sav with its .prev backup?\n\nRunning this again will redo the same change.'):
                return
            current=p.read_bytes();oldprev=prev.read_bytes();p.write_bytes(oldprev);prev.write_bytes(current)
            self.refresh_meta();messagebox.showinfo('Undo Metadata Edit','Restored the previous 93_meta.sav. The replaced version is now in .prev.')
        except Exception as e:messagebox.showerror('Undo Metadata Edit error',str(e))

    def restore_meta_backup(self):
        try:
            p=self.meta_path
            if not p:raise RuntimeError('93_meta.sav is not loaded.')
            p=Path(p);bak=Path(str(p)+'.bak');prev=Path(str(p)+'.prev')
            if not bak.is_file():
                messagebox.showinfo('Restore Original Metadata','No .bak baseline exists yet for 93_meta.sav.');return
            parse_slot_meta(dec(bak))
            if not messagebox.askyesno('Restore Original Metadata','Restore 93_meta.sav from its original .bak baseline?\n\nThe current metadata file will first be copied to .prev.'):
                return
            shutil.copy2(p,prev);shutil.copy2(bak,p);self.refresh_meta()
            messagebox.showinfo('Restore Original Metadata','Restored 93_meta.sav from .bak. The pre-restore version is in .prev.')
        except Exception as e:messagebox.showerror('Restore Original Metadata error',str(e))

    def build_quests(self):
        f=ttk.Frame(self.quests,padding=10);f.pack(fill='both',expand=True)
        ttk.Label(
            f,
            text=(
                '93_quests.sav contains the selected slot\'s generated side quests. v1.15 maps the quest-type enum, nested task records, '
                'positions, and the two fixed reward fields. Reward fields 9/10 are deliberately labelled Raw Reward A/B until the exact '
                'Qbits-versus-XP ordering is runtime-confirmed. The TaskCfg catalog lists story definitions; current story state is not identified; '
                'direct story advancement remains read-only because world/story state is distributed across several saves.'
            ),wraplength=1460
        ).pack(anchor='w',pady=(0,7))

        bar=ttk.Frame(f);bar.pack(fill='x',pady=(0,6))
        ttk.Button(bar,text='Reload Quest Data',command=self.refresh_quests).pack(side='left',padx=(0,5))
        ttk.Button(bar,text='Edit Raw Reward Values',command=self.edit_quest_rewards).pack(side='left',padx=5)
        ttk.Button(bar,text='Abandon Selected Quest',command=self.abandon_selected_quest).pack(side='left',padx=5)
        ttk.Button(bar,text='Undo Last Quest Edit (.prev)',command=self.undo_quest_edit).pack(side='right',padx=4)
        ttk.Button(bar,text='Restore Original Quests (.bak)',command=self.restore_quest_backup).pack(side='right',padx=4)
        self.quest_status=tk.StringVar(value='Quest data not scanned yet.')
        ttk.Label(f,textvariable=self.quest_status,anchor='w').pack(fill='x',pady=(0,7))

        qf=ttk.LabelFrame(f,text='Active / saved generated quests',padding=6);qf.pack(fill='both',expand=True)
        self.quest_tree=ttk.Treeview(qf,columns=('index','type','ra','rb','tasks','target','position','ids'),show='headings',height=8)
        for c,title,w in [
            ('index','#',42),('type','Quest type',190),('ra','Raw reward A',95),('rb','Raw reward B',95),
            ('tasks','Tasks',55),('target','Task / target data',360),('position','Position',240),('ids','Raw IDs / state',360)
        ]:
            self.quest_tree.heading(c,text=title);self.quest_tree.column(c,width=w,anchor='w')
        self.quest_tree.pack(fill='both',expand=True)

        sf=ttk.LabelFrame(f,text='Current story task + TaskCfg progression catalog (read-only)',padding=6);sf.pack(fill='both',expand=True,pady=(10,0))
        top=ttk.Frame(sf);top.pack(fill='x')
        self.story_current=tk.StringVar(value='Current story task not loaded.')
        ttk.Label(top,textvariable=self.story_current,anchor='w').pack(side='left',fill='x',expand=True)
        ttk.Label(top,text=f'Loaded TaskCfg definitions: {len(self.progression_catalog):,}').pack(side='right',padx=(8,0))
        search=ttk.Frame(sf);search.pack(fill='x',pady=(6,0))
        ttk.Label(search,text='Search progression:').pack(side='left')
        self.story_query=tk.StringVar();ttk.Entry(search,textvariable=self.story_query,width=46).pack(side='left',padx=5)
        self.story_tree=ttk.Treeview(sf,columns=('current','id','step','chapter','category','description','arg','needed','reward'),show='headings',height=9)
        for c,title,w in [
            ('current','Current',62),('id','Task ID',60),('step','Story step',230),('chapter','Chapter',65),
            ('category','Category',180),('description','Description token',150),('arg','Argument',250),
            ('needed','Needed items',300),('reward','Config reward',240)
        ]:
            self.story_tree.heading(c,text=title);self.story_tree.column(c,width=w,anchor='w')
        self.story_tree.pack(fill='both',expand=True,pady=(6,0))
        self.story_query.trace_add('write',lambda *_:self.story_search())
        self.quest_path=None;self.quest_meta={};self.current_story_task=None
        self.story_search()

    def story_search(self):
        if not hasattr(self,'story_tree'):return
        self.story_tree.delete(*self.story_tree.get_children())
        q=self.story_query.get().strip().lower() if hasattr(self,'story_query') else ''
        current=getattr(self,'current_story_task',None)
        for tid,cfg in sorted(self.progression_catalog.items()):
            needed=', '.join(f'{name} x{qty}' if qty is not None else name for name,qty in cfg.get('needed_items',[]))
            reward=''
            if cfg.get('reward_item'):
                reward=cfg.get('reward_item','')
                if cfg.get('reward_quantity') is not None:reward+=f" x{cfg['reward_quantity']}"
            hay=' '.join(str(x) for x in [tid,cfg.get('story_step',''),cfg.get('category',''),cfg.get('description',''),cfg.get('arg',''),needed,reward]).lower()
            if q and q not in hay:continue
            self.story_tree.insert('', 'end',values=(
                'YES' if tid==current else '',tid,cfg.get('story_step',''),
                '' if cfg.get('chapter') is None else cfg.get('chapter'),cfg.get('category',''),cfg.get('description',''),
                cfg.get('arg',''),needed,reward
            ))

    def refresh_quests(self):
        try:
            if hasattr(self,'quest_tree'):self.quest_tree.delete(*self.quest_tree.get_children())
            self.quest_meta={};self.quest_path=None;self.current_story_task=None
            selected=str(self.sa.get()).strip() if hasattr(self,'sa') else ''
            slot_dir=self.slot_paths.get(selected) if hasattr(self,'slot_paths') else None
            if not slot_dir:
                self.quest_status.set('No save slot is selected.')
                self.story_current.set('Current story task not loaded.')
                self.story_search();return
            p=slot_dir/'93_quests.sav';self.quest_path=p
            if not p.exists():
                self.quest_status.set(f'93_quests.sav was not found in {slot_dir}.')
            else:
                info=parse_player_quests(dec(p))
                for row in info['rows']:
                    iid=f"quest_{row['index']}"
                    tasks=[]
                    for t in row['tasks']:
                        bit=f"type {t['type']}"
                        if t.get('target'):bit+=f": {t['target']}"
                        if t.get('value') is not None:bit+=f" ({t['value']})"
                        tasks.append(bit)
                    pos=row.get('position')
                    pos_text='' if not pos else f'{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}'
                    ids=(f"f5={row.get('raw5')} f6={row.get('raw6')} f7={row.get('raw7')} "
                         f"f16={row.get('raw16')} f17={row.get('raw17')} f18={row.get('raw18')}")
                    self.quest_tree.insert('', 'end',iid=iid,values=(
                        row['index'],row['type_name'],row['reward_a'],row['reward_b'],row['task_count'],
                        ' | '.join(tasks),pos_text,ids
                    ))
                    self.quest_meta[iid]=row
                self.quest_status.set(
                    f'Loaded {p} | {info["count"]} saved generated quest(s) | '
                    'Abandon removes one complete PlayerQuest array element and validates the entire save.'
                )

            self.current_story_task=None
            self.story_current.set('Story definitions catalog. Current story task is not identified; metadata field 13 is character level.')
            self.story_search()
        except Exception as e:
            self.quest_path=None;self.quest_meta={};self.current_story_task=None
            self.quest_status.set(f'Quest scan error: {e}')
            self.story_current.set('Current story task unavailable because quest/story scanning failed.')
            self.story_search()

    def edit_quest_rewards(self):
        try:
            sel=self.quest_tree.selection()
            if not sel:
                messagebox.showinfo('Edit Quest Rewards','Select a quest first.');return
            meta=self.quest_meta.get(sel[0])
            if not meta or not self.quest_path:
                raise RuntimeError('The selected quest metadata is unavailable. Reload the quest data.')
            a=simpledialog.askinteger(
                'Raw Quest Reward A',
                f"{meta['type_name']}\n\nCurrent raw field 9 value: {meta['reward_a']}\n\nNew unsigned value:",
                parent=self.w,minvalue=0,maxvalue=4294967295,initialvalue=meta['reward_a']
            )
            if a is None:return
            b=simpledialog.askinteger(
                'Raw Quest Reward B',
                f"{meta['type_name']}\n\nCurrent raw field 10 value: {meta['reward_b']}\n\nNew unsigned value:\n\n"
                'Note: fields 9 and 10 strongly behave like the two quest rewards, but their exact Qbits/XP ordering is not yet runtime-confirmed.',
                parent=self.w,minvalue=0,maxvalue=4294967295,initialvalue=meta['reward_b']
            )
            if b is None:return
            if a==meta['reward_a'] and b==meta['reward_b']:
                messagebox.showinfo('Edit Quest Rewards','No reward-value change was requested.');return
            if not messagebox.askyesno(
                'Confirm Raw Quest Reward Edit',
                f"{meta['type_name']}\n\nField 9: {meta['reward_a']} -> {a}\nField 10: {meta['reward_b']} -> {b}\n\n"
                'This is structurally validated, but the exact Qbits/XP ordering remains experimental. Continue?'
            ):return
            raw=dec(self.quest_path)
            changed=set_quest_reward_values(raw,meta['target_offset'],a,b)
            write(self.quest_path,changed);self.refresh()
            messagebox.showinfo('Quest Rewards Updated','Quest reward fields were updated and the complete save structure was validated.\n\n.bak and .prev recovery copies are available.')
        except Exception as e:messagebox.showerror('Edit Quest Rewards error',str(e))

    def abandon_selected_quest(self):
        try:
            sel=self.quest_tree.selection()
            if not sel:
                messagebox.showinfo('Abandon Quest','Select a quest first.');return
            meta=self.quest_meta.get(sel[0])
            if not meta or not self.quest_path:
                raise RuntimeError('The selected quest metadata is unavailable. Reload the quest data.')
            taskinfo=' | '.join(t.get('target','') for t in meta.get('tasks',[]) if t.get('target'))
            if not messagebox.askyesno(
                'Abandon Selected Quest',
                f"Remove this complete PlayerQuest entry?\n\nType: {meta['type_name']}\n"
                f"Task target: {taskinfo or '(none stored)'}\n\n"
                'The array count and serialized length will be updated and validated. This is an experimental save-level equivalent of abandoning/removing the generated quest.'
            ):return
            raw=dec(self.quest_path)
            changed,old_count,new_count,delta,_=remove_quest_structural(raw,meta['target_offset'])
            write(self.quest_path,changed);self.refresh()
            messagebox.showinfo('Quest Removed',f'Saved quest count: {old_count} -> {new_count}\nRemoved {delta} decoded bytes.\n\n.bak and .prev recovery copies are available.')
        except Exception as e:messagebox.showerror('Abandon Quest error',str(e))

    def undo_quest_edit(self):
        try:
            p=getattr(self,'quest_path',None)
            if not p or not Path(p).exists():
                messagebox.showinfo('Undo Quest Edit','No selected 93_quests.sav is available.');return
            p=Path(p);prev=Path(str(p)+'.prev')
            if not prev.exists():
                messagebox.showinfo('Undo Quest Edit','No .prev backup exists yet for this quest save.');return
            if not messagebox.askyesno('Undo Quest Edit','Swap the current 93_quests.sav with its .prev backup?\n\nRunning this again will redo the same change.'):return
            temp=Path(str(p)+'.undo_swap_tmp');shutil.copy2(p,temp);shutil.copy2(prev,p);shutil.copy2(temp,prev);temp.unlink(missing_ok=True);self.refresh()
        except Exception as e:messagebox.showerror('Undo Quest Edit error',str(e))

    def restore_quest_backup(self):
        try:
            p=getattr(self,'quest_path',None)
            if not p or not Path(p).exists():
                messagebox.showinfo('Restore Original Quests','No selected 93_quests.sav is available.');return
            p=Path(p);bak=Path(str(p)+'.bak');prev=Path(str(p)+'.prev')
            if not bak.exists():
                messagebox.showinfo('Restore Original Quests','No .bak baseline exists yet for this quest save.');return
            if not messagebox.askyesno('Restore Original Quests','Restore the original .bak baseline for 93_quests.sav?\n\nThe current version will first be copied to .prev.'):return
            shutil.copy2(p,prev);shutil.copy2(bak,p);self.refresh()
        except Exception as e:messagebox.showerror('Restore Original Quests error',str(e))

    def build_ships(self):
        f=ttk.Frame(self.ships,padding=10);f.pack(fill='both',expand=True)
        ttk.Label(
            f,
            text=(
                'v1.14 structurally parses the PlayerShipCollection inside 93_client_state.sav. '
                'Installed components are joined to VehicleComponentCfg by config filename, exposing the real component role and vehicle class. '
                'Component replacement resizes the saved identifier and fixes every enclosing container length. '
                'Only same-role + same-vehicle-class replacements are offered by default. Ship numeric fields remain read-only until their runtime semantics are proven.'
            ),
            wraplength=1480,justify='left'
        ).pack(anchor='w',pady=(0,8))

        bar=ttk.Frame(f);bar.pack(fill='x',pady=(0,6))
        ttk.Button(bar,text='Reload Ship Data',command=self.refresh_ships).pack(side='left',padx=(0,5))
        ttk.Button(bar,text='Replace Selected Component',command=self.replace_ship_component).pack(side='left',padx=5)
        ttk.Button(bar,text='Undo Last Ship Edit (.prev)',command=self.undo_ship_edit).pack(side='right',padx=4)
        ttk.Button(bar,text='Restore Original Ship Save (.bak)',command=self.restore_ship_backup).pack(side='right',padx=4)
        self.ship_status=tk.StringVar(value='Ship data not scanned yet.')
        ttk.Label(f,textvariable=self.ship_status,anchor='w').pack(fill='x',pady=(0,7))

        sf=ttk.LabelFrame(f,text='Saved ships',padding=5);sf.pack(fill='x',pady=(0,7))
        self.ship_tree=ttk.Treeview(
            sf,columns=('ship','tag','components','deployables','cargo','f12','f24','energy','voxel'),show='headings',height=3
        )
        for c,title,w in [
            ('ship','Ship',55),('tag','Serializer Tag',95),('components','Components',90),
            ('deployables','Deployables',90),('cargo','Cargo Items',85),
            ('f12','Field 12',85),('f24','Field 24',85),('energy','Field 22 Pair',150),('voxel','ship_1.vx',170)
        ]:
            self.ship_tree.heading(c,text=title);self.ship_tree.column(c,width=w)
        self.ship_tree.pack(fill='x')

        cf=ttk.LabelFrame(f,text='Installed ship components',padding=5);cf.pack(fill='both',expand=True,pady=(0,7))
        self.ship_component_tree=ttk.Treeview(
            cf,columns=('ship','slot','identifier','role','class','tier','price','raw2','attributes'),show='headings',height=10
        )
        for c,title,w in [
            ('ship','Ship',50),('slot','Saved Slot',75),('identifier','Identifier',310),
            ('role','Component Role',110),('class','Vehicle Class',115),('tier','Tier',50),
            ('price','Base Price',75),('raw2','Raw Field 2',85),('attributes','Config Attributes',600)
        ]:
            self.ship_component_tree.heading(c,text=title);self.ship_component_tree.column(c,width=w)
        self.ship_component_tree.pack(fill='both',expand=True)
        self.ship_component_tree.bind('<Double-1>',lambda e:self.replace_ship_component())

        df=ttk.LabelFrame(f,text='Ship deployables (read-only)',padding=5);df.pack(fill='both',expand=True)
        self.ship_deploy_tree=ttk.Treeview(
            df,columns=('ship','entity','identifier','condition','tag'),show='headings',height=6
        )
        for c,title,w in [
            ('ship','Ship',50),('entity','Entity ID',95),('identifier','Identifier',330),
            ('condition','Raw Field 5',110),('tag','Serializer Tag',100)
        ]:
            self.ship_deploy_tree.heading(c,text=title);self.ship_deploy_tree.column(c,width=w)
        self.ship_deploy_tree.pack(fill='both',expand=True)
        self.ship_component_meta={};self.ship_path=None

    def refresh_ships(self):
        if not hasattr(self,'ship_tree'):
            return
        self.ship_tree.delete(*self.ship_tree.get_children())
        self.ship_component_tree.delete(*self.ship_component_tree.get_children())
        self.ship_deploy_tree.delete(*self.ship_deploy_tree.get_children())
        self.ship_component_meta={};self.ship_path=None
        try:
            selected=str(self.sa.get()).strip();slot_dir=self.slot_paths.get(selected)
            if not slot_dir:
                self.ship_status.set('No save slot is selected.');return
            p=slot_dir/'93_client_state.sav';self.ship_path=p
            if not p.is_file():
                self.ship_status.set('93_client_state.sav was not found in the selected slot.');return
            d=dec(p);ships=parse_player_ships(d)
            vx=slot_dir/'ship_1.vx'
            voxel_text=f'{vx.stat().st_size:,} bytes' if vx.is_file() else 'not found'
            comp_rows=dep_rows=cargo_total=matched=0
            for ship in ships:
                ep=ship.get('energy_pair')
                energy='' if ep is None else f'{ep[0]:g} / {ep[1]:g}'
                self.ship_tree.insert('', 'end', values=(
                    ship['index']+1,ship['tag'],len(ship['components']),len(ship['deployables']),len(ship['cargo']),
                    '' if ship['field12'] is None else f"{ship['field12']:g}",
                    '' if ship['field24'] is None else f"{ship['field24']:g}",energy,voxel_text
                ))
                cargo_total+=len(ship['cargo'])
                for comp in ship['components']:
                    cfg=self.vehicle_component_catalog.get(comp['identifier'],{})
                    if cfg:matched+=1
                    iid=f'shipcomp_{comp_rows}'
                    attrs=cfg.get('attributes_text','')
                    self.ship_component_tree.insert('', 'end', iid=iid, values=(
                        ship['index']+1,'' if comp['slot'] is None else comp['slot'],comp['identifier'],
                        cfg.get('component_type',''),cfg.get('component_class',''),
                        '' if cfg.get('tier') is None else cfg.get('tier'),
                        '' if cfg.get('base_price') is None else f"{cfg.get('base_price'):g}",
                        '' if comp.get('field2') is None else f"{comp.get('field2'):g}",attrs
                    ))
                    self.ship_component_meta[iid]={
                        'path':str(p),'ship_index':ship['index'],'identifier':comp['identifier'],
                        'identifier_header':comp['identifier_header'],'slot':comp.get('slot'),
                        'role':cfg.get('component_type',''),'class':cfg.get('component_class','')
                    }
                    comp_rows+=1
                for dep in ship['deployables']:
                    self.ship_deploy_tree.insert('', 'end', values=(
                        ship['index']+1,'' if dep.get('entity_id') is None else dep.get('entity_id'),
                        dep.get('identifier',''),'' if dep.get('condition') is None else f"{dep.get('condition'):g}",dep.get('tag','')
                    ));dep_rows+=1
            self.ship_status.set(
                f'Slot {selected} | {len(ships)} saved ship(s) | {comp_rows} installed components '
                f'({matched} matched to VehicleComponentCfg) | {dep_rows} deployables | {cargo_total} ship-cargo item record(s) | '
                f'ship_1.vx: {voxel_text} | Component definitions loaded: {len(self.vehicle_component_catalog):,}'
            )
        except Exception as e:
            self.ship_status.set(f'Ship scan error: {e}')

    def _pick_ship_component_replacement(self,old_ident):
        current=self.vehicle_component_catalog.get(old_ident,{})
        role=current.get('component_type','');vclass=current.get('component_class','')
        if not current:
            messagebox.showinfo(
                'Replace Ship Component',
                'The selected component could not be matched to a VehicleComponentCfg. v1.14 will not guess a compatible replacement.'
            );return None
        candidates=[(ident,cfg) for ident,cfg in self.vehicle_component_catalog.items() if ident!=old_ident]
        if not candidates:
            return None
        top=tk.Toplevel(self.w);top.title('Choose Ship Component');top.geometry('1180x650');top.transient(self.w);top.grab_set()
        outer=ttk.Frame(top,padding=10);outer.pack(fill='both',expand=True)
        ttk.Label(
            outer,text=(
                f'Current: {old_ident}\nRole: {role or "?"} | Vehicle class: {vclass or "?"}\n'
                'Same role + same vehicle class is enabled by default. Disabling it is experimental because the saved ship also contains cached numeric state whose exact rebuild behavior is not yet proven.'
            ),wraplength=1120,justify='left'
        ).pack(anchor='w',pady=(0,7))
        row=ttk.Frame(outer);row.pack(fill='x')
        query=tk.StringVar();compatible=tk.BooleanVar(value=True)
        ttk.Label(row,text='Search:').pack(side='left');entry=ttk.Entry(row,textvariable=query,width=45);entry.pack(side='left',padx=5)
        ttk.Checkbutton(row,text='Same role + vehicle class only',variable=compatible).pack(side='left',padx=12)
        tree=ttk.Treeview(outer,columns=('id','role','class','tier','price','delta','attrs'),show='headings')
        for c,title,w in [
            ('id','Identifier',300),('role','Role',100),('class','Vehicle Class',110),('tier','Tier',50),
            ('price','Base Price',75),('delta','Size Δ',60),('attrs','Config Attributes',430)
        ]:
            tree.heading(c,text=title);tree.column(c,width=w)
        tree.pack(fill='both',expand=True,pady=7)
        status=tk.StringVar();ttk.Label(outer,textvariable=status).pack(anchor='w')
        buttons=ttk.Frame(outer);buttons.pack(fill='x',pady=(8,0));result={'value':None}
        old_n=len(old_ident.encode('utf-8'))
        def refill(*_):
            tree.delete(*tree.get_children());q=query.get().strip().lower();shown=0
            for ident,cfg in sorted(candidates,key=lambda x:(x[1].get('component_type',''),x[1].get('component_class',''),x[1].get('tier') or -1,x[0])):
                if compatible.get() and (cfg.get('component_type','')!=role or cfg.get('component_class','')!=vclass):
                    continue
                hay=' '.join([ident,cfg.get('component_type',''),cfg.get('component_class',''),cfg.get('attributes_text','')]).lower()
                if q and q not in hay:continue
                delta=len(ident.encode('utf-8'))-old_n
                tree.insert('', 'end', iid=f'c{shown}', values=(
                    ident,cfg.get('component_type',''),cfg.get('component_class',''),
                    '' if cfg.get('tier') is None else cfg.get('tier'),
                    '' if cfg.get('base_price') is None else f"{cfg.get('base_price'):g}",f'{delta:+d}',cfg.get('attributes_text','')
                ));shown+=1
            status.set(f'{shown} component definitions shown')
        def choose(*_):
            sel=tree.selection()
            if not sel:return
            result['value']=tree.item(sel[0],'values')[0];top.destroy()
        ttk.Button(buttons,text='Use Selected Component',command=choose).pack(side='right',padx=4)
        ttk.Button(buttons,text='Cancel',command=top.destroy).pack(side='right',padx=4)
        query.trace_add('write',refill);compatible.trace_add('write',refill);tree.bind('<Double-1>',choose)
        refill();entry.focus_set();self.w.wait_window(top)
        return result['value']

    def replace_ship_component(self):
        try:
            sel=self.ship_component_tree.selection()
            if not sel:
                messagebox.showinfo('Replace Ship Component','Select an installed ship component first.');return
            meta=self.ship_component_meta.get(sel[0])
            if not meta:raise RuntimeError('Could not identify the selected ship-component record.')
            if not self.vehicle_component_catalog:
                messagebox.showinfo('Replace Ship Component','Select the extracted game configs folder when starting the editor.');return
            old_ident=meta['identifier'];new_ident=self._pick_ship_component_replacement(old_ident)
            if not new_ident or new_ident==old_ident:return
            old_cfg=self.vehicle_component_catalog.get(old_ident,{});new_cfg=self.vehicle_component_catalog.get(new_ident,{})
            compatible=(old_cfg.get('component_type')==new_cfg.get('component_type') and old_cfg.get('component_class')==new_cfg.get('component_class'))
            old_n=len(old_ident.encode('utf-8'));new_n=len(new_ident.encode('utf-8'))
            if not messagebox.askyesno(
                'Confirm Ship Component Replacement',
                f'Replace installed component:\n\n{old_ident}\n\nwith:\n\n{new_ident}\n\n'
                f"Role: {old_cfg.get('component_type','?')} → {new_cfg.get('component_type','?')}\n"
                f"Vehicle class: {old_cfg.get('component_class','?')} → {new_cfg.get('component_class','?')}\n"
                f'Identifier size: {old_n} → {new_n} bytes ({new_n-old_n:+d})\n'
                f"Compatibility filter: {'MATCH' if compatible else 'EXPERIMENTAL MISMATCH'}\n\n"
                'The editor will resize only the component identifier field, update every enclosing serializer length, reparse the entire ship collection, and validate the full known save tree before writing. '
                'The game may also keep derived/cached ship attributes, so component effects should be verified in-game. Continue?'
            ):return
            p=Path(meta['path']);before=dec(p);before_ships=parse_player_ships(before)
            data,delta,depth=replace_counted_utf8_field_structural(before,meta['identifier_header'],old_ident,new_ident,expected_fid=1)
            after_ships=parse_player_ships(data)
            if len(after_ships)!=len(before_ships):
                raise RuntimeError('Ship count changed during component replacement. No data was written.')
            before_components=sum(len(x['components']) for x in before_ships);after_components=sum(len(x['components']) for x in after_ships)
            if before_components!=after_components:
                raise RuntimeError('Installed-component count changed during replacement. No data was written.')
            if not any(c['identifier']==new_ident for sh in after_ships for c in sh['components']):
                raise RuntimeError('Replacement component was not found after reparsing. No data was written.')
            write(p,data);self.refresh()
            messagebox.showinfo(
                'Ship Component Replaced',
                f'{old_ident}\n→ {new_ident}\n\nDecoded size change: {delta:+d} bytes.\n'
                f'Updated {depth} enclosing length field(s).\nShip collection and full known save structure both validated.'
            )
        except Exception as e:
            messagebox.showerror('Replace Ship Component error',str(e))

    def undo_ship_edit(self):
        try:
            p=self.ship_path
            if not p or not Path(p).is_file():
                messagebox.showinfo('Undo Ship Edit','No selected 93_client_state.sav is available.');return
            p=Path(p);prev=Path(str(p)+'.prev')
            if not prev.is_file():
                messagebox.showinfo('Undo Ship Edit','No .prev backup exists yet for this client-state save.');return
            parse_player_ships(dec(prev))
            if not messagebox.askyesno('Undo Ship Edit','Swap the current 93_client_state.sav with its .prev backup?\n\nRunning this again will redo the same change.'):return
            current=p.read_bytes();oldprev=prev.read_bytes();p.write_bytes(oldprev);prev.write_bytes(current);self.refresh()
        except Exception as e:messagebox.showerror('Undo Ship Edit error',str(e))

    def restore_ship_backup(self):
        try:
            p=self.ship_path
            if not p or not Path(p).is_file():
                messagebox.showinfo('Restore Original Ship Save','No selected 93_client_state.sav is available.');return
            p=Path(p);bak=Path(str(p)+'.bak');prev=Path(str(p)+'.prev')
            if not bak.is_file():
                messagebox.showinfo('Restore Original Ship Save','No .bak baseline exists yet for this client-state save.');return
            parse_player_ships(dec(bak))
            if not messagebox.askyesno('Restore Original Ship Save','Restore the original .bak baseline for 93_client_state.sav?\n\nThe current version will first be copied to .prev.'):return
            shutil.copy2(p,prev);shutil.copy2(bak,p);self.refresh()
        except Exception as e:messagebox.showerror('Restore Original Ship Save error',str(e))

    def build_world(self):
        f=ttk.Frame(self.world,padding=10);f.pack(fill='both',expand=True)
        ttk.Label(f,text=(
            'Item records found in the selected slot\'s numbered world saves. '
            'Location shows the containing world object, its saved ID, and position when available. '
            'Quantity and float condition/charge can be edited without changing record size. '
            'Other fields remain unchanged.'
        ),wraplength=1450).pack(anchor='w',pady=(0,8))
        controls=ttk.Frame(f);controls.pack(fill='x',pady=(0,7))
        ttk.Label(controls,text='File').pack(side='left')
        self.world_file=tk.StringVar(value='All world files')
        self.world_file_box=ttk.Combobox(controls,textvariable=self.world_file,width=26,state='readonly')
        self.world_file_box.pack(side='left',padx=(5,16))
        ttk.Label(controls,text='Find item').pack(side='left')
        self.world_query=tk.StringVar()
        ttk.Entry(controls,textvariable=self.world_query,width=48).pack(side='left',padx=5)
        ttk.Button(controls,text='Reload World Items',command=self.refresh_world).pack(side='left',padx=10)
        actions=ttk.Frame(f);actions.pack(fill='x',pady=(0,7))
        ttk.Button(actions,text='Set Quantity',command=self.edit_world_quantity).pack(side='left',padx=(0,6))
        ttk.Button(actions,text='Edit Condition / Charge',command=self.edit_world_condition).pack(side='left',padx=(0,6))
        ttk.Button(actions,text='Undo Last World Edit (.prev)',command=self.undo_world_edit).pack(side='left',padx=(18,6))
        ttk.Button(actions,text='Restore Original World Save (.bak)',command=self.restore_world_original).pack(side='left')
        self.world_status=tk.StringVar(value='World items not loaded yet.')
        ttk.Label(f,textvariable=self.world_status,anchor='w').pack(fill='x',pady=(0,7))
        table=ttk.Frame(f);table.pack(fill='both',expand=True)
        self.world_tree=ttk.Treeview(table,columns=('file','location','identifier','type','tier','quantity','condition','offset'),show='headings')
        for key,title,width in [
            ('file','World save',160),('location','Location / container',410),
            ('identifier','Item identifier',360),('type','Config type',160),
            ('tier','Tier',50),('quantity','Quantity',80),
            ('condition','Condition / charge',135),('offset','Decoded offset',110),
        ]:
            self.world_tree.heading(key,text=title)
            self.world_tree.column(key,width=width,anchor='w')
        scroll=ttk.Scrollbar(table,orient='vertical',command=self.world_tree.yview)
        self.world_tree.configure(yscrollcommand=scroll.set)
        self.world_tree.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        self.world_rows=[]
        self.world_row_meta={}
        self.world_file_box.bind('<<ComboboxSelected>>',lambda _event:self.world_filter())
        self.world_query.trace_add('write',lambda *_:self.world_filter())
        self.world_tree.bind('<Double-1>',lambda _event:self.edit_world_quantity())

    def refresh_world(self):
        self.world_rows=[]
        slot_dir=self.slot_paths.get(str(self.sa.get()).strip())
        files=[]
        errors=[]
        if slot_dir:
            files=sorted(p for p in slot_dir.glob('*.sav')
                         if re.fullmatch(r'93_3[0-9a-fA-F]{8}\.sav',p.name))
        for p in files:
            try:
                data=self.cache.get(p)
                if data is None:
                    data=dec(p)
                validate_world_save_envelope(data)
                for row in world_item_locations(data,world_item_records(data)):
                    row['file']=p.name
                    row['path']=str(p)
                    self.world_rows.append(row)
            except Exception as exc:
                errors.append(f'{p.name}: {exc}')
        choices=['All world files']+[p.name for p in files]
        self.world_file_box['values']=choices
        if self.world_file.get() not in choices:
            self.world_file.set('All world files')
        self.world_filter()
        if not slot_dir:
            self.world_status.set('No save slot selected.')
        else:
            summary=f'{len(files)} world saves | {len(self.world_rows)} item records | Slot: {slot_dir}'
            if errors:
                summary+=f' | {len(errors)} file errors: '+ '; '.join(errors[:2])
            self.world_status.set(summary)

    def world_filter(self):
        if not hasattr(self,'world_tree'):
            return
        self.world_tree.delete(*self.world_tree.get_children())
        self.world_row_meta={}
        selected=self.world_file.get()
        query=self.world_query.get().strip().casefold()
        for row in self.world_rows:
            if selected!='All world files' and row['file']!=selected:
                continue
            if query and query not in row['identifier'].casefold():
                continue
            cfg=self.item_catalog.get(row['identifier'],{})
            condition=(f'{float(row["condition"]):.2f}' if row['condition_type']==10
                       else str(row['condition']))
            iid=f'world_{len(self.world_row_meta)}'
            self.world_tree.insert('', 'end', iid=iid, values=(
                row['file'],row['location'],row['identifier'],cfg.get('type','') or '',
                '' if cfg.get('tier') is None else cfg['tier'],
                row['quantity'],condition,row['offset'],
            ))
            self.world_row_meta[iid]=row

    def _selected_world_row(self):
        selected=self.world_tree.selection()
        if not selected:
            raise ValueError('Select a world item first.')
        row=self.world_row_meta.get(selected[0])
        if row is None:
            raise ValueError('Selected world item is stale. Reload the slot and try again.')
        return row

    def _selected_world_file(self):
        selected=self.world_tree.selection()
        if selected:
            row=self.world_row_meta.get(selected[0])
            if row:
                return Path(row['path'])
        name=self.world_file.get()
        if name=='All world files':
            raise ValueError('Select an item or choose one world save in the File filter first.')
        slot_dir=self.slot_paths.get(str(self.sa.get()).strip())
        if not slot_dir or not re.fullmatch(r'93_3[0-9a-fA-F]{8}\.sav',name):
            raise ValueError('Choose a valid world save file.')
        path=slot_dir/name
        if not path.is_file():
            raise ValueError('Selected world save no longer exists.')
        return path

    def edit_world_quantity(self):
        try:
            row=self._selected_world_row()
            value=simpledialog.askinteger(
                'Set World Item Quantity',
                f'{row["identifier"]}\n{row["file"]}\n\nCurrent quantity: {row["quantity"]}\nNew quantity:',
                parent=self.w,minvalue=0,maxvalue=4294967295,initialvalue=row['quantity'])
            if value is None or value==row['quantity']:
                return
            p=Path(row['path'])
            before_compressed=p.read_bytes()
            before=dec(p)
            if p.read_bytes()!=before_compressed:
                raise ValueError('World save changed while loading. Reload the slot and try again.')
            changed,old,new=set_world_item_scalar(
                before,row['offset'],row['identifier'],'quantity',row['quantity'],value)
            if not messagebox.askyesno('Confirm World Item Edit',
                f'Change {row["identifier"]} in {p.name} from {old} to {new}?\n\n'
                'The original .bak and one-step .prev recovery copies will be kept.'):
                return
            write_world_verified(p,changed,before_compressed)
            self.world_file.set(p.name)
            self.refresh()
            messagebox.showinfo('World Item Updated',f'{row["identifier"]}: {old} → {new}\n{p.name}')
        except Exception as exc:
            messagebox.showerror('Set World Item Quantity error',str(exc))

    def edit_world_condition(self):
        try:
            row=self._selected_world_row()
            if row['condition_type']!=10:
                messagebox.showinfo('Edit World Condition / Charge',
                    'This item does not store condition/charge as a 32-bit float.')
                return
            old=row['condition']
            value=simpledialog.askfloat(
                'Edit World Condition / Charge',
                f'{row["identifier"]}\n{row["file"]}\n\nCurrent field-5 value: {old:g}\nNew value:',
                parent=self.w,minvalue=0.0,maxvalue=1000000.0,initialvalue=float(old))
            if value is None or value==old:
                return
            p=Path(row['path'])
            before_compressed=p.read_bytes()
            before=dec(p)
            if p.read_bytes()!=before_compressed:
                raise ValueError('World save changed while loading. Reload the slot and try again.')
            changed,old,new=set_world_item_scalar(
                before,row['offset'],row['identifier'],'condition',old,value)
            if not messagebox.askyesno('Confirm World Item Edit',
                f'Change {row["identifier"]} in {p.name} from {old:g} to {new:g}?\n\n'
                'The original .bak and one-step .prev recovery copies will be kept.'):
                return
            write_world_verified(p,changed,before_compressed)
            self.world_file.set(p.name)
            self.refresh()
            messagebox.showinfo('World Item Updated',f'{row["identifier"]}: {old:g} → {new:g}\n{p.name}')
        except Exception as exc:
            messagebox.showerror('Edit World Condition / Charge error',str(exc))

    def undo_world_edit(self):
        try:
            p=self._selected_world_file()
            prev=Path(str(p)+'.prev')
            if not prev.is_file():
                messagebox.showinfo('Undo World Edit',f'No .prev backup exists for {p.name}.')
                return
            validate_world_save_envelope(dec(prev))
            if not messagebox.askyesno('Undo World Edit',
                f'Swap {p.name} with its .prev copy? Running this again will redo the change.'):
                return
            current=p.read_bytes();prior=prev.read_bytes()
            p.write_bytes(prior);prev.write_bytes(current)
            self.world_file.set(p.name)
            self.refresh()
        except Exception as exc:
            messagebox.showerror('Undo World Edit error',str(exc))

    def restore_world_original(self):
        try:
            p=self._selected_world_file()
            bak=Path(str(p)+'.bak');prev=Path(str(p)+'.prev')
            if not bak.is_file():
                messagebox.showinfo('Restore Original World Save',f'No .bak backup exists for {p.name}.')
                return
            validate_world_save_envelope(dec(bak))
            if not messagebox.askyesno('Restore Original World Save',
                f'Restore the original .bak baseline for {p.name}?\n\n'
                'The current save will first be copied to .prev.'):
                return
            shutil.copy2(p,prev);shutil.copy2(bak,p)
            self.world_file.set(p.name)
            self.refresh()
        except Exception as exc:
            messagebox.showerror('Restore Original World Save error',str(exc))

    def build_blueprints(self):
        f=ttk.Frame(self.blueprints,padding=10);f.pack(fill='both',expand=True)
        ttk.Label(
            f,
            text=(
                '93_blueprints.sav is a global PlayerBlueprintCollection. The supplied save contains zero saved BlueprintEntry objects, '
                'so v1.14 inspects the collection but does not invent unlock records. The built-in VehicleBlueprintCfg catalog below '
                'comes from the optional configs folder and is shown separately because those definitions are not proven unlock flags.'
            ),wraplength=1320
        ).pack(anchor='w',pady=(0,7))
        self.bp_status=tk.StringVar(value='Blueprint collection not loaded yet.')
        ttk.Label(f,textvariable=self.bp_status,anchor='w').pack(fill='x',pady=(0,7))
        ttk.Button(f,text='Reload Blueprints',command=self.refresh_blueprints).pack(anchor='w',pady=(0,7))

        saved=ttk.LabelFrame(f,text='Saved BlueprintEntry objects in 93_blueprints.sav',padding=6)
        saved.pack(fill='both',expand=True)
        self.bp_saved_tree=ttk.Treeview(saved,columns=('index','tag','fields','size','strings'),show='headings',height=7)
        for c,title,w in [('index','#',45),('tag','Tag',70),('fields','Fields',70),('size','Bytes',80),('strings','Readable strings',1050)]:
            self.bp_saved_tree.heading(c,text=title);self.bp_saved_tree.column(c,width=w,anchor='w')
        self.bp_saved_tree.pack(fill='both',expand=True)

        cat=ttk.LabelFrame(f,text='Built-in VehicleBlueprintCfg catalog (config definitions, not proven unlock state)',padding=6)
        cat.pack(fill='both',expand=True,pady=(10,0))
        top=ttk.Frame(cat);top.pack(fill='x')
        ttk.Label(top,text=f'Loaded definitions: {len(self.blueprint_catalog):,}').pack(side='left',padx=(0,8))
        self.bp_query=tk.StringVar();ttk.Entry(top,textvariable=self.bp_query,width=48).pack(side='left')
        ttk.Button(top,text='Search',command=self.blueprint_search).pack(side='left',padx=5)
        self.bp_catalog_tree=ttk.Treeview(cat,columns=('name','class','title','weapon','mounts','file'),show='headings',height=10)
        for c,title,w in [('name','Config name',260),('class','Ship class',120),('title','Title string',320),('weapon','Starting weapon',140),('mounts','Max mounts',80),('file','Config file',550)]:
            self.bp_catalog_tree.heading(c,text=title);self.bp_catalog_tree.column(c,width=w,anchor='w')
        self.bp_catalog_tree.pack(fill='both',expand=True,pady=(6,0))
        self.bp_query.trace_add('write',lambda *_:self.blueprint_search())
        self.blueprint_path=None
        self.blueprint_search()

    def blueprint_search(self):
        if not hasattr(self,'bp_catalog_tree'):return
        self.bp_catalog_tree.delete(*self.bp_catalog_tree.get_children())
        q=self.bp_query.get().strip().lower() if hasattr(self,'bp_query') else ''
        for name,bp in sorted(self.blueprint_catalog.items()):
            hay=' '.join([name,bp.get('class',''),bp.get('title',''),bp.get('starting_weapon',''),bp.get('config','')]).lower()
            if q and q not in hay:continue
            self.bp_catalog_tree.insert('', 'end', values=(
                name,bp.get('class',''),bp.get('title',''),bp.get('starting_weapon',''),
                '' if bp.get('max_weapon_mounts') is None else bp.get('max_weapon_mounts'),bp.get('config','')
            ))

    def refresh_blueprints(self):
        try:
            if hasattr(self,'bp_saved_tree'):
                self.bp_saved_tree.delete(*self.bp_saved_tree.get_children())
            p=find_global_save_file(self.root,'93_blueprints.sav');self.blueprint_path=p
            if not p:
                self.bp_status.set('93_blueprints.sav was not found from the selected save location.')
                return
            info=parse_player_blueprints(dec(p))
            for row in info['rows']:
                self.bp_saved_tree.insert('', 'end', values=(
                    row['index'],row['tag'],row['field_count'],row['size'],' | '.join(row['strings'])
                ))
            note='No saved BlueprintEntry objects are present.' if info['count']==0 else f'{info["count"]} saved BlueprintEntry objects parsed.'
            self.bp_status.set(
                f'Loaded {p} | Raw field 1: {info["raw_field1"]} | Saved entries: {info["count"]} | '
                f'Built-in config definitions: {len(self.blueprint_catalog)} | {note}'
            )
        except Exception as e:
            self.blueprint_path=None;self.bp_status.set(f'Blueprint collection error: {e}')

    def build_edit(self):
        f=ttk.Frame(self.edit,padding=12);f.pack(fill="both",expand=True)
        self.money=tk.StringVar()
        ttk.Label(f,text="Proven editor: Qbits").pack(anchor="w")
        row=ttk.Frame(f);row.pack(fill="x",pady=6)
        ttk.Entry(row,textvariable=self.money,width=20).pack(side="left")
        ttk.Button(row,text="Set Qbits",command=self.money_set).pack(side="left",padx=6)

        ttk.Separator(f,orient="horizontal").pack(fill="x",pady=12)
        ttk.Label(f,text="Backups for the file selected in Experiment Lab").pack(anchor="w")
        brow=ttk.Frame(f);brow.pack(fill="x",pady=6)
        ttk.Button(brow,text="Undo Last Edit (.prev)",command=self.undo_last_edit).pack(side="left")
        ttk.Button(brow,text="Restore Original (.bak)",command=self.restore_original_backup).pack(side="left",padx=6)
        ttk.Label(
            f,
            text=(
                "v1.14 keeps two safety copies: .bak is the file as it was before this editor first changed it, while .prev is the compressed save immediately before the most recent edit. "
                "Undo Last Edit swaps the current file and .prev, so it can also redo the same change if pressed again."
            ),wraplength=1180
        ).pack(anchor="w",pady=(0,8))

        ttk.Separator(f,orient="horizontal").pack(fill="x",pady=12)
        ttk.Label(
            f,
            text=(
                "Inventory quantity, config-aware Max Stack, condition/charge, structurally resized item replacement, duplicate/remove, and quickslot management are available in the Inventory tab. "
                "Field 3 is the validated quantity integer. Field 5 is editable only when stored as a 32-bit float. "
                "Quickslot position is the validated field-2 integer for records structurally identified inside the __quickslots array. "
                "v1.14 validates the surrounding 0x15/0x16/0x17 length-delimited containers before structural writes."
            ),
            wraplength=1180
        ).pack(anchor="w",pady=8)

    def _selected_lab_file(self):
        slot=str(self.sa.get()).strip();fname=str(self.fn.get()).strip()
        slot_dir=self.slot_paths.get(slot)
        if not slot_dir or not fname:
            raise RuntimeError("Select a save slot and file in the Experiment Lab tab first.")
        p=slot_dir/fname
        if not p.is_file():
            raise RuntimeError(f"Selected save file no longer exists: {p}")
        return p

    def undo_last_edit(self):
        try:
            p=self._selected_lab_file();prev=Path(str(p)+".prev")
            if not prev.is_file():
                messagebox.showinfo("Undo Last Edit",f"No .prev backup exists yet for {p.name}.");return
            # Validate that the backup is a decodable Cubic Odyssey save before
            # offering to replace the current file.
            dec(prev)
            if not messagebox.askyesno(
                "Undo Last Edit",
                f"Swap the current {p.name} with its .prev backup?\n\nThis undoes the most recent editor write. Running it again will redo that same change."
            ):return
            current=p.read_bytes();oldprev=prev.read_bytes()
            p.write_bytes(oldprev);prev.write_bytes(current)
            self.refresh()
            messagebox.showinfo("Undo Last Edit",f"Restored the previous version of {p.name}.\nThe version you just replaced is now stored in .prev.")
        except Exception as e:
            messagebox.showerror("Undo Last Edit error",str(e))

    def restore_original_backup(self):
        try:
            p=self._selected_lab_file();bak=Path(str(p)+".bak");prev=Path(str(p)+".prev")
            if not bak.is_file():
                messagebox.showinfo("Restore Original",f"No .bak baseline exists yet for {p.name}.");return
            dec(bak)
            if not messagebox.askyesno(
                "Restore Original Backup",
                f"Restore the original .bak baseline for {p.name}?\n\nThe current version will first be copied to .prev so this restore can be undone once."
            ):return
            shutil.copy2(p,prev);shutil.copy2(bak,p)
            self.refresh()
            messagebox.showinfo("Restore Original",f"Restored {p.name} from its .bak baseline.\nThe pre-restore version is in .prev.")
        except Exception as e:
            messagebox.showerror("Restore Original error",str(e))

    def build_cfg(self):
        f=ttk.Frame(self.cfg,padding=8);f.pack(fill="both",expand=True)
        r=ttk.Frame(f);r.pack(fill="x")
        self.q=tk.StringVar()
        ttk.Label(r,text=f"Loaded ItemCfg entries: {len(self.item_catalog):,}").pack(side="left",padx=(0,10))
        ttk.Entry(r,textvariable=self.q,width=50).pack(side="left")
        ttk.Button(r,text="Search Items",command=self.cfg_search).pack(side="left",padx=5)
        self.ct=ttk.Treeview(
            f,columns=("id","type","tier","stack","price","file"),show="headings"
        )
        for c,title,w in [
            ("id","Identifier",360),("type","Type",170),("tier","Tier",55),
            ("stack","Stack",65),("price","Base Price",90),("file","Config",650)
        ]:
            self.ct.heading(c,text=title);self.ct.column(c,width=w)
        self.ct.pack(fill="both",expand=True,pady=8)
        self.q.trace_add('write',lambda *_:self.cfg_search())
        self.cfg_search()

    def refresh(self):
        try:
            discovered=discover_slot_dirs(self.root)
            self.slot_paths={label:path for label,path in discovered}
            slots=[label for label,_ in discovered]

            self.ca["values"]=slots
            if slots:
                current=str(self.sa.get()).strip()
                if current not in self.slot_paths:
                    self.sa.set(slots[0])
            else:
                self.sa.set("")

            selected=str(self.sa.get()).strip()
            slot_dir=self.slot_paths.get(selected)

            files=[]
            if slot_dir:
                files=sorted(p.name for p in slot_dir.glob("*.sav"))
            self.cf["values"]=files
            if files:
                current=str(self.fn.get()).strip()
                if current not in files:
                    preferred="93_client_state.sav"
                    self.fn.set(preferred if preferred in files else files[0])
            else:
                self.fn.set("")

            # Decode only the selected slot.
            self.cache.clear()
            decode_errors=[]
            if slot_dir:
                for p in sorted(slot_dir.glob("*.sav")):
                    try:
                        self.cache[p]=dec(p)
                    except Exception as e:
                        decode_errors.append(f"{p.name}: {e}")

            self.it.delete(*self.it.get_children())
            self.inventory_meta={}
            row_id=0
            parsed_records=0
            record_errors=[]

            def fmt_value(typ,val):
                if typ==10:
                    return f"{float(val):.2f}"
                return str(int(val))

            # Player inventory/equipment lives in 93_client_state.sav.
            # Restrict the Inventory tab to that file when present so world/NPC
            # inventories do not flood the list with unrelated records.
            client_path=(slot_dir/"93_client_state.sav") if slot_dir else None
            if client_path in self.cache:
                inventory_sources=[(client_path,self.cache[client_path])]
            else:
                inventory_sources=[]

            for p,d in inventory_sources:
                try:
                    records=item_records(d)
                except Exception as e:
                    record_errors.append(f"{p.name}: {e}")
                    continue

                parsed_records += len(records)
                for ident,rec_start,rec_end,fields,v in records:
                    try:
                        qtyp,qoff=fields[3]
                        if qtyp != 4:
                            continue

                        # v1.6 accidentally referenced v[1] here even though
                        # the parser intentionally returns fields 2-5 only.
                        # That KeyError was caught as a record error, so every
                        # valid inventory row silently disappeared.
                        iid=f"item_{row_id}"
                        cfg=self.item_catalog.get(ident,{})
                        ident_bytes=ident.encode("utf-8")
                        ident_header=rec_end-len(ident_bytes)-11
                        location=inventory_record_location(d,ident_header)
                        self.it.insert(
                            "", "end", iid=iid,
                            values=(
                                selected,location,
                                (int(v[2])+1) if location=="Quickslots" and fields[2][0]==4 and 0<=int(v[2])<=9 else "",
                                ident,cfg.get("type","") or "",
                                "" if cfg.get("tier") is None else cfg.get("tier"),
                                int(v[3]),
                                "" if cfg.get("stack_size") is None else cfg.get("stack_size"),
                                fmt_value(fields[5][0],v[5]),p.name
                            )
                        )
                        self.inventory_meta[iid]={
                            "path":str(p),
                            "identifier":ident,
                            "record_start":rec_start,
                            "record_end":rec_end,
                            "identifier_header":ident_header,
                            "identifier_offset":ident_header+10,
                            "identifier_length":len(ident_bytes),
                            "quantity_offset":qoff,
                            "quantity":int(v[3]),
                            "field2_type":fields[2][0],
                            "field2_offset":fields[2][1],
                            "field2":int(v[2]),
                            "condition_type":fields[5][0],
                            "condition_offset":fields[5][1],
                            "location":location
                        }
                        row_id += 1
                    except Exception as e:
                        record_errors.append(f"{p.name}: {ident}: {e}")

            if slot_dir:
                location=str(slot_dir)
                condition_editable=sum(
                    1 for meta in self.inventory_meta.values()
                    if meta.get("condition_type")==10
                )
                config_matched=sum(
                    1 for meta in self.inventory_meta.values()
                    if meta.get("identifier") in self.item_catalog
                )
                structural_editable=sum(
                    1 for meta in self.inventory_meta.values()
                    if meta.get("location") in ("Player inventory","Ship inventory","Other inventory")
                )
                quickslot_count=sum(1 for meta in self.inventory_meta.values() if meta.get("location")=="Quickslots")
                msg=(f"Slot {selected} | {len(self.cache)} save files decoded | "
                     f"{parsed_records} inventory records parsed | {row_id} rows shown | "
                     f"{quickslot_count} quickslots | {structural_editable} add/remove-capable inventory rows | "
                     f"{config_matched} config matches | {condition_editable} condition/charge fields editable")
                self.inv_status.set(msg + f" | Folder: {location}")
            else:
                msg="No save-slot folders detected"
                self.inv_status.set(
                    "No save slots detected. Select either the Cubic Odyssey save folder "
                    "or a folder containing 93_client_state.sav."
                )

            if decode_errors:
                msg += f" | {len(decode_errors)} decode errors"
            if record_errors:
                msg += f" | {len(record_errors)} record errors"
            self.status.set(msg)

            # Qbits for selected slot.
            self.money.set("")
            if slot_dir:
                ep=slot_dir/"93_economy.sav"
                if ep.exists():
                    try:
                        ed=dec(ep)
                        if len(ed)>=16:
                            self.money.set(str(struct.unpack_from("<I",ed,12)[0]))
                    except Exception:
                        pass

            # Global account/class stats and blueprint collection live outside numbered slot folders.
            self.refresh_stats()
            self.refresh_vitals()
            self.refresh_skills()
            self.refresh_meta()
            self.refresh_quests()
            self.refresh_ships()
            self.refresh_world()
            self.refresh_blueprints()

        except Exception as e:
            self.status.set(f"Refresh error: {e}")
            if hasattr(self,"inv_status"):
                self.inv_status.set(f"Refresh error: {e}")
            messagebox.showerror("Refresh error",str(e))

    def analyze(self):
        try:
            slot=str(self.sa.get()).strip()
            fname=str(self.fn.get()).strip()

            if not slot or not fname:
                messagebox.showwarning(
                    "Experiment Lab",
                    "Select your save slot and a .sav file."
                )
                return

            slot_dir=self.slot_paths.get(slot)
            if not slot_dir:
                raise RuntimeError("The selected save slot is no longer available.")
            p=slot_dir/fname
            if not p.is_file():
                raise RuntimeError("Save file was not found:\n\n"+str(p))

            data=dec(p)
            self.labtree.delete(*self.labtree.get_children())
            self.report=[]

            # Basic file information.
            self.labtree.insert(
                "", "end",
                values=(
                    fname,
                    f"{len(data):,} decoded bytes",
                    f"{p.stat().st_size:,} compressed bytes",
                    data[:4].hex(" "),
                    "Valid Cubic Odyssey save"
                )
            )

            # Locate all readable identifiers. This is particularly useful for
            # inventory/equipment/world files.
            strings=re.findall(rb"[ -~]{4,}",data)
            seen=set()
            for s in strings:
                try:
                    t=s.decode("utf-8","replace")
                except Exception:
                    continue
                if t in seen:
                    continue
                seen.add(t)

                interesting=(
                    "." in t or
                    t.startswith(("npc_","res_","wep_","mod_","cloth_","dpl_"))
                )
                if interesting:
                    pos=data.find(s)
                    self.labtree.insert(
                        "", "end",
                        values=(
                            t,
                            f"0x{pos:08X}",
                            f"{len(s)} chars",
                            "",
                            "Readable identifier"
                        )
                    )
                    self.report.append({
                        "identifier":t,
                        "offset":pos,
                        "length":len(s)
                    })

            self.status.set(
                f"{fname}: {len(data):,} decoded bytes, "
                f"{len(self.report):,} readable identifiers"
            )

            messagebox.showinfo(
                "Analyze Save",
                f"{fname}\n\n"
                f"Decoded size: {len(data):,} bytes\n"
                f"Readable identifiers: {len(self.report):,}\n\n"
                "No second slot is required."
            )

        except Exception as e:
            messagebox.showerror("Analyze Save error",str(e))
    def scan_slot(self):
        try:
            slot=str(self.sa.get()).strip()
            if not slot:
                messagebox.showwarning("Experiment Lab","Select a save slot first.")
                return

            folder=self.slot_paths.get(slot)
            if not folder:
                raise RuntimeError("The selected save slot is no longer available.")
            files=sorted(folder.glob("*.sav"))
            if not files:
                raise RuntimeError("No .sav files were found in:\n\n"+str(folder))

            self.labtree.delete(*self.labtree.get_children())
            self.report=[]
            ok=0; errors=0

            for p in files:
                try:
                    data=dec(p)
                    ok+=1

                    # Count readable game-style identifiers.
                    strings=re.findall(rb"[ -~]{4,}",data)
                    identifiers=[]
                    for s in strings:
                        t=s.decode("utf-8","replace")
                        if (
                            "." in t or
                            t.startswith(("npc_","res_","wep_","mod_","cloth_","dpl_"))
                        ) and t not in identifiers:
                            identifiers.append(t)

                    self.labtree.insert(
                        "", "end",
                        values=(
                            p.name,
                            f"{len(data):,} bytes",
                            f"{p.stat().st_size:,} compressed",
                            f"{len(identifiers):,} identifiers",
                            "OK"
                        )
                    )

                except Exception as e:
                    errors+=1
                    self.labtree.insert(
                        "", "end",
                        values=(p.name,"ERROR","","",str(e))
                    )

            self.status.set(
                f"Slot {slot}: {ok} files decoded, {errors} errors"
            )
            messagebox.showinfo(
                "Scan Save Slot",
                f"Slot {slot}\n\n"
                f".sav files found: {len(files)}\n"
                f"Decoded successfully: {ok}\n"
                f"Errors: {errors}"
            )

        except Exception as e:
            messagebox.showerror("Scan Save Slot error",str(e))

    def export(self):
        if not getattr(self,"report",None):
            messagebox.showinfo("Export JSON","There is no analysis to export yet.")
            return

        p=filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON","*.json")]
        )
        if not p:
            return

        payload={
            "slot":str(self.sa.get()),
            "file":str(self.fn.get()),
            "results":self.report
        }
        Path(p).write_text(
            json.dumps(payload,indent=2),
            encoding="utf8"
        )
        messagebox.showinfo("Export JSON","Analysis exported successfully.")
    def money_set(self):
        try:
            v=int(self.money.get())
        except Exception:
            messagebox.showerror("Invalid Qbits","Enter a whole number.")
            return
        if not (0 <= v <= 4294967295):
            messagebox.showerror("Invalid Qbits","Qbits must be between 0 and 4,294,967,295.")
            return

        slot_dir=self.slot_paths.get(str(self.sa.get()).strip())
        if not slot_dir:
            messagebox.showerror("Set Qbits","No save slot is selected.")
            return

        p=slot_dir/"93_economy.sav"
        if not p.exists():
            messagebox.showerror("Set Qbits","93_economy.sav was not found in the selected slot.")
            return

        try:
            d=bytearray(dec(p))
            if len(d)<16:
                raise RuntimeError("93_economy.sav is shorter than expected.")
            old=struct.unpack_from("<I",d,12)[0]
            struct.pack_into("<I",d,12,v)
            write(p,d)
            self.refresh()
            messagebox.showinfo("Qbits Updated",f"{old:,} → {v:,}\n\nA .bak backup is kept alongside the save.")
        except Exception as e:
            messagebox.showerror("Set Qbits error",str(e))

    def cfg_search(self):
        self.ct.delete(*self.ct.get_children())
        q=self.q.get().strip().lower()
        for ident,cfg in sorted(self.item_catalog.items()):
            hay=' '.join([
                ident,cfg.get('type',''),cfg.get('title_string',''),cfg.get('config','')
            ]).lower()
            if q and q not in hay:
                continue
            self.ct.insert('', 'end', values=(
                ident,cfg.get('type',''),
                '' if cfg.get('tier') is None else cfg.get('tier'),
                '' if cfg.get('stack_size') is None else cfg.get('stack_size'),
                '' if cfg.get('base_price') is None else f"{cfg.get('base_price'):g}",
                cfg.get('config','')
            ))

    def run(self):self.w.mainloop()

def main():
    import sys
    root=Path(sys.argv[1]) if len(sys.argv)>1 else None
    cfg=Path(sys.argv[2]) if len(sys.argv)>2 else None

    if not root:
        t=tk.Tk()
        t.withdraw()
        selected=filedialog.askdirectory(
            title="Select Cubic Odyssey save folder (save root OR one slot folder)"
        )
        t.destroy()
        if not selected:
            return
        root=Path(selected)

    # Configs are optional. The editor works without them.
    if not cfg:
        t=tk.Tk()
        t.withdraw()
        selected=filedialog.askdirectory(
            title="Select configs directory (optional)"
        )
        t.destroy()
        cfg=Path(selected) if selected else None

    App(root,cfg).run()
if __name__=="__main__":main()
