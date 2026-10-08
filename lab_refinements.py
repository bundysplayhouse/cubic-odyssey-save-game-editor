"""Evidence filters/bookmarks, snapshot mapping, progress and guided experiments."""
from pathlib import Path
import json,hashlib,datetime,queue,threading,re
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import save_lab as lab
import save_schema as schema
import save_transactions as tx

FILTERS=('All evidence','Known fields','Unknown fields','Added objects / fields','Numeric changes','Bookmarked')
CHECKS=('Appears in game','Loads successfully','Saves independently','Survives game restart','Original slot unchanged')

def known(item):return item.get('kind')=='Semantic' or bool(item.get('name') and item['name']!='Object')
def matches(item,mode,query='',bookmarked=False):
    kind=item.get('kind','')
    hit={'All evidence':True,'Known fields':known(item),'Unknown fields':kind in ('Field','Added object/field','Removed object/field') and not known(item),
         'Added objects / fields':kind=='Added object/field','Numeric changes':item.get('type') in (4,8,10) or kind.startswith('Numeric candidate'),'Bookmarked':bookmarked}.get(mode,False)
    return hit and (not query or query.casefold() in json.dumps(item,ensure_ascii=False).casefold())

def bookmark_key(report,filename,item):
    raw=[report['snapshot_a'],report['snapshot_b'],filename,item.get('kind'),item.get('path'),item.get('offset_a'),item.get('offset_b')]
    return hashlib.sha256(json.dumps(raw,ensure_ascii=False).encode('utf-8')).hexdigest()

def currency_candidates(report,before,after):
    if isinstance(before,bool) or isinstance(after,bool) or not isinstance(before,int) or not isinstance(after,int) or min(before,after)<0 or before==after:raise ValueError('Enter different non-negative whole-number Qbits balances')
    result=[]
    for row in report['files']:
        for item in row['changes']:
            a,b=item.get('before'),item.get('after')
            if item.get('kind','').startswith('Numeric candidate'):
                ma=re.match(r'uint=(\d+)',str(a));mb=re.match(r'uint=(\d+)',str(b))
                a=int(ma[1]) if ma else None;b=int(mb[1]) if mb else None
            elif item.get('type') not in (4,8,10):continue
            if a==before and b==after:result.append({'file':row['file'],'path':item['path'],'kind':item['kind'],'offset_a':item.get('offset_a'),'offset_b':item.get('offset_b'),'before':before,'after':after})
    return result

from guided_capture import GuidedCaptureUI

