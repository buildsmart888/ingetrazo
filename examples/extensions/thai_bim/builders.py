"""Assembly dialogs and tool icons, drawn locally with Qt."""
import math
from PySide6.QtCore import Qt,QPointF,QSize,QTimer
from PySide6.QtGui import QPixmap,QIcon,QPainter,QPen,QColor,QPolygonF
from PySide6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QScrollArea,
    QDoubleSpinBox,QSpinBox,QComboBox,QLabel,QPushButton,QPlainTextEdit,QToolBar,QTabWidget)
from . import engine as E
from . import structures as S

PRESETS={'Footing':(.0,.0,-.4,1.2,1.2,.4),'Column':(0,0,0,.25,.25,3),
         'Beam':(0,0,3,3,.2,.4),'Slab':(0,0,3,4,3,.15)}


def icon(kind):
    pix=QPixmap(64,64);pix.fill(Qt.transparent);p=QPainter(pix)
    try:
        p.setRenderHint(QPainter.Antialiasing);p.setPen(QPen(QColor('#2183a4'),4,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
        paths={
            'Project':[[(12,8),(12,56)],[(32,8),(32,56)],[(52,8),(52,56)],[(8,18),(56,18)],[(8,42),(56,42)]],
            'Footing':[[(9,45),(55,45),(55,56),(9,56),(9,45)],[(24,45),(24,17),(40,17),(40,45)]],
            'Column':[[(24,8),(40,8),(40,56),(24,56),(24,8)]],
            'Beam':[[(8,22),(56,22),(56,38),(8,38),(8,22)],[(15,38),(15,56)],[(49,38),(49,56)]],
            'Slab':[[(6,28),(40,14),(58,27),(24,43),(6,28)],[(6,28),(6,37),(24,52),(58,36),(58,27)],[(24,43),(24,52)]],
            'Stair':[[(8,56),(8,44),(20,44),(20,32),(32,32),(32,20),(44,20),(44,8),(56,8)]],
            'Rebar':[[(12,12),(52,12),(52,52),(12,52),(12,12)],[(20,7),(20,57)],[(44,7),(44,57)]],
            'Roof':[[(7,43),(32,14),(57,43)],[(14,37),(14,56),(50,56),(50,37)]],
            'Multi':[[(7,44),(22,12),(44,12),(57,44),(7,44)],[(22,12),(32,32),(44,12)],[(7,44),(32,32),(57,44)]],
            'QTO':[[(13,8),(51,8),(51,56),(13,56),(13,8)],[(21,22),(44,22)],[(21,33),(44,33)],[(21,44),(44,44)]],
            'Cut':[[(7,17),(57,17),(57,29),(7,29),(7,17)],[(27,9),(27,36)],[(7,45),(26,45)],[(38,45),(57,45)]],
        }
        for path in paths[kind]:p.drawPolyline(QPolygonF([QPointF(*v) for v in path]))
        p.setPen(QPen(QColor('#d88524'),3));p.drawLine(12,60,52,60)
    finally:p.end()
    return QIcon(pix)


class AssemblyPreview(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumSize(440,360);self.specs=[];self.error='';self.host=[]
    def display(self,specs,host=()):self.specs=specs;self.host=list(host);self.error='';self.update()
    def invalid(self,e):self.error=str(e);self.specs=[];self.update()
    def paintEvent(self,event):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor('#14283a'))
            p.setPen(QColor('#f2f6fa'));p.drawText(QPointF(18,28),'พรีวิวรูปทรงตามค่า • หน่วย geometry = m')
            if self.error:p.drawText(self.rect().adjusted(20,50,-20,-20),Qt.TextWordWrap,self.error);return
            specs=self.host+self.specs
            if not specs:p.drawText(QPointF(20,65),'เลือกชิ้นงาน / กรอกค่าเพื่อดูพรีวิว');return
            def raw(v):return (v[0]-.65*v[1],-.35*v[0]-.25*v[1]-v[2])
            points=[raw(v) for s in specs for f in s['faces'] for v in f]
            xmin=min(v[0] for v in points);xmax=max(v[0] for v in points);ymin=min(v[1] for v in points);ymax=max(v[1] for v in points)
            scale=min((self.width()-70)/max(xmax-xmin,.01),(self.height()-100)/max(ymax-ymin,.01))
            ox=(self.width()-(xmax-xmin)*scale)/2;oy=50+(self.height()-100-(ymax-ymin)*scale)/2
            def point(v):
                u,w=raw(v);return QPointF(ox+(u-xmin)*scale,oy+(w-ymin)*scale)
            faces=[]
            for spec in specs:
                if spec.get('bar_path'):
                    pts=spec['bar_path'];pts=pts+pts[:1] if spec.get('bar_closed') else pts
                    p.setPen(QPen(QColor('#ffac66'),1.5));p.drawPolyline(QPolygonF([point(v) for v in pts]));continue
                if spec.get('axis'):
                    p.setPen(QPen(QColor('#2ac6e6') if spec['kind']=='Rafter' else QColor('#e3ac59'),1.3));p.drawLine(point(spec['axis'][0]),point(spec['axis'][1]));continue
                for face in spec['faces']:
                    faces.append((sum(v[0]+v[1]+v[2] for v in face)/len(face),face,spec in self.host,spec['kind']=='Roof cover'))
            for _,face,ghost,roof in sorted(faces,key=lambda v:v[0]):
                p.setPen(QPen(QColor('#7798ac'),1));p.setBrush(Qt.NoBrush if ghost or roof else QColor('#738b9b'))
                p.drawPolygon(QPolygonF([point(v) for v in face]))
            p.setBrush(Qt.NoBrush)
            # Draw steel over the concrete outline so reinforcement remains readable.
            for spec in self.specs:
                if spec.get('bar_path'):
                    pts=spec['bar_path'];pts=pts+pts[:1] if spec.get('bar_closed') else pts
                    p.setPen(QPen(QColor('#ffac66'),1.5));p.drawPolyline(QPolygonF([point(v) for v in pts]))
        finally:p.end()


class BuilderDialog(QDialog):
    def __init__(self,panel,title):
        super().__init__(panel.app.window);self.panel=panel;self.setWindowTitle('Thai BIM 0.4 — '+title);self.setWindowIcon(icon(title if title in ('Stair','Rebar') else 'Roof'));self.resize(1080,800)
        lay=QVBoxLayout(self);row=QHBoxLayout();lay.addLayout(row,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(355);scroll.setMaximumWidth(470);row.addWidget(scroll,4)
        content=QWidget();self.form=QFormLayout(content);scroll.setWidget(content)
        self.visual=AssemblyPreview();row.addWidget(self.visual,6)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumHeight(130);lay.addWidget(self.output)
        self.fields={};self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(200);self.timer.timeout.connect(self.preview)
    def field(self,key,label,value,integer=False,minimum=None,maximum=None):
        w=QSpinBox() if integer else QDoubleSpinBox()
        if not integer:w.setDecimals(3);w.setSingleStep(.05 if 'mm' not in label else 1)
        w.setRange(minimum if minimum is not None else -10000,maximum if maximum is not None else 10000)
        w.setValue(value);w.valueChanged.connect(lambda _:self.timer.start());self.form.addRow(label,w);self.fields[key]=w;return w
    def button(self,label,fn):
        b=QPushButton(label);b.clicked.connect(lambda _:self.panel.guard(fn));self.form.addRow(b);return b
    def note(self,text):w=QLabel(text);w.setWordWrap(True);self.form.addRow(w)
    def showEvent(self,event):super().showEvent(event);self.preview()
    def preview(self):
        try:
            specs=self.specs();self.visual.display(specs)
            self.output.setPlainText(f'พรีวิว {len(specs)} ชิ้น • ยังไม่ได้สร้าง\n'+'\n'.join(f'{item}: {value:.3f} {unit}' for item,unit,value in self.summary(specs)))
        except Exception as e:self.visual.invalid(e);self.output.setPlainText(str(e))
    @staticmethod
    def summary(specs):
        totals={}
        for s in specs:totals[(s['item'],s['unit'])]=totals.get((s['item'],s['unit']),0)+s['quantity']
        return [(item,unit,value) for (item,unit),value in totals.items()]
    def build(self,update=False):
        from . import assembly_command
        specs=self.specs();params=self.params();selected=list(self.panel.app.scene.selection) if update else None
        command,count=assembly_command(self.panel.app.scene,specs,self.assembly_kind,params,selected)
        self.panel.execute(command);self.output.setPlainText(f'สร้าง/อัปเดต {count} ชิ้น • Undo ได้')
    def read(self):
        from . import selected_assembly
        group=selected_assembly(self.panel.app.scene,self.assembly_kind)
        params=group.ext['thai_bim']['assembly_params']
        if hasattr(self,'kind'):self.kind.setCurrentText(params['kind'])
        for key,w in self.fields.items():w.setValue(params[key])
        self.preview()


class RoofDialog(BuilderDialog):
    assembly_kind='roof-library'
    def __init__(self,panel):
        super().__init__(panel,'Roof');self.kind=QComboBox();self.kind.addItems(['Gable','Hip','Shed']);self.form.addRow('ชนิด: จั่ว / ปั้นหยา / เพิง',self.kind)
        self.kind.currentIndexChanged.connect(lambda _:self.timer.start())
        for key,label,v in [('x','X (m)',0),('y','Y (m)',0),('z','Z แนวผนังต่ำ (m)',3),('width','กว้าง X (m)',6),('depth','ลึก Y (m)',4),('pitch','มุมลาด (°)',30),('overhang','ชายคา (m)',.4),('cover','ความหนาหลังคา (m)',.06),('rafter_spacing','ระยะจันทันสูงสุด (m)',1),('batten_spacing','ระยะแปตามลาด (m)',.3)]:self.field(key,label,v)
        self.note('จั่วสันตาม Y • ปั้นหยาสันตามด้านยาว\nจันทัน/สัน/ตะเข้ C125×50×20×3.2; แป PROFAST\nยังไม่รวมข้อต่อ/การออกแบบรับแรง; gauge ตามกระเบื้อง')
        self.button('สร้างหลังคาชุดใหม่',self.build);self.button('อ่านชุดหลังคาที่เลือก',self.read);self.button('อัปเดตเฉพาะชุดที่เลือก',lambda:self.build(True))
    def params(self):return dict(kind=self.kind.currentText(),**{k:w.value() for k,w in self.fields.items()})
    def specs(self):return S.roof_assembly(**self.params())[1]


class StairDialog(BuilderDialog):
    assembly_kind='rc-stair'
    def __init__(self,panel):
        super().__init__(panel,'Stair')
        self.note('บันได RC ตรง • Z คือระดับชั้นล่าง; ท้องยื่นต่ำกว่าระดับนี้\nชั้นบนเป็นลูกตั้งสุดท้าย; ยังไม่รวมชานพัก/ราว/ฐานรองรับ')
        for key,label,v in [('x','X (m)',0),('y','Y (m)',0),('z','Z ระดับเริ่ม (m)',0),('width','กว้าง (m)',1),('height','สูงระหว่างชั้น (m)',3),('going','ลูกนอน (m)',.28),('waist','ความหนาท้องตั้งฉากลาด (m)',.15)]:self.field(key,label,v)
        self.field('risers','จำนวนลูกตั้ง',18,True,2,60)
        self.button('สร้างบันไดชุดใหม่',self.build);self.button('อ่านบันไดที่เลือก',self.read);self.button('อัปเดตบันไดที่เลือก',lambda:self.build(True))
    def params(self):return {k:w.value() for k,w in self.fields.items()}
    def specs(self):
        p=self.params();sp=S.stair_spec(**p);r=p['height']/p['risers']
        self.setToolTip(f"ลูกตั้ง {r*1000:.1f} mm; 2R+G = {(2*r+p['going'])*1000:.1f} mm (ข้อมูล ไม่ใช่เกณฑ์ผ่าน)")
        return [sp]
    def preview(self):
        super().preview()
        if not self.visual.error:
            p=self.params();r=p['height']/p['risers']
            self.output.appendPlainText(f"ลูกตั้ง {p['risers']} × {r*1000:.2f} mm • ลูกนอน {p['risers']-1} ขั้น\nระยะวิ่ง {(p['risers']-1)*p['going']:.3f} m • 2R+G {(2*r+p['going'])*1000:.1f} mm (ข้อมูลรูปทรง)")


class RebarDialog(BuilderDialog):
    def __init__(self,panel):
        super().__init__(panel,'Rebar');self.host_uid=None;self.host_params=None;self.host_kind=None
        self.host_label=QLabel('เลือก RC หนึ่งชิ้น แล้วกดอ่าน Host');self.host_label.setWordWrap(True);self.form.addRow(self.host_label)
        self.button('อ่านฐานราก / คาน / เสา / พื้น / บันไดที่เลือก',self.read_host)
        self.field('cover','Cover ถึงผิวนอกเหล็ก (mm)',40,False,15,150)
        self.field('diameter','เหล็กหลัก / ตะแกรง (mm)',12,False,4,50)
        self.field('tie_diameter','เหล็กปลอก (mm)',6,False,4,25)
        self.field('spacing','ระยะปลอก / ตะแกรงสูงสุด (mm)',150,False,40,1000)
        self.field('count_x','จำนวนหลักตามด้านที่ 1',3,True,2,30)
        self.field('count_y','จำนวนหลักตามด้านที่ 2',3,True,2,30)
        self.field('layers','ชั้นตะแกรงฐาน/พื้น: 1 ล่าง / 2 บนล่าง',1,True,1,2)
        self.note('สร้างรูปทรงตามค่าที่กรอก • ไม่มีการออกแบบรับแรง\nปลอกเป็นวงปิดมุม miter สำหรับโมเดล\nยังไม่รวมตะขอ/รัศมีดัด/ระยะทาบ/ฝังยึด; ปริมาณสุทธิไม่ใช่ BBS พร้อมผลิต\nคานวิ่งตาม X; บันไดตรงใช้เหล็กล่างหนึ่งชั้น')
        self.button('สร้าง / อัปเดตเหล็กของ Host นี้',self.build)
    def read_host(self):
        from . import mesh_fingerprint
        scene=self.panel.app.scene;selected=[g for g in scene.selection if g in scene.groups]
        if len(selected)!=1:raise ValueError('เลือกชิ้นคอนกรีต Thai BIM หนึ่งชิ้น')
        host=selected[0];rec=(host.ext or {}).get('thai_bim',{})
        params=rec.get('params') or rec.get('stair_params')
        if not params or rec.get('kind') not in ('Footing','Column','Beam','Slab','Stair'):raise ValueError('รองรับ RC และบันไดตรงที่สร้างด้วย Thai BIM')
        if host.xform is not None or mesh_fingerprint(host)!=rec.get('fingerprint'):raise ValueError('Host ถูก Transform/แก้ผิว: รุ่นนี้ต้องใช้ geometry ตามพารามิเตอร์เดิม')
        self.host_uid=host.uid;self.host_params=params;self.host_kind=rec['kind'];self.host_label.setText(host.name)
        for w in ('count_x','count_y','tie_diameter'):self.fields[w].setEnabled(self.host_kind in ('Beam','Column'))
        self.fields['layers'].setEnabled(self.host_kind in ('Footing','Slab'))
        old=next(((g.ext or {}).get('thai_bim',{}) for g in scene.groups if (g.ext or {}).get('thai_bim',{}).get('host_uid')==host.uid),{})
        if old.get('rebar_params'):
            for k,w in self.fields.items():w.setValue(old['rebar_params'][k])
        self.preview()
    def host(self):
        from . import mesh_fingerprint
        host=next((g for g in self.panel.app.scene.groups if g.uid==self.host_uid),None)
        if host is None:raise ValueError('กรุณาอ่าน Host ในเอกสารปัจจุบันก่อน')
        rec=host.ext['thai_bim']
        if host.xform is not None or mesh_fingerprint(host)!=rec['fingerprint']:raise ValueError('Host เปลี่ยนแล้ว: อ่าน/ตรวจ Host ใหม่')
        if rec['kind']!=self.host_kind:raise ValueError('Host เปลี่ยนชนิด: กดอ่าน Host ใหม่')
        self.host_params=rec.get('params') or rec.get('stair_params');return host
    def params(self):return {k:w.value() for k,w in self.fields.items()}
    def specs(self):
        self.host();p=self.params()
        for k in ('cover','diameter','tie_diameter','spacing'):p[k]/=1000
        if self.host_kind=='Stair':p['layers']=1
        return S.reinforcement(self.host_kind,self.host_params,**p)
    def preview(self):
        super().preview()
        if not self.visual.error and self.host_params:
            hostspec=S.stair_spec(**self.host_params) if self.host_kind=='Stair' else E.box_spec(**self.host_params)
            self.visual.display(self.visual.specs,[hostspec])
    def build(self,update=False):
        from . import rebar_command
        host=self.host();command,count=rebar_command(self.panel.app.scene,host,self.specs(),self.params())
        self.panel.execute(command);self.output.setPlainText(f'เหล็ก {count} เส้น • Host {host.name}\nกดซ้ำอัปเดตชุดเดิม • Undo ได้ • ปริมาณไม่รวมทาบ/ตะขอ')


def add_tools(panel):
    if getattr(panel,'_v04_tools',False):return
    panel._v04_tools=True
    panel.builder_dialogs={}
    def open_builder(kind):
        if kind not in panel.builder_dialogs:panel.builder_dialogs[kind]={'Roof':RoofDialog,'Stair':StairDialog,'Rebar':RebarDialog}[kind](panel)
        d=panel.builder_dialogs[kind];d.show();d.raise_();d.activateWindow()
    panel.open_builder=open_builder
    tabs=next(w for w in panel.findChildren(QTabWidget) if w.tabText(0)=='โครงการ')
    def member(kind):
        tabs.setCurrentIndex(1);panel.kind.setCurrentText(kind)
        for key,value in zip(('x','y','z','width','depth','height'),PRESETS[kind]):panel.mfields[key].setValue(value)
        panel.open_workspace()
    panel.apply_member_preset=lambda:member(panel.kind.currentText())
    grid_x=QComboBox();grid_y=QComboBox();level=QComboBox()
    panel.members.addRow('จุดวาง Grid X',grid_x);panel.members.addRow('จุดวาง Grid Y',grid_y);panel.members.addRow('ระดับฐานชิ้น',level)
    def read_grid():
        grid_x.clear();grid_y.clear();level.clear()
        for v in E.coordinates(panel.gx.text()):grid_x.addItem(f'X {v:g} m',v)
        for v in E.coordinates(panel.gy.text()):grid_y.addItem(f'Y {v:g} m',v)
        for p in E.levels(panel.lv.toPlainText()):level.addItem(f"{p['name']} {p['z']:+.3f} m",p['z'])
    def place_grid():
        if grid_x.currentData() is None or grid_y.currentData() is None or level.currentData() is None:raise ValueError('อ่าน Grid/Level ก่อน')
        centred=panel.kind.currentText() in ('Column','Footing')
        panel.mfields['x'].setValue(grid_x.currentData()-(panel.mfields['width'].value()/2 if centred else 0))
        panel.mfields['y'].setValue(grid_y.currentData()-(panel.mfields['depth'].value()/2 if centred else 0))
        panel.mfields['z'].setValue(level.currentData())
        panel.report.setPlainText('ตั้งจุดวางแล้ว • เสา/ฐานรากใช้ศูนย์กลางตรง Grid; คาน/พื้นใช้มุมฐาน • กดสร้างเมื่อพร้อม')
    panel.button(panel.members,'อ่าน Grid/Level จากช่องโครงการ',read_grid)
    panel.button(panel.members,'ใช้จุดตัด Grid / Level เป็นจุดวาง',place_grid)
    panel.grid_place_controls=(grid_x,grid_y,level);panel.place_grid=place_grid
    read_grid()
    panel.button(panel.members,'ใช้ขนาดตัวอย่างชนิดนี้',panel.apply_member_preset)
    panel.button(panel.members,'เหล็กเสริมของชิ้นที่เลือก…',lambda:open_builder('Rebar'))
    panel.button(panel.members,'สร้างบันได RC ตรง…',lambda:open_builder('Stair'))
    panel.button(panel.roof,'หลังคาจั่ว / ปั้นหยา / เพิง…',lambda:open_builder('Roof'))
    toolbar=QToolBar('Thai BIM 0.4',panel.app.window);toolbar.setObjectName('thai_bim_toolbar');toolbar.setIconSize(QSize(28,28));toolbar.setMovable(True);toolbar.setFloatable(True)
    panel.app.window.addToolBarBreak(Qt.TopToolBarArea)
    panel.app.window.addToolBar(Qt.TopToolBarArea,toolbar);panel.toolbar=toolbar
    actions=[('Project','โครงการ / Grid / Level',lambda:(tabs.setCurrentIndex(0),panel.open_workspace()))]
    actions += [(k,'สร้าง '+{'Footing':'ฐานราก','Column':'เสา','Beam':'คาน','Slab':'พื้น'}[k],lambda k=k:member(k)) for k in PRESETS]
    actions += [('Stair','บันได RC ตรง',lambda:open_builder('Stair')),('Rebar','เหล็กเสริม Host',lambda:open_builder('Rebar')),
        ('Roof','หลังคาจั่ว / ปั้นหยา / เพิง',lambda:open_builder('Roof')),('Multi','โครงหลังคาจาก IfcRoof',panel.open_multi),
        ('QTO','ปริมาณ / Excel',lambda:(tabs.setCurrentIndex(3),panel.open_workspace())),('Cut','แผนตัดวัสดุ',panel.open_cuts)]
    for k,title,fn in actions:
        action=toolbar.addAction(icon(k),title);action.setToolTip(title);action.triggered.connect(lambda checked=False,fn=fn:panel.guard(fn))
    panel.workspace_dialog.setWindowIcon(icon('Project'));panel.workspace_dialog.setWindowTitle('Thai BIM Toolkit 0.4 — โครงสร้าง / หลังคา / เหล็กเสริม')
    for label in panel.findChildren(QLabel):
        if label.text().startswith('Thai BIM Toolkit'):label.setText('Thai BIM Toolkit 0.4 • โครงสร้าง / หลังคา / เหล็กเสริม')
    for action in panel.app.window.findChildren(type(toolbar.toggleViewAction())):
        if action.text()=='Thai BIM Toolkit…':action.setIcon(icon('Project'))
    # QToolBar has a native visibility action; no private host toolbar API needed.
    panel.app.add_menu_action('แสดงแถบไอคอน Thai BIM',lambda:toolbar.setVisible(True),tip='Thai BIM toolbar')
