"""Investigation and recovery pages built on the existing editor widgets."""
from pathlib import Path
import json,sys,struct,platform,datetime,threading,queue
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
import save_lab as lab
import save_schema as schema
import save_transactions as transactions

class LabUI:
    def build_extensions(self):
        from types import SimpleNamespace
        self.api=SimpleNamespace(**self.__init__.__globals__)
        self.data_home=self.settings_path.parent/'.editor_data';self.data_home.mkdir(exist_ok=True)
        self.store.journal_root=self.data_home/'transactions'
        self.lab_report=None;self.mapping_records=[];self.mapping_meta={};self.entity_meta={}
        self.mapping_path=self.data_home/'field_notes.json'
        try:self.mapping_notes=json.loads(self.mapping_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.mapping_notes={}
        self._background=False
        self.build_difference();self.build_health();self.build_mapping();self.build_entities();self.build_about()
        self.w.after(500,self.check_recovery)

    def draft_count(self):
        count=super().draft_count()
        if hasattr(self,'_mapping_baseline'):
            count+=((self.map_status.get(),self.map_evidence.get('1.0','end-1c'))!=self._mapping_baseline)
        return count

    def ext_tree(self,parent,columns,height=14):
        tree=self.api.ScrollTree(parent,columns=tuple(c[0] for c in columns),show='headings',height=height)
        for name,title,width in columns:tree.heading(name,text=title);tree.column(name,width=width)
        tree.pack(fill='both',expand=True,pady=6);return tree

    def run_job(self,label,work,done):
        if self._background:messagebox.showinfo('Working','Please wait for the current operation.');return
        self._background=True;self.lab_job_status.set(label);q=queue.Queue()
        def worker():
            try:q.put((True,work()))
            except Exception as exc:q.put((False,str(exc)))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            try:ok,value=q.get_nowait()
            except queue.Empty:self.w.after(100,poll);return
            self._background=False;self.lab_job_status.set('Ready' if ok else 'Operation failed')
            if ok:
                try:done(value)
                except Exception as exc:messagebox.showerror(label,str(exc))
            else:messagebox.showerror(label,value)
        self.w.after(100,poll)

    def build_difference(self):
        f=ttk.Frame(self.difference,padding=12);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Choose before/after files with Choose File A and B, then Compare A / B. Choose Folder also accepts ordinary save folders or editor snapshots. Source files are not modified.',wraplength=1000).pack(anchor='w',pady=8)
        row=ttk.Frame(f);row.pack(fill='x');self.capture_root=tk.StringVar(value=str(self.root.resolve()))
        ttk.Entry(row,textvariable=self.capture_root,width=85).pack(side='left')
        ttk.Button(row,text='Choose Save Root',command=lambda:self.choose_directory(self.capture_root)).pack(side='left',padx=5)
        self.snapshot_vars={key:tk.StringVar() for key in ('A','B')}
        for key in ('A','B'):
            row=ttk.Frame(f);row.pack(fill='x',pady=5)
            ttk.Button(row,text=f'Capture Snapshot {key}',command=lambda k=key:self.capture_snapshot(k)).pack(side='left')
            ttk.Button(row,text=f'Choose File {key}',command=lambda k=key:self.choose_comparison_file(k)).pack(side='left',padx=5)
            ttk.Button(row,text=f'Choose Folder {key}',command=lambda k=key:self.choose_directory(self.snapshot_vars[k])).pack(side='left',padx=5)
            ttk.Entry(row,textvariable=self.snapshot_vars[key],width=65).pack(side='left')
        row=ttk.Frame(f);row.pack(fill='x',pady=5)
        ttk.Button(row,text='Compare A / B',command=self.compare_snapshots).pack(side='left')
        ttk.Button(row,text='Export Difference Report',command=self.export_difference).pack(side='left',padx=6)
        self.lab_job_status=tk.StringVar(value='Ready');ttk.Label(row,textvariable=self.lab_job_status).pack(side='left')
        self.diff_tree=self.ext_tree(f,[('file','File',500),('state','Status',100),('a','A bytes',110),('b','B bytes',110),('decoded','Decoded A → B',190)],7)
        self.diff_detail=self.ext_tree(f,[('kind','Evidence',190),('field','Field / offset',350),('before','Before',400),('after','After',400)],12)
        self.diff_tree.bind('<<TreeviewSelect>>',lambda ev:self.show_diff_details())
        self.diff_detail.bind('<Double-1>',lambda ev:self.full_row(self.diff_detail))

    def choose_directory(self,var):
        path=filedialog.askdirectory(parent=self.w)
        if path:var.set(path)

    def capture_snapshot(self,key):
        root=Path(self.capture_root.get());dest=self.data_home/'snapshots'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+key)
        self.run_job('Capturing '+key,lambda:lab.capture(root,dest),lambda path:self.snapshot_vars[key].set(str(path.resolve())))

    def compare_snapshots(self):
        a=self.snapshot_vars['A'].get();b=self.snapshot_vars['B'].get()
        if not a or not b:messagebox.showerror('Difference Lab','Choose both snapshots first.');return
        def done(report):
            self.lab_report=report;self.diff_tree.delete(*self.diff_tree.get_children());self.diff_detail.delete(*self.diff_detail.get_children())
            for i,row in enumerate(report['files']):self.diff_tree.insert('','end',iid=str(i),values=(row['file'],row['status'],row['before_bytes'],row['after_bytes'],f'{row.get("before_decoded","—")} → {row.get("after_decoded","—")}'))
            changed=sum(r['status']!='Unchanged' for r in report['files']);self.lab_job_status.set(f'{changed} changed / {len(report["files"])} files; double-click evidence for full text')
        self.run_job('Comparing snapshots',lambda:lab.compare(self.api,a,b),done)

    def show_diff_details(self):
        self.diff_detail.delete(*self.diff_detail.get_children());selected=self.diff_tree.selection()
        if not selected or not self.lab_report:return
        row=self.lab_report['files'][int(selected[0])]
        for item in row['changes']:self.diff_detail.insert('','end',values=(item['kind'],item.get('name') or item['path'],str(item.get('before')),str(item.get('after'))))
        for note in row.get('notes',[]):self.diff_detail.insert('','end',values=('Note',note,'',''))
        if row.get('error'):self.diff_detail.insert('','end',values=('Decode/parse error',row['error'],'',''))

    def full_row(self,tree):
        selected=tree.selection()
        if not selected:return
        top=tk.Toplevel(self.w);top.title('Evidence details');top.geometry('950x600')
        box=tk.Text(top,wrap='word');scroll=ttk.Scrollbar(top,command=box.yview);box.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');box.pack(fill='both',expand=True)
        box.insert('1.0','\n\n'.join(str(v) for v in tree.item(selected[0],'values')));box.configure(state='disabled')

    def export_difference(self):
        if not self.lab_report:return
        path=filedialog.asksaveasfilename(parent=self.w,defaultextension='.json',initialfile='save_difference.json')
        if path:transactions.save_manifest(path,self.lab_report)

    def build_health(self):
        f=ttk.Frame(self.health,padding=12);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Healthy means available checks passed. Unknown formats receive partial validation.',wraplength=1000).pack(anchor='w',pady=8)
        row=ttk.Frame(f);row.pack(fill='x')
        for title,command in [('Scan Save Health',self.scan_health),('Recover Interrupted Transactions',self.recover_transactions),('Clone Selected Slot',self.clone_selected_slot)]:ttk.Button(row,text=title,command=command).pack(side='left',padx=4)
        self.health_status=tk.StringVar();ttk.Label(f,textvariable=self.health_status,wraplength=1000).pack(anchor='w')
        self.health_tree=self.ext_tree(f,[('file','File',500),('state','Status',110),('detail','Validation',950)],21)
        self.health_tree.bind('<Double-1>',lambda ev:self.full_row(self.health_tree))

    def scan_health(self):
        self.health_tree.delete(*self.health_tree.get_children());rows=[];slot=self.slot_paths.get(self.sa.get())
        if slot:
            for name in ('93_client_state.sav','93_meta.sav','93_economy.sav','93_quests.sav','93_sv_state.sav'):
                if not (slot/name).is_file():rows.append((str(slot/name),'Failed','Expected slot file missing'))
            paths=set(p for p in slot.rglob('*') if p.is_file() and not any(part.startswith('.') for part in p.relative_to(slot).parts))
            for name in ('93_stats.sav','93_blueprints.sav','meta.sav'):
                p=self.api.find_global_save_file(self.root,name)
                if p:
                    paths.add(p)
                    for suffix in ('.bak','.prev'):
                        backup=Path(str(p)+suffix)
                        if backup.is_file():paths.add(backup)
            for path in sorted(paths):
                if path.suffix in ('.bak','.prev'):
                    target=Path(str(path).rsplit('.',1)[0]);status,detail=schema.health(self.api,target,path.read_bytes())
                else:
                    try:raw=self.store.read(path);status,detail=schema.health(self.api,path,raw)
                    except Exception as exc:status,detail='Failed',str(exc)
                rows.append((str(path),status,detail))
                if path.suffix=='.sav' and path.name.startswith('93_3') and status!='Failed':
                    try:
                        ids=[r['id'] for r in lab.entities(self.api,self.api.dec(path)) if r['id']]
                        if len(ids)!=len(set(ids)):rows.append((str(path),'Warning','Duplicate entity IDs in this world file'))
                    except Exception:pass
            manifests=set()
            for parent in {p.parent for p in paths}|{Path(key).parent for key in self.store.entries}:
                manifests.update((parent/'.cubic_editor_history').glob('*.json'))
            for manifest in manifests:
                try:self.api.read_history_record(manifest);rows.append((str(manifest),'Healthy','Snapshot hash valid'))
                except Exception as exc:rows.append((str(manifest),'Failed',str(exc)))
        for key,entry in self.store.entries.items():
            try:
                if Path(key).read_bytes()!=entry['before']:raise ValueError('Stale pending baseline: file changed on disk')
                status,detail=schema.health(self.api,key,entry['after'])
            except Exception as exc:status,detail='Failed',str(exc)
            rows.append((key+' [pending]',status,detail))
        journals=transactions.pending(self.store.journal_root)
        for path in journals:rows.append((str(path),'Failed','Interrupted or unreadable transaction; recovery required'))
        for row in rows:self.health_tree.insert('','end',values=row)
        counts={state:sum(row[1]==state for row in rows) for state in ('Healthy','Warning','Failed')}
        self.health_status.set(' | '.join(f'{k}: {v}' for k,v in counts.items()));return rows

    def check_recovery(self):
        if transactions.pending(self.store.journal_root):
            self.show_page('health','Save Health / Integrity');self.scan_health()
            self.recover_transactions()

    def recover_transactions(self):
        journals=transactions.pending(self.store.journal_root)
        if not journals:messagebox.showinfo('Recovery','No interrupted transactions found.');return
        targets=[]
        for manifest in journals:
            try:targets.extend(entry['path'] for entry in json.loads(manifest.read_text(encoding='utf-8'))['files'])
            except Exception:targets.append('Unreadable journal: '+str(manifest))
        preview='\n'.join(targets[:20])+('\n…additional files' if len(targets)>20 else '')
        if not messagebox.askyesno('Recover Transactions',f'Restore originals for {len(journals)} transaction(s)?\n\n{preview}\n\nOutside changes will block automatic recovery.'):return
        try:
            for manifest in journals:transactions.recover(manifest)
            self.store.discard();self.refresh(preserve_forms=False);self.scan_health()
        except Exception as exc:messagebox.showerror('Recovery',str(exc))

    def clone_selected_slot(self):
        slot=self.slot_paths.get(self.sa.get())
        if not slot:return
        if self.store.entries:messagebox.showerror('Clone Slot','Apply or discard pending changes first. Cloning reads disk files.');return
        parent=filedialog.askdirectory(parent=self.w,title='Choose parent folder for a new free numbered slot')
        if not parent:return
        if not messagebox.askyesno('Clone Slot','Copy all selected slot files into a free numbered folder? Global/account files will not be copied or changed. In-game slot registration is not proven; the clone is suitable for editor experiments.'):return
        self.run_job('Cloning selected slot',lambda:lab.clone_slot(self.api,slot,parent,self.notify_progress),lambda path:messagebox.showinfo('Clone Created',str(path)))

    def build_mapping(self):
        f=ttk.Frame(self.mapping,padding=12);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Record field evidence across slots. Only known fields have validated writers.',wraplength=1000).pack(anchor='w',pady=8)
        row=ttk.Frame(f);row.pack(fill='x');self.mapping_file=tk.StringVar(value='93_client_state.sav')
        ttk.Entry(row,textvariable=self.mapping_file,width=32).pack(side='left')
        ttk.Button(row,text='Scan Fields Across Slots',command=self.scan_mapping).pack(side='left',padx=5)
        self.map_status=tk.StringVar(value='Unknown');ttk.Combobox(row,textvariable=self.map_status,values=('Unknown','Suspected','Verified'),state='readonly',width=14).pack(side='left')
        ttk.Button(row,text='Edit Known Field',command=self.edit_mapped_field).pack(side='left',padx=5)
        self.mapping_tree=self.ext_tree(f,[('slot','Slot',75),('path','Serializer path',330),('name','Known name',270),('type','Type',65),('offset','Offset',100),('value','Observed value',380),('state','Research status',150)],13)
        self.mapping_tree.bind('<<TreeviewSelect>>',lambda ev:self.select_mapping())
        ttk.Label(f,text='Source evidence and in-game observations').pack(anchor='w')
        self.map_evidence=tk.Text(f,height=6,wrap='word');self.map_evidence.pack(fill='x')
        self.map_evidence._is_dirty=lambda:False
        ttk.Button(f,text='Save Mapping Evidence',command=self.save_mapping).pack(anchor='w',pady=6)

    def scan_mapping(self):
        name=self.mapping_file.get().strip()
        if Path(name).name!=name or not name.endswith('.sav'):messagebox.showerror('Field Mapping','Enter a save filename, without a directory.');return
        self.mapping_tree.delete(*self.mapping_tree.get_children());self.mapping_meta={}
        for slot,path in self.slot_paths.items():
            p=path/name
            if not p.is_file():continue
            try:
                data=self.api.dec(p);records,_=schema.fields(self.api,data,name)
                for row in records:
                    key=name+':'+row['path'];note=self.mapping_notes.get(key,{})
                    iid=str(len(self.mapping_meta));self.mapping_meta[iid]=(p,row,key,transactions.sha(data))
                    self.mapping_tree.insert('','end',iid=iid,values=(slot,row['path'],row['name'],row['type'],hex(row['offset']),str(row['value']),note.get('status','Unknown')))
            except Exception as exc:messagebox.showerror('Field Mapping',f'{p}: {exc}');return

    def select_mapping(self):
        selection=self.mapping_tree.selection()
        if not selection:return
        _,_,key,_=self.mapping_meta[selection[0]];note=self.mapping_notes.get(key,{})
        self.map_status.set(note.get('status','Unknown'));self.map_evidence.delete('1.0','end');self.map_evidence.insert('1.0',note.get('evidence',''))
        self._mapping_baseline=(self.map_status.get(),self.map_evidence.get('1.0','end-1c'))

    def save_mapping(self):
        selection=self.mapping_tree.selection()
        if not selection:return
        _,row,key,_=self.mapping_meta[selection[0]];evidence=self.map_evidence.get('1.0','end-1c').strip()
        if self.map_status.get()!='Unknown' and not evidence:messagebox.showerror('Mapping Evidence','Attach evidence before promoting a discovery.');return
        self.mapping_notes[key]={'status':self.map_status.get(),'evidence':evidence,'type':row['type'],'updated':datetime.datetime.now().isoformat()}
        transactions.save_manifest(self.mapping_path,self.mapping_notes)
        self._mapping_baseline=(self.map_status.get(),self.map_evidence.get('1.0','end-1c'))
        for iid,(_,_,other,_) in self.mapping_meta.items():
            if other==key:self.mapping_tree.set(iid,'state',self.map_status.get())

    def edit_mapped_field(self):
        selection=self.mapping_tree.selection()
        if not selection:return
        path,row,key,baseline=self.mapping_meta[selection[0]]
        if not row.get('binding'):messagebox.showinfo('Field Mapping','This field has no validated writer. Evidence status cannot enable an unknown writer.');return
        value=simpledialog.askstring('Edit Known Field',f'{path}\n{row["name"]}\nCurrent: {row["value"]}',parent=self.w)
        if value is None:return
        try:
            data=self.api.dec(path)
            if transactions.sha(data)!=baseline:raise ValueError('Save changed since the mapping scan; scan again')
            changed=schema.write_known(self.api,data,row,value);self.api.write(path,changed);self.refresh();self.scan_mapping();self.review_pending()
        except Exception as exc:messagebox.showerror('Edit Known Field',str(exc))

    def build_entities(self):
        f=ttk.Frame(self.entities,padding=12);f.pack(fill='both',expand=True)
        ttk.Label(f,text='Inspect world objects and edit supported contained items. Other entity state is read-only.',wraplength=1000).pack(anchor='w',pady=8)
        row=ttk.Frame(f);row.pack(fill='x');self.entity_query=tk.StringVar()
        ttk.Entry(row,textvariable=self.entity_query,width=45).pack(side='left')
        ttk.Button(row,text='Scan / Filter Entities',command=self.scan_entities).pack(side='left',padx=5)
        self.entity_tree=self.ext_tree(f,[('file','World file',220),('category','Category hint',180),('id','Entity ID',150),('kind','Saved kind',300),('position','Position',240),('items','Items',70)],10)
        self.entity_tree.bind('<<TreeviewSelect>>',lambda ev:self.show_entity_items())
        self.entity_items=self.ext_tree(f,[('id','Item',400),('qty','Quantity',150),('condition','Condition / charge',180),('offset','Offset',120)],8)
        row=ttk.Frame(f);row.pack(fill='x')
        ttk.Button(row,text='Edit Contained Quantity',command=lambda:self.edit_entity_item('quantity')).pack(side='left')
        ttk.Button(row,text='Edit Contained Condition',command=lambda:self.edit_entity_item('condition')).pack(side='left',padx=6)

    def scan_entities(self):
        self.entity_tree.delete(*self.entity_tree.get_children());self.entity_items.delete(*self.entity_items.get_children());self.entity_meta={}
        slot=self.slot_paths.get(self.sa.get());query=self.entity_query.get().casefold()
        if not slot:return
        for path in sorted(slot.glob('93_3*.sav')):
            try:
                for row in lab.entities(self.api,self.api.dec(path)):
                    values=(path.name,row['category'],row['id'],row['kind'],row['position'],len(row['items']))
                    if query and query not in ' '.join(map(str,values)).casefold():continue
                    iid=str(len(self.entity_meta));self.entity_meta[iid]=(path,row);self.entity_tree.insert('','end',iid=iid,values=values)
            except Exception as exc:messagebox.showerror('World Entities',f'{path}: {exc}')

    def show_entity_items(self):
        self.entity_items.delete(*self.entity_items.get_children());selection=self.entity_tree.selection()
        if not selection:return
        _,entity=self.entity_meta[selection[0]]
        for i,row in enumerate(entity['items']):self.entity_items.insert('','end',iid=str(i),values=(row['identifier'],row['quantity'],row['condition'],hex(row['offset'])))

    def edit_entity_item(self,field):
        selection=self.entity_tree.selection();items=self.entity_items.selection()
        if not selection or not items:return
        path,entity=self.entity_meta[selection[0]];row=entity['items'][int(items[0])]
        if field=='condition' and row['condition_type']!=10:messagebox.showerror('Condition','This record has no validated float condition field.');return
        value=simpledialog.askstring('Edit Contained Item',f'{field}: {row[field]}',parent=self.w)
        if value is None:return
        try:
            value=int(value) if field=='quantity' else float(value)
            changed,_,_=self.api.set_world_item_scalar(self.api.dec(path),row['offset'],row['identifier'],field,row[field],value)
            self.api.write(path,changed);self.refresh();self.scan_entities();self.review_pending()
        except Exception as exc:messagebox.showerror('Contained Item',str(exc))

    def add_item_wizard(self):
        selected=self.it.selection()
        if not selected:messagebox.showinfo('Add Item','Select a simple item in the destination cargo container to use as a template.');return
        meta=self.inventory_meta[selected[0]];current=self.item_catalog.get(meta['identifier'],{})
        choices=sorted(key for key,value in self.item_catalog.items() if current.get('type') and value.get('type')==current['type'])
        if not choices:messagebox.showerror('Add Item','Matching item configs are required.');return
        top=tk.Toplevel(self.w);top.title('Add Item from Template');top.geometry('850x300');top.transient(self.w)
        ttk.Label(top,text=f'Template: {meta["identifier"]}\nDestination: {meta["location"]}\nOnly matching item classes are allowed. Nested state is rejected. Condition is inherited from the template.',wraplength=800).pack(anchor='w',padx=12,pady=12)
        ident=tk.StringVar(value=meta['identifier']);quantity=tk.StringVar(value='1')
        ttk.Combobox(top,textvariable=ident,values=choices,width=80,state='readonly').pack(padx=12,pady=8)
        ttk.Entry(top,textvariable=quantity,width=20).pack(padx=12,pady=8)
        baseline=transactions.sha(self.api.dec(Path(meta['path'])))
        def create():
            try:
                path=Path(meta['path']);data=self.api.dec(path)
                if transactions.sha(data)!=baseline:raise ValueError('Inventory changed; reopen the wizard')
                changed=lab.add_from_template(self.api,data,meta['identifier_header'],ident.get(),int(quantity.get()),self.item_catalog)
                self.api.write(path,changed);top.destroy();self.refresh();self.review_pending()
            except Exception as exc:messagebox.showerror('Add Item',str(exc),parent=top)
        ttk.Button(top,text='Stage New Item',command=create).pack(pady=10)

    def build_about(self):
        f=ttk.Frame(self.about,padding=20);f.pack(fill='both',expand=True)
        text=f'Cubic Odyssey Save Editor v1.34\n\nPython {platform.python_version()} ({platform.architecture()[0]})\nTk {tk.TkVersion}\nRuntime: {sys.executable}\n\nSave format: supplied 93_* Zstd saves; known serializers validated through the schema registry. Other voxel/world formats are compared as opaque bytes unless their compression is recognized.\n\nConfigs: {self.cfgroot or "Not selected"}\nItem definitions: {len(self.item_catalog)}\nJournal / snapshot / mapping storage: {self.data_home}\n\nSource modules are included. Research status is evidence tracking, not permission to write unknown fields.\n\nGlobal account edits remain separate from numbered-slot data.'
        ttk.Label(f,text=text,wraplength=1000,justify='left').pack(anchor='w')