class RefinementUI(GuidedCaptureUI):
    def tr(self,text):return self.api.translate_ui(text,self.language_name.get())

    def build_extensions(self):
        home=self.settings_path.parent/'.editor_data';self.bookmark_path=home/'bookmarks.json'
        try:self.bookmarks=json.loads(self.bookmark_path.read_text(encoding='utf-8'))
        except (ValueError,OSError):self.bookmarks={}
        if not isinstance(self.bookmarks,dict):self.bookmarks={}
        self.detail_items={};self.progress_messages=None
        super().build_extensions()
        row=ttk.Frame(self.w);row.pack(side='bottom',fill='x',before=self.w.winfo_children()[0])
        self.progress_text=tk.StringVar(value=self.tr('Ready'));ttk.Label(row,textvariable=self.progress_text,wraplength=1000).pack(side='left',padx=10)
        self.job_progress=ttk.Progressbar(row,maximum=100,mode='determinate',length=180);self.job_progress.pack(side='right',padx=10)

    def build_difference(self):
        super().build_difference()
        parent=self.diff_tree.container.master
        panel=ttk.LabelFrame(parent,text='Evidence filters',padding=6);panel.pack(fill='x',before=self.diff_tree.container,pady=5)
        self.diff_filter=tk.StringVar(value='All evidence');self.diff_query=tk.StringVar();self.changed_only=tk.BooleanVar(value=True)
        for i,key in enumerate(FILTERS):ttk.Radiobutton(panel,text=key,value=key,variable=self.diff_filter,command=self.show_diff_details).grid(row=i//3,column=i%3,sticky='w',padx=7)
        ttk.Label(panel,text='Search evidence').grid(row=2,column=0,sticky='w')
        ttk.Entry(panel,textvariable=self.diff_query,width=42).grid(row=2,column=1,sticky='ew')
        ttk.Checkbutton(panel,text='Only changed files',variable=self.changed_only,command=self.populate_diff_files).grid(row=2,column=2,padx=5)
        self.diff_query.trace_add('write',lambda *args:self.show_diff_details())
        actions=ttk.Frame(parent);actions.pack(fill='x',before=self.diff_detail.container,pady=4)
        for label,command in [('Toggle Bookmark',self.toggle_bookmark),('Open Bookmarks',self.open_bookmarks),('Open in Field Mapping',self.evidence_to_mapping),('Guided Capture',self.open_guided_capture),('Guided Experiment',self.open_experiment)]:ttk.Button(actions,text=label,command=command).pack(side='left',padx=4)
        self.evidence_count=tk.StringVar();ttk.Label(parent,textvariable=self.evidence_count).pack(anchor='w')

    def notify_progress(self,done,total,phase,filename):
        if self.progress_messages is not None:self.progress_messages.put(('progress',(done,total,phase,filename)))

    def run_job(self,label,work,done):
        if self._background:messagebox.showinfo(self.tr('Working'),self.tr('Please wait for the current operation.'));return
        self._background=True;q=queue.Queue();self.progress_messages=q
        self.lab_job_status.set(self.tr(label));self.progress_text.set(self.tr(label));self.job_progress.configure(mode='indeterminate');self.job_progress.start(12)
        def worker():
            try:q.put(('result',(True,work())))
            except Exception as exc:q.put(('result',(False,str(exc))))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            progress=None;result=None
            for _ in range(500):
                try:kind,value=q.get_nowait()
                except queue.Empty:break
                if kind=='progress':progress=value
                else:result=value;break
            if progress:
                count,total,phase,filename=progress;self.job_progress.stop();self.job_progress.configure(mode='determinate',value=100*count/max(1,total))
                self.progress_text.set(f'{self.tr(phase)} {count}/{total} · {filename}')
            if result is None:self.w.after(75,poll);return
            self._background=False;self.progress_messages=None;self.job_progress.stop();ok,value=result
            self.job_progress.configure(mode='determinate',value=100 if ok else 0)
            self.progress_text.set(self.tr('Complete' if ok else 'Operation failed'));self.lab_job_status.set(self.tr('Ready' if ok else 'Operation failed'))
            if ok:
                try:done(value)
                except Exception as exc:messagebox.showerror(self.tr(label),str(exc))
            else:messagebox.showerror(self.tr(label),value)
        self.w.after(75,poll)

    def capture_snapshot(self,key):
        root=Path(self.capture_root.get());dest=self.data_home/'snapshots'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+key)
        self.run_job('Capturing',lambda:lab.capture(root,dest,self.notify_progress),lambda path:self.snapshot_vars[key].set(str(path.resolve())))

    def choose_comparison_file(self,key):
        old=Path(self.snapshot_vars[key].get())
        chosen=filedialog.askopenfilename(parent=self.w,title=self.tr('Choose File')+' '+key,
            initialdir=str(old.parent) if old.is_file() else None,
            filetypes=[('Save / world files','*.sav *.vx *.vw3'),('All files','*.*')])
        if chosen:self.snapshot_vars[key].set(str(Path(chosen).resolve()))

    def compare_snapshots(self):
        a=self.snapshot_vars['A'].get();b=self.snapshot_vars['B'].get()
        if not a or not b:messagebox.showerror(self.tr('Save Difference Lab'),self.tr('Choose both inputs first.'));return
        def done(report):
            self.lab_report=report;self.populate_diff_files()
            count=sum(row['status']!='Unchanged' for row in report['files'])
            self.lab_job_status.set(f'{self.tr("Changed files")}: {count} / {len(report["files"])}' if count else self.tr('No differences found.'))
        self.run_job('Comparing',lambda:lab.compare_inputs(self.api,a,b,self.data_home/'comparisons',self.notify_progress),done)

    def populate_diff_files(self):
        previous=self.diff_tree.selection()
        self.diff_tree.delete(*self.diff_tree.get_children());self.diff_detail.delete(*self.diff_detail.get_children());self.detail_items={}
        if not self.lab_report:return
        for i,row in enumerate(self.lab_report['files']):
            if self.changed_only.get() and row['status']=='Unchanged':continue
            self.diff_tree.insert('','end',iid=str(i),values=(row['file'],self.tr(row['status']),row['before_bytes'],row['after_bytes'],f'{row.get("before_decoded","—")} → {row.get("after_decoded","—")}'))
        children=self.diff_tree.get_children()
        target=getattr(self,'_bookmark_target',None)
        selected=next((iid for iid in children if target and self.lab_report['files'][int(iid)]['file']==target[0]),None)
        if selected is None:selected=previous[0] if previous and previous[0] in children else children[0] if children else None
        if selected:
            self.diff_tree.selection_set(selected);self.diff_tree.see(selected);self.show_diff_details()
            if target:
                iid=next((i for i,(_,_,token) in self.detail_items.items() if token==target[1]),None)
                if iid:self.diff_detail.selection_set(iid);self.diff_detail.see(iid)
        self._bookmark_target=None

    def show_diff_details(self):
        self.diff_detail.delete(*self.diff_detail.get_children());self.detail_items={};selection=self.diff_tree.selection()
        if not selection or not self.lab_report:return
        row=self.lab_report['files'][int(selection[0])]
        for i,item in enumerate(row['changes']):
            token=bookmark_key(self.lab_report,row['file'],item);marked=token in self.bookmarks
            if not matches(item,self.diff_filter.get(),self.diff_query.get(),marked):continue
            iid=str(i);self.detail_items[iid]=(row,item,token)
            label=item.get('name') or item['path']
            self.diff_detail.insert('','end',iid=iid,values=(('★ ' if marked else '')+self.tr(item['kind']),label,str(item.get('before')),str(item.get('after'))))
        self.evidence_count.set(f'{len(self.detail_items)} / {len(row["changes"])} · '+self.tr('Evidence'))
        # Warnings are always visible, even with a filter active.
        for note in row.get('notes',[]):self.diff_detail.insert('','end',values=(self.tr('Note'),note,'',''))
        if row.get('error'):self.diff_detail.insert('','end',values=(self.tr('Error'),row['error'],'',''))

    def toggle_bookmark(self):
        selected=self.diff_detail.selection()
        if not selected or selected[0] not in self.detail_items:return
        row,item,token=self.detail_items[selected[0]]
        if token in self.bookmarks:del self.bookmarks[token]
        else:self.bookmarks[token]={'file':row['file'],'item':item,'snapshot_a':self.lab_report['snapshot_a'],'snapshot_b':self.lab_report['snapshot_b'],'created':datetime.datetime.now().isoformat()}
        tx.save_manifest(self.bookmark_path,self.bookmarks);self.show_diff_details()

    def open_bookmarks(self):
        top=tk.Toplevel(self.w);top.title(self.tr('Open Bookmarks'));top.geometry('1000x600')
        tree=self.ext_tree(top,[('file','File',350),('field','Field / offset',300),('date','Date',220)],16);keys=list(self.bookmarks)
        for i,key in enumerate(keys):
            b=self.bookmarks[key];tree.insert('','end',iid=str(i),values=(b['file'],b['item'].get('name') or b['item']['path'],b['created']))
        def load():
            selected=tree.selection()
            if not selected:return
            mark=self.bookmarks[keys[int(selected[0])]]
            if self._background:messagebox.showinfo(self.tr('Working'),self.tr('Please wait for the current operation.'));return
            self._bookmark_target=(mark['file'],keys[int(selected[0])])
            self.diff_query.set('');self.snapshot_vars['A'].set(mark['snapshot_a']);self.snapshot_vars['B'].set(mark['snapshot_b']);self.diff_filter.set('Bookmarked');top.destroy();self.compare_snapshots()

    def change_language(self,event=None):
        super().change_language(event)
        if hasattr(self,'diff_filter'):self.populate_diff_files()
        for iid,(_,_,key,_) in getattr(self,'mapping_meta',{}).items():
            if self.mapping_tree.exists(iid):self.mapping_tree.set(iid,'state',self.tr(self.mapping_notes.get(key,{}).get('status','Unknown')))
        ttk.Button(top,text='Open Evidence',command=load).pack(pady=8);self.localize_widgets(top)

    def evidence_to_mapping(self):
        selected=self.diff_detail.selection()
        if not selected or selected[0] not in self.detail_items:return
        row,item,_=self.detail_items[selected[0]];side='B' if row['status']!='Removed' and item.get('after') is not None else 'A';folder=Path(self.lab_report['snapshot_b' if side=='B' else 'snapshot_a'])
        try:
            snapshot=lab.load_snapshot(folder);info=snapshot['files'][row['file']];raw=(folder/'blobs'/info['sha256']).read_bytes();data,_=lab.decoded(self.api,raw)
            records,_=schema.fields(self.api,data,Path(row['file']).name)
            match=next((r for r in records if r['path']==item.get('path') or r.get('name') and r['name']==item.get('path')),None)
            if match is None:
                offset=item.get('offset_b' if side=='B' else 'offset_a')
                if offset is None:
                    try:offset=int(item['path'].split('–')[0],16)
                    except ValueError:pass
                candidates=[r for r in records if isinstance(offset,int) and r['offset']<=offset<r['offset']+r['length']]
                match=min(candidates,key=lambda r:r['length']) if candidates else None
            if match is None:raise ValueError('No serializer field covers this evidence. Keep it bookmarked as raw evidence.')
            self.mapping_tree.delete(*self.mapping_tree.get_children());self.mapping_meta={};target=None
            for i,r in enumerate(records):
                iid=str(i);key=Path(row['file']).name+':'+r['path'];self.mapping_meta[iid]=(None,r,key,tx.sha(data))
                self.mapping_tree.insert('','end',iid=iid,values=(self.tr('Snapshot')+' '+side,r['path'],r['name'],r['type'],hex(r['offset']),str(r['value']),self.mapping_notes.get(key,{}).get('status','Unknown')))
                if r is match:target=iid
            self.mapping_file.set(Path(row['file']).name);self.show_page('mapping','Field Mapping');self.mapping_tree.selection_set(target);self.mapping_tree.see(target);self.select_mapping()
            evidence=f'\nSnapshot {side}: {folder}\nFile: {row["file"]}\nA: {self.lab_report["snapshot_a"]}\nB: {self.lab_report["snapshot_b"]}\nEvidence: {json.dumps(item,ensure_ascii=False)}\nSnapshot reference only; live file not loaded.'
            def attach():
                if self.mapping_tree.selection()==(target,) and evidence not in self.map_evidence.get('1.0','end-1c'):self.map_evidence.insert('end',evidence)
            self.w.after_idle(attach)
        except Exception as exc:messagebox.showerror(self.tr('Open in Field Mapping'),str(exc))

    def edit_mapped_field(self):
        selected=self.mapping_tree.selection()
        if selected and self.mapping_meta[selected[0]][0] is None:
            messagebox.showinfo(self.tr('Field Mapping'),self.tr('Snapshot evidence is read-only. Scan live fields to edit a supported value.'));return
        return super().edit_mapped_field()

    def scan_mapping(self):
        name=self.mapping_file.get().strip()
        if Path(name).name!=name or not name.endswith('.sav'):messagebox.showerror(self.tr('Field Mapping'),'Enter a save filename without a directory.');return
        try:inputs=[(slot,path/name,self.store.read(path/name)) for slot,path in self.slot_paths.items() if (path/name).is_file()]
        except Exception as exc:messagebox.showerror(self.tr('Field Mapping'),str(exc));return
        def work():
            result=[]
            for i,(slot,path,raw) in enumerate(inputs):
                data=self.api.unpack_blob(raw);records,_=schema.fields(self.api,data,name);result.append((slot,path,tx.sha(data),records));self.notify_progress(i+1,len(inputs),'Scanning',str(path))
            return result
        def done(result):
            self.mapping_tree.delete(*self.mapping_tree.get_children());self.mapping_meta={}
            for slot,path,digest,records in result:
                for row in records:
                    key=name+':'+row['path'];iid=str(len(self.mapping_meta));self.mapping_meta[iid]=(path,row,key,digest)
                    self.mapping_tree.insert('','end',iid=iid,values=(slot,row['path'],row['name'],row['type'],hex(row['offset']),str(row['value']),self.tr(self.mapping_notes.get(key,{}).get('status','Unknown'))))
        self.run_job('Scanning',work,done)

    def open_experiment(self):
        top=tk.Toplevel(self.w);top.title(self.tr('Guided Experiment'));top.geometry('1000x720')
        kind=tk.StringVar(value='Qbits');action=tk.StringVar();before=tk.StringVar();after=tk.StringVar();checks={key:tk.BooleanVar() for key in CHECKS}
        ttk.Label(top,text='Capture A, perform one action in-game, then capture B. Record your observations.',wraplength=920).pack(anchor='w',padx=14,pady=12)
        row=ttk.Frame(top);row.pack(fill='x',padx=14)
        for key in ('Qbits','Recipe unlock','Ship blueprint','Clone validation'):ttk.Radiobutton(row,text=key,value=key,variable=kind).pack(side='left',padx=6)
        ttk.Label(top,text='Action / recipe / blueprint / clone path').pack(anchor='w',padx=14,pady=(12,0));ttk.Entry(top,textvariable=action,width=110).pack(padx=14,fill='x')
        row=ttk.Frame(top);row.pack(fill='x',padx=14,pady=12)
        for label,var in [('Qbits before',before),('Qbits after',after)]:ttk.Label(row,text=label).pack(side='left');ttk.Entry(row,textvariable=var,width=18).pack(side='left',padx=8)
        ttk.Label(top,text='Clone checks — tick only results you observed in-game.').pack(anchor='w',padx=14)
        for label,var in checks.items():ttk.Checkbutton(top,text=label,variable=var).pack(anchor='w',padx=20)
        ttk.Label(top,text='Additional observations / repeat experiment / in-game result').pack(anchor='w',padx=14,pady=(12,0));notes=tk.Text(top,height=6,wrap='word');notes.pack(fill='both',expand=True,padx=14)
        outcome=tk.StringVar();ttk.Label(top,textvariable=outcome,wraplength=920).pack(anchor='w',padx=14,pady=8)
        def save():
            try:
                if self._background:raise ValueError('Wait for the current operation before recording an experiment.')
                a=self.snapshot_vars['A'].get();b=self.snapshot_vars['B'].get()
                if not a or not b:raise ValueError('Choose snapshots A and B on the Difference Lab page first.')
                if Path(a).resolve()==Path(b).resolve():raise ValueError('Use two different captures.')
                if not action.get().strip():raise ValueError('Describe the exact action or clone path.')
                experiment={'version':1,'kind':kind.get(),'action':action.get().strip(),'notes':notes.get('1.0','end-1c'),'snapshot_a':a,'snapshot_b':b,'checks':{k:v.get() for k,v in checks.items()},'status':'User observations; not editor-verified'}
                if kind.get()=='Qbits':
                    experiment.update(before=int(before.get()),after=int(after.get()))
                    currency_candidates({'files':[]},experiment['before'],experiment['after'])
                def work():
                    report=lab.compare_inputs(self.api,a,b,self.data_home/'comparisons',self.notify_progress)
                    experiment.update(snapshot_a=report['snapshot_a'],snapshot_b=report['snapshot_b'],input_a=a,input_b=b)
                    experiment['changed_files']=[r['file'] for r in report['files'] if r['status']!='Unchanged']
                    if experiment['kind']=='Qbits':experiment['candidates']=currency_candidates(report,experiment['before'],experiment['after'])
                    path=self.data_home/'experiments'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json');tx.save_manifest(path,experiment);return path
                def done(path):
                    count=len(experiment.get('candidates',[]));outcome.set(str(path)+ (f' · {count} unproven balance matches' if experiment['kind']=='Qbits' else ''))
                self.run_job('Recording experiment',work,done)
            except Exception as exc:messagebox.showerror(self.tr('Guided Experiment'),str(exc),parent=top)
        ttk.Button(top,text='Save Experiment Record',command=save).pack(pady=8)
        top.protocol('WM_DELETE_WINDOW',lambda:None if self._background else top.destroy());self.localize_widgets(top)
