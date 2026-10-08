"""Persistent, read-only before/after captures of one selected slot."""
from pathlib import Path
import json, uuid
import tkinter as tk
from tkinter import ttk, messagebox
import save_lab as lab
from save_transactions import save_manifest


def capture_step(api, home, session, phase, progress=None):
    session=dict(session)
    if phase not in ('before','after'):raise ValueError('Unknown capture step')
    if phase=='after' and not session.get('before'):raise ValueError('Capture Before first.')
    root=Path(session['source']).resolve()
    if not root.is_dir():raise ValueError(f'Selected slot folder was not found: {root}')
    if phase=='after':
        manifest=lab.load_snapshot(session['before'],progress)
        if Path(manifest['source']).resolve()!=root:raise ValueError('The Before capture belongs to a different slot.')
    destination=Path(home)/'guided_captures'/uuid.uuid4().hex
    captured=lab.capture(root,destination,progress)
    session[phase]=str(captured.resolve())
    # Persist each completed capture before comparison, so a failure is recoverable.
    save_manifest(Path(home)/'guided_session.json',session)
    save_manifest(captured/'experiment.json',session)
    report=lab.compare(api,session['before'],session['after'],progress) if phase=='after' else None
    return session,report


ACTION_PRESETS=(
    'Earn Qbits', 'Spend Qbits', 'Unlock one recipe', 'Unlock one ship blueprint',
    'Gain skill experience', 'Equip one item', 'Unequip one item',
    'Install one ship module', 'Remove one ship module',
    'Move one item into a container', 'Move one item out of a container',
    'Complete one quest',
)


class GuidedCaptureUI:
    def open_guided_capture(self):
        existing=getattr(self,'guided_window',None)
        if existing is not None and existing.winfo_exists():existing.lift();return
        top=tk.Toplevel(self.w);self.guided_window=top
        top.title(self.tr('Guided Capture'));top.geometry('820x610');top.minsize(640,520)
        frame=ttk.Frame(top,padding=16);frame.pack(fill='both',expand=True)
        session_path=self.data_home/'guided_session.json'
        try:
            session=json.loads(session_path.read_text(encoding='utf-8'))
            if not isinstance(session,dict):session={}
        except (OSError,ValueError):session={}
        self.guided_session=session
        ttk.Label(frame,text=self.tr('Select a slot once. Capture Before, perform one action in-game, then Capture After.'),wraplength=750).pack(anchor='w',pady=(0,10))
        ttk.Label(frame,text=self.tr('Save and fully close the game before each capture. Captures use saved files on disk; staged editor changes are not included.'),wraplength=750).pack(anchor='w',pady=(0,10))
        ttk.Label(frame,text=self.tr('Save Slot')).pack(anchor='w')
        selected=tk.StringVar(value=session.get('slot',self.sa.get()))
        selector=ttk.Combobox(frame,textvariable=selected,values=list(self.slot_paths),state='readonly');selector.pack(fill='x')
        source=tk.StringVar();ttk.Label(frame,textvariable=source,wraplength=750).pack(anchor='w',pady=8)
        ttk.Label(frame,text=self.tr('Choose an action, or type your own.')).pack(anchor='w')
        action=tk.StringVar(value=session.get('action',''))
        entry=ttk.Combobox(frame,textvariable=action,values=[self.tr(label) for label in ACTION_PRESETS],state='normal',height=12)
        entry.pack(fill='x',pady=6)
        self.guided_action_combo=entry
        state=tk.StringVar();ttk.Label(frame,textvariable=state,wraplength=750).pack(anchor='w',pady=12)
        ttk.Label(frame,text=self.tr('All game files inside this slot are captured. Account-wide files outside the slot are not included.'),wraplength=750).pack(anchor='w',pady=8)
        row=ttk.Frame(frame);row.pack(fill='x',pady=8)
        before_button=ttk.Button(row,text='Capture Before',command=lambda:self.guided_capture_step('before'))
        before_button.pack(side='left',padx=(0,8))
        after_button=ttk.Button(row,text='Capture After',command=lambda:self.guided_capture_step('after'))
        after_button.pack(side='left',padx=(0,8))
        results_button=ttk.Button(frame,text='Compare Saved Captures',command=self.guided_compare_saved)
        results_button.pack(anchor='w',pady=8)
        def new():
            if self._background:return
            save_manifest(session_path,{})
            self.guided_session={};action.set('');update()
        ttk.Button(frame,text='New Experiment',command=new).pack(anchor='w',pady=8)
        ttk.Label(frame,text=self.tr('Completed captures are kept when you start a new experiment. You can close this window and resume later.'),wraplength=750).pack(anchor='w',pady=8)
        def update(*args):
            current=self.guided_session;locked=bool(current.get('before'))
            path=current.get('source') if locked else self.slot_paths.get(selected.get())
            source.set(str(path or ''))
            selector.configure(state='disabled' if locked else 'readonly');entry.configure(state='disabled' if locked else 'normal')
            before_button.configure(state='disabled' if locked else 'normal');after_button.configure(state='normal' if locked else 'disabled')
            results_button.configure(state='normal' if current.get('after') else 'disabled')
            if current.get('after'):key='Both captures saved. Compare Saved Captures reopens the results without capturing again.'
            elif locked:key='Before saved. Perform your action, save and close the game, then click Capture After.'
            else:key='Ready: choose a slot and an action, then click Capture Before.'
            state.set(self.tr(key))
        selected.trace_add('write',update)
        self.guided_controls=(selected,action,state,update)
        update();top.protocol('WM_DELETE_WINDOW',lambda:None if self._background else top.destroy())
        self.localize_widgets(top)

    def guided_capture_step(self,phase):
        if self._background:return
        selected,action,state,update=self.guided_controls
        session=dict(self.guided_session)
        if phase=='before':
            if session.get('before'):return
            source=self.slot_paths.get(selected.get())
            if not source:
                messagebox.showerror(self.tr('Guided Capture'),self.tr('Select a save slot first.'));return
            if not action.get().strip():
                messagebox.showerror(self.tr('Guided Capture'),self.tr('Choose an action, or type your own.'));return
            session={'version':1,'slot':selected.get(),'source':str(Path(source).resolve()),'action':action.get().strip()}
        def done(result):
            current,report=result;self.guided_session=current;update()
            self.snapshot_vars['A'].set(current['before'])
            self.snapshot_vars['B'].set(current.get('after',''))
            if report is not None:
                self.lab_report=report;self.populate_diff_files()
                changed=sum(r['status']!='Unchanged' for r in report['files'])
                self.lab_job_status.set(f'{self.tr("Changed files")}: {changed} / {len(report["files"])}' if changed else self.tr('No differences found.'))
                state.set(self.tr('Comparison complete. Close this window to view the results in Difference Lab.'))
        self.run_job('Capturing',lambda:capture_step(self.api,self.data_home,session,phase,self.notify_progress),done)

    def guided_compare_saved(self):
        if self._background:return
        session=dict(self.guided_session)
        if not session.get('before') or not session.get('after'):return
        def done(report):
            self.snapshot_vars['A'].set(session['before']);self.snapshot_vars['B'].set(session['after'])
            self.lab_report=report;self.populate_diff_files()
            count=sum(row['status']!='Unchanged' for row in report['files'])
            self.lab_job_status.set(f'{self.tr("Changed files")}: {count} / {len(report["files"])}' if count else self.tr('No differences found.'))
            self.guided_controls[2].set(self.tr('Comparison complete. Close this window to view the results in Difference Lab.'))
        self.run_job('Comparing',lambda:lab.compare(self.api,session['before'],session['after'],self.notify_progress),done)
