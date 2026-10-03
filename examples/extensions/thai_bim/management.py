"""Undoable layer management, representation updates and compact native saves."""
import copy,json,os,tempfile,zipfile
from pathlib import Path
from core.history import Command
from core.layers import Layer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QCheckBox,QComboBox,QFileDialog

def layer_name(record):
    kind=record['kind'];discipline=record.get('discipline','Structure')
    if kind=='Rebar':return 'TBIM S Rebar '+record.get('host_kind','Unassigned')
    if kind in ('Footing','Column','Beam','Slab','Stair'):return 'TBIM S '+kind
    return 'TBIM '+discipline+' '+kind

class LayerChanges(Command):
    def __init__(self,scene,migrate=False,visibility=None):
        self.scene=scene;self.groups=[];self.layers=list(scene.layers)
        names={l.name:l for l in self.layers};self.add=[];self.states=[]
        if migrate:
            for g in scene.groups:
                r=(g.ext or {}).get('thai_bim')
                if not r:continue
                target=layer_name(r);self.groups.append((g,g.layer,target))
                if target not in names:
                    source=names.get(g.layer);l=Layer(target,source.visible if source else True,source.locked if source else False)
                    names[target]=l;self.add.append(l)
        for name,value in (visibility or {}).items():
            if name in names:self.states.append((names[name],names[name].visible,bool(value)))
    def do(self,scene):
        if scene is not self.scene or any(g not in scene.groups for g,_,_ in self.groups):raise ValueError('Document changed; refresh layers')
        scene.layers[:]=self.layers+self.add
        for g,old,new in self.groups:g.layer=new
        for l,old,new in self.states:l.visible=new
        scene.version+=1
    def undo(self,scene):
        for g,old,new in self.groups:g.layer=old
        for l,old,new in self.states:l.visible=old
        scene.layers[:]=self.layers;scene.version+=1

def compact_save(scene,path):
    from formats.igz import save_scene
    path=Path(path)
    if path.suffix.lower()!='.igz':path=path.with_suffix('.igz')
    # Save natively first so embedded assets and all host schema fields survive.
    with tempfile.TemporaryDirectory(prefix='thai-bim-save-') as directory:
        native=Path(directory)/'model.igz';save_scene(scene,native)
        temp=Path(directory)/'compact.igz'
        if zipfile.is_zipfile(native):
            with zipfile.ZipFile(native) as src,zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as dst:
                for name in src.namelist():dst.writestr(name,src.read(name))
        else:
            data=native.read_bytes();json.loads(data)
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as dst:dst.writestr('document.json',data)
        data=temp.read_bytes()
    # Replace only after the complete archive is prepared, atomically on target volume.
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return len(data)

def open_manager(panel):
    old=getattr(panel,'layer_dialog',None)
    if old is not None:old.close();old.deleteLater()
    dialog=QDialog(panel.app.window);dialog.setWindowTitle('Thai BIM 0.7 — Layer / โมเดลเบา');dialog.resize(680,650)
    layout=QVBoxLayout(dialog);label=QLabel('แยกฐานราก เสา คาน พื้น บันได และเหล็กตาม Host\nเปิด/ปิดเลเยอร์มีผลต่อการมองเห็นและการส่งออกภาพ/geometry; QTO/BBS ยังคงนับชิ้นที่ตรวจแล้ว')
    label.setWordWrap(True);layout.addWidget(label);checks={};bound=panel.app.scene
    def button(text,fn):
        b=QPushButton(text);b.clicked.connect(lambda _:panel.guard(fn));layout.addWidget(b)
    def current():
        if panel.app.scene is not bound:raise ValueError('เอกสารเปลี่ยน: เปิด Layer dialog ใหม่')
        return bound
    def migrate():panel.execute(LayerChanges(current(),migrate=True));open_manager(panel)
    button('จัดเลเยอร์ชิ้น Thai BIM เดิม (Undo ได้)',migrate)
    for l in bound.layers:
        if not l.name.startswith('TBIM'):continue
        count=sum(g.layer==l.name for g in bound.groups);c=QCheckBox(f'{l.name} — {count} ชิ้น');c.setChecked(l.visible)
        checks[l.name]=c;layout.addWidget(c)
    button('ใช้การมองเห็นที่เลือก',lambda:panel.execute(LayerChanges(current(),visibility={n:c.isChecked() for n,c in checks.items()})))
    button('ซ่อนเหล็กทุก Host เพื่อหมุนโมเดล',lambda:panel.execute(LayerChanges(current(),visibility={l.name:False for l in bound.layers if l.name.startswith('TBIM S Rebar')})))
    mode=QComboBox();mode.addItems(['Lightweight','Centreline','Full']);layout.addWidget(QLabel('เปลี่ยนการแสดงผลเหล็กของ Host คอนกรีตที่เลือก • ตรวจ Host แล้วสร้างชุดเดิมใหม่'));layout.addWidget(mode)
    def convert():
        from .builders import RebarDialog
        d=RebarDialog(panel);d.read_host();d.representation.setCurrentText(mode.currentText());d.review();d.build();d.deleteLater()
    button('เปลี่ยนโหมดเหล็กของ Host ที่เลือก (Undo ได้)',convert)
    button('บันทึกสำเนา IGZ แบบบีบอัด…',lambda:save())
    def save():
        path,_=QFileDialog.getSaveFileName(dialog,'บันทึกสำเนา IGZ แบบบีบอัด','','IGZ (*.igz)')
        if path:label.setText(f'บันทึกสำเนาแล้ว: {path}\n{compact_save(current(),path):,} bytes; ลดขนาดบนดิสก์ โหมดเบาลด geometry ในหน่วยความจำ')
    panel.layer_dialog=dialog;dialog.show();return dialog

def install(panel):
    if getattr(panel,'_v07_tools',False):return
    from .builders import icon
    panel._v07_tools=True
    action=panel.toolbar.addAction(icon('Project'),'Layer / โมเดลเบา');action.triggered.connect(lambda _:panel.guard(lambda:open_manager(panel)))
