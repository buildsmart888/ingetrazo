"""Four-action IngeTrazo QToolBar + Extensions menu, API v2, v0.5.9+.

Toolbar is installed through the documented plugin `setup(app)` hook, not by
editing Program Files or monkey-patching the application's main source.
"""
from __future__ import annotations

import traceback
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGridLayout, QLabel, QMessageBox, QSpinBox,
    QTabWidget, QToolBar, QVBoxLayout, QWidget, QLineEdit)

from .beam_adapter import assert_baseline_locked
from .column_model import ColumnParams


ICONS = {
    "single": ("single beam", "#2F6387"),
    "multi": ("continuous beam", "#2F6387"),
    "rect": ("rectangular column", "#C76A30"),
    "circular": ("circular column", "#C76A30"),
    "wire": ("rebar wire / solid", "#178CA9"),
}


def _icon(key):
    """Rasterized 44x44 toolbar pictogram; avoids external image assets."""
    pix=QPixmap(44,44)
    pix.fill(Qt.GlobalColor.transparent)
    pen_color=QColor(ICONS[key][1])
    painter=QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing,True)
    painter.setPen(QPen(pen_color,2.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if key in ("single","multi"):
        spans=1 if key=="single" else 3
        painter.drawLine(6,18,38,18)
        painter.drawLine(6,25,38,25)
        for i in range(spans+1):
            x=6+int(32*i/spans)
            painter.drawLine(x,13,x,30)
            painter.drawLine(x-4,34,x+4,34)
        painter.setPen(QPen(QColor("#CB8442"),2.0))
        painter.drawLine(8,21,36,21)
    elif key=="wire":
        painter.drawLine(7,33,16,12)
        painter.drawLine(16,12,25,33)
        painter.drawLine(25,33,36,12)
        for x,y in [(7,33),(16,12),(25,33),(36,12)]:
            painter.drawEllipse(x-2,y-2,4,4)
    elif key=="rect":
        painter.drawRoundedRect(9,8,26,28,4,4)
        painter.drawRoundedRect(14,13,16,18,3,3)
        painter.setBrush(QColor("#C76A30"))
        for x,y in [(14,13),(30,13),(14,31),(30,31)]:
            painter.drawEllipse(x-2,y-2,4,4)
    else:
        painter.drawEllipse(8,8,28,28)
        painter.drawEllipse(13,13,18,18)
        painter.setBrush(QColor("#C76A30"))
        for i in range(8):
            import math
            a=2*math.pi*i/8
            x=int(round(22+11*math.cos(a)))
            y=int(round(22+11*math.sin(a)))
            painter.drawEllipse(x-2,y-2,4,4)
    painter.end()
    return QIcon(pix)


def _value_spin(form,label,value,low,high,step=5,integer=False):
    w=QSpinBox() if integer else QDoubleSpinBox()
    if not integer:
        w.setDecimals(1)
    w.setRange(low,high)
    w.setSingleStep(step)
    w.setValue(value)
    form.addRow(label,w)
    return w


def _next_column_id(scene):
    from .adapters.ingetrazo.scene import existing_column_ids
    existing=existing_column_ids(scene)
    for i in range(1,999):
        cid=f"C{i}"
        if cid not in existing:
            return cid
    return "C999"


def show_column_dialog(app,shape):
    """Return ColumnParams on OK, None on Cancel."""
    dialog=QDialog(app.window)
    dialog.setWindowTitle("GO RC Detailing v0.10.3 — "+(
        "Rectangular Column" if shape=="rect" else "Circular Column"))
    dialog.setMinimumSize(490,520)
    layout=QVBoxLayout(dialog)
    layout.addWidget(QLabel("3D Geometry + BIM + BOQ/BBS (NOT Engineering Code Compliance)"))
    tabs=QTabWidget(dialog)
    layout.addWidget(tabs)
    geo=QWidget(dialog);g=QFormLayout(geo)
    tabs.addTab(geo,"Column / Main Bars")
    hookstab=QWidget(dialog);hf=QFormLayout(hookstab)
    tabs.addTab(hookstab,"Main End Hooks")
    ties=QWidget(dialog);t=QFormLayout(ties)
    tabs.addTab(ties,"Ties / Formwork")
    placement=QWidget(dialog);p=QFormLayout(placement)
    tabs.addTab(placement,"Placement / Output")
    cid=QLineEdit(_next_column_id(app.scene))
    g.addRow("Column ID",cid)
    width=_value_spin(g,"Width X (mm)",300,220,2000,25) if shape=="rect" else None
    depth=_value_spin(g,"Depth Y (mm)",400,220,2000,25) if shape=="rect" else None
    diameter=_value_spin(g,"Diameter (mm)",400,280,2500,25) if shape!="rect" else None
    height=_value_spin(g,"Height (mm)",3000,600,15000,100)
    cover=_value_spin(g,"Concrete cover (mm)",40,20,110,5)
    main_d=_value_spin(g,"Longitudinal DB (mm)",16,10,40,1)
    top_hook=QCheckBox("90° hook at TOP")
    bottom_hook=QCheckBox("90° hook at BOTTOM")
    top_hook.setChecked(False)
    bottom_hook.setChecked(False)
    hf.addRow(top_hook)
    top_projection=_value_spin(hf,"ยื่นเหนือหัวเสา / TOP projection (mm)",0,0,5000,50)
    top_dir=QComboBox(dialog)
    top_dir.addItem("งอเข้าด้านใน / Inward", "inward")
    top_dir.addItem("งอบานออกด้านนอก / Outward fan", "outward")
    hf.addRow("TOP direction",top_dir)
    top_tail=_value_spin(hf,"TOP hook straight tail (mm)",40,20,400,5)
    hf.addRow(bottom_hook)
    bottom_projection=_value_spin(hf,"ยื่นใต้ตีนเสา / BOTTOM projection (mm)",0,0,5000,50)
    bottom_dir=QComboBox(dialog)
    bottom_dir.addItem("งอเข้าด้านใน / Inward", "inward")
    bottom_dir.addItem("งอบานออกด้านนอก / Outward fan", "outward")
    hf.addRow("BOTTOM direction",bottom_dir)
    bottom_tail=_value_spin(hf,"BOTTOM hook straight tail (mm)",40,20,400,5)
    helptext=QLabel("EXTENSION vs HOOK are independent. Set top/bottom projections >0 "
                    "to extend MAIN BARS beyond the finished column concrete faces "
                    "(example: TOP 500 mm, BOTTOM 600 mm). 0 keeps the legacy "
                    "inside-cover bar endpoint. With a hook, the projection measures "
                    "STRAIGHT vertical bar up to the bend tangent; bends are extra. "
                    "Outward bends need separate footing/slab/joint concrete. "
                    "Host cover, lap, anchorage and code compliance are NOT checked.")
    helptext.setWordWrap(True)
    hf.addRow(helptext)
    if shape=="rect":
        bx=_value_spin(g,"Bars along X edge",2,2,12,1,True)
        by=_value_spin(g,"Bars along Y edge",2,2,12,1,True)
        bc=None
    else:
        bc=_value_spin(g,"Longitudinal bar count",8,6,40,1,True)
        bx=by=None
    tie_d=_value_spin(t,"Tie RB (mm)",9,6,25,1)
    spacing=_value_spin(t, "Spiral pitch maximum (mm)" if shape=="circular"
                         else "Tie maximum spacing (mm)",150,50,400,10)
    first=_value_spin(t,"First tie from ends (mm)",50,30,200,5)
    tail=None;hook=None;spiral_facets=None
    if shape=="rect":
        tail=_value_spin(t,"Tie hook tail after bend (mm)",90,60,220,5)
        hook=QComboBox(dialog)
        hook.addItem("135 deg - return inside",135)
        hook.addItem("90 deg - perpendicular",90)
        t.addRow("Tie hooks",hook)
    else:
        spiral_facets=_value_spin(t,"Spiral segments per turn",32,12,96,4,True)
        info=QLabel("ONE continuous solid helix (not a stack of hoops). "
                    "Pitch is axial rise per revolution. End anchorage not code-checked.")
        info.setWordWrap(True)
        t.addRow(info)
    plywood=_value_spin(t,"Formwork thickness (mm)",18,9,40,1)
    display_form=QCheckBox("Show formwork geometry")
    display_form.setChecked(True)
    t.addRow(display_form)
    x=_value_spin(p,"Origin X (mm)",0,-200000,200000,500)
    y=_value_spin(p,"Origin Y (mm)",0,-200000,200000,500)
    z=_value_spin(p,"Origin Z (mm)",0,-200000,200000,500)
    ifc=QCheckBox("Export native IFC4 (GO BBS is authoritative for bent bars)")
    ifc.setChecked(True)
    p.addRow(ifc)
    native_mode=QCheckBox("Display IFC classes in IngeTrazo native BIM panel")
    native_mode.setChecked(True)
    native_mode.setToolTip("Flat tagged groups; removes native parent assembly. "
        "Uncheck to keep one physical parent and use GO RC BIM Browser instead.")
    p.addRow(native_mode)
    note=QLabel("Geometry only. Main bar straight projections and end hooks are "
                "separate TOP/BOTTOM controls. 0 mm keeps the original inset ends. "
                "Long hooks may clash or escape cover; they are rejected. "
                "Native BIM visibility replaces the physical parent hierarchy with logical group IDs.")
    note.setWordWrap(True)
    p.addRow(note)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                             QDialogButtonBox.StandardButton.Cancel,dialog)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec()!=QDialog.DialogCode.Accepted:
        return None
    return ColumnParams(
        shape=shape,column_id=cid.text().strip(),
        width_mm=width.value() if width else 300.0,
        depth_mm=depth.value() if depth else 400.0,
        diameter_mm=diameter.value() if diameter else 400.0,
        height_mm=height.value(),cover_mm=cover.value(),
        longitudinal_db_mm=main_d.value(),
        bars_x=bx.value() if bx else 2,bars_y=by.value() if by else 2,
        circular_bar_count=bc.value() if bc else 8,
        tie_db_mm=tie_d.value(),tie_spacing_mm=spacing.value(),
        tie_hook_deg=hook.currentData() if hook else 135,
        tie_hook_tail_mm=tail.value() if tail else 90.0,
        first_tie_mm=first.value(),plywood_mm=plywood.value(),
        show_formwork=display_form.isChecked(),export_ifc=ifc.isChecked(),
        pos_x_mm=x.value(),pos_y_mm=y.value(),pos_z_mm=z.value(),
        main_hook_top=top_hook.isChecked(),main_hook_bottom=bottom_hook.isChecked(),
        main_hook_top_direction=top_dir.currentData(),
        main_hook_bottom_direction=bottom_dir.currentData(),
        main_hook_top_tail_mm=top_tail.value(),
        main_hook_bottom_tail_mm=bottom_tail.value(),
        main_top_projection_mm=top_projection.value(),
        main_bottom_projection_mm=bottom_projection.value(),
        spiral_segments_per_turn=spiral_facets.value() if spiral_facets else 32,
        native_bim_visible=native_mode.isChecked())


def _run(app, code, title):
    """Run through SnapshotImport with a truthful, stage-based progress UI.

    The progress object is injected into the transactional scope and reported
    at meaningful geometry/IFC checkpoints. No background Qt scene mutation.
    """
    from .adapters.ingetrazo.transaction import run_script
    from .adapters.ingetrazo.progress import QtBuildProgress
    if getattr(app.window,"_go_rc_build_busy",False):
        QMessageBox.information(app.window,"GO RC Detailing","A model is already being generated")
        return {"changed":False,"error":"busy"}
    app.window._go_rc_build_busy=True
    tb=app.window.findChild(QToolBar,"go_rc_detailing_toolbar")
    if tb is not None: tb.setEnabled(False)
    progress=QtBuildProgress(app.window,title+" — Working")
    try:
        # Column parameter dialog has already closed here. Show status
        # BEFORE IngeTrazo snapshots the document for Undo, because the
        # snapshot itself may take noticeable time in large scenes.
        if "Column" in title:
            progress.begin("กำลังเตรียม Undo Snapshot / Preparing scene snapshot")
        result=run_script(app.viewport,code,scope={
            "__name__":"__go_rc_toolbar__", "window":app.window,
            "_go_rc_progress":progress,
        })
        if progress.cancelled:
            app.window.statusBar().showMessage(title+" — canceled, scene rolled back",10000)
            return result
        if result.get("error") is not None:
            msg=result.get("stderr") or str(result["error"])
            QMessageBox.critical(app.window,"GO RC Detailing — Error",msg[-7000:])
        elif result.get("changed"):
            app.window.statusBar().showMessage(title+" — created; save .igz when ready",10000)
        else:
            app.window.statusBar().showMessage(title+" — canceled",5000)
        return result
    except Exception as exc:
        QMessageBox.critical(app.window,"GO RC Detailing — Error",str(exc))
        return {"changed":False,"error":exc}
    finally:
        progress.close()
        if tb is not None:tb.setEnabled(True)
        app.window._go_rc_build_busy=False


def _beam(app,mode):
    try:
        assert_baseline_locked()
        native=bool(getattr(app.window,"_go_rc_native_bim_default",True))
        use_phase2=bool(getattr(app.window,"_go_rc_phase2_opt_in",True))
        fast_mesh=bool(getattr(app.window,"_go_rc_fast_mesh_opt_in",False)) and use_phase2
        pipeline="phase2" if use_phase2 else "accepted"
        src=("from ingetrazo_plugin_go_rc_detailing.beam_adapter import execute_beam\n"
             f"execute_beam(globals(), mode={mode!r}, native_bim_visible={native!r}, "
             f"pipeline={pipeline!r}, fast_mesh={fast_mesh!r}, progress=_go_rc_progress, "
             "dual_display=True)\n")
        _run(app,src,"GO RC Beam")
    except Exception as exc:
        QMessageBox.critical(app.window,"GO RC Baseline",str(exc))


def _column(app,shape):
    params=show_column_dialog(app,shape)
    if params is None:return
    from dataclasses import asdict
    code=("from ingetrazo_plugin_go_rc_detailing.column_model import ColumnParams,create_column\n"
          f"create_column(ColumnParams(**{asdict(params)!r}), globals(), "
          "progress=_go_rc_progress, dual_display=True)\n")
    _run(app,code,"GO RC Column")


def install_toolbar(app):
    """Registered once during IngeTrazo extensions startup."""
    if getattr(app.window,"_go_rc_toolbar_installed",False):
        return
    assert_baseline_locked()
    tb=QToolBar("GO RC Detailing",app.window)
    tb.setObjectName("go_rc_detailing_toolbar")
    tb.setToolTip("GO Engineering | Beam + Column BIM Detailing")
    tb.setIconSize(QSize(34,34))
    tb.setMovable(True)
    tb.setFloatable(True)
    entries=[
        ("single","คานช่วงเดียว", "สร้างคานเสริมเหล็ก 1 ช่วง / 1 span",lambda:_beam(app,"single")),
        ("multi","คานต่อเนื่อง", "สร้างคานเสริมเหล็กหลายช่วง / continuous",lambda:_beam(app,"multi")),
        ("rect","เสาสี่เหลี่ยม", "สร้างเสา ค.ส.ล. สี่เหลี่ยมพร้อมเหล็กหลักและปลอก",lambda:_column(app,"rect")),
        ("circular","เสากลม", "สร้างเสา ค.ส.ล. กลมพร้อมเหล็กหลักและ Hoop",lambda:_column(app,"circular")),
    ]
    submenu=app.add_menu("GO RC Detailing")
    for i,(key,display,tip,callback) in enumerate(entries):
        if i==2:
            tb.addSeparator()
            if submenu is not None:submenu.addSeparator()
        action=QAction(_icon(key),display,app.window)
        action.setToolTip(display+"\n"+tip)
        action.setStatusTip(tip)
        action.triggered.connect(lambda checked=False,cb=callback:cb())
        tb.addAction(action)
        if submenu is not None:
            menuaction=submenu.addAction(display)
            menuaction.setIcon(_icon(key))
            menuaction.triggered.connect(lambda checked=False,cb=callback:cb())
    if submenu is not None:
        native=QAction("Native BIM visible for new beams (flat tagged groups)",app.window)
        native.setCheckable(True)
        native.setChecked(True)
        native.setToolTip("Turn OFF to preserve a single native parent group. "
                          "ON shows IFC classes in the built-in BIM panel.")
        native.toggled.connect(lambda checked: setattr(
            app.window,"_go_rc_native_bim_default",bool(checked)))
        app.window._go_rc_native_bim_default=True
        submenu.addSeparator()
        submenu.addAction(native)
        def publish_existing():
            code=("from ingetrazo_plugin_go_rc_detailing.native_bim_mode "
                  "import expose_existing_assemblies\n"
                  "print('Native BIM publication:', expose_existing_assemblies(scene))\n")
            _run(app,code,"GO RC Publish Native BIM")
        sub_action=submenu.addAction("Publish existing RC assemblies to native BIM...")
        sub_action.triggered.connect(lambda checked=False:publish_existing())
    if submenu is not None:
        def inspect_solids():
            from .geometry_adapter import mesh_closed_report
            from core.group import iter_placements
            seen=set();issues=[];count=0
            for root in app.scene.groups:
                for leaf,_ in iter_placements(root):
                    if (getattr(leaf,'ifc',None) or {}).get('class') != 'IfcReinforcingBar':
                        continue
                    mesh=leaf.mesh
                    if id(mesh) in seen:continue
                    seen.add(id(mesh));count+=1
                    report=mesh_closed_report(mesh)
                    if not report['closed']:
                        issues.append(f"{leaf.name}: {report}")
            if issues:
                QMessageBox.warning(app.window,'GO RC Solid Audit',
                    f"{len(issues)} of {count} REBAR MESH PROTOTYPES have topology issues.\n\n"+
                    "\n".join(issues[:20])+"\n\nRebuild old objects with v0.8.2; do not run Repair All blindly.")
            else:
                QMessageBox.information(app.window,'GO RC Solid Audit',
                    f"{count} distinct reinforcing-bar mesh prototypes examined; all report closed surfaces. "
                    "This is not an engineering approval.")
        sub_action=submenu.addAction('Inspect GO RC rebar solids (read-only)')
        sub_action.triggered.connect(lambda checked=False:inspect_solids())
    if submenu is not None:
        submenu.addSeparator()
        phase2_action=QAction("Use Phase2 Beam Builder (accepted on Windows)",app.window)
        phase2_action.setCheckable(True)
        phase2_action.setChecked(True)  # Phase2 passed Windows acceptance
        app.window._go_rc_phase2_opt_in=True
        phase2_action.toggled.connect(lambda on:setattr(
            app.window,'_go_rc_phase2_opt_in',bool(on)))
        phase2_action.setToolTip("Uncheck to use the locked v0.7 legacy fallback")
        submenu.addAction(phase2_action)

        low_poly=QAction("New beams: 8-sided rebar preview (BBS axes unchanged)",app.window)
        low_poly.setCheckable(True)
        low_poly.setChecked(False)
        app.window._go_rc_fast_mesh_opt_in=False
        low_poly.toggled.connect(lambda on:setattr(
            app.window,'_go_rc_fast_mesh_opt_in',bool(on)))
        low_poly.setToolTip("Phase2 only; reduces tube face count. Native geometric IFC cross-section is approximated.")
        submenu.addAction(low_poly)

        from .performance import complexity_report, diagnostic_text, set_fast_shaded
        fast_style=QAction("Fast Shaded View (no edges / silhouettes)",app.window)
        fast_style.setCheckable(True)
        fast_style.setChecked(False)
        def on_fast_style(on):
            try:
                set_fast_shaded(app,bool(on))
            except Exception as exc:
                fast_style.blockSignals(True)
                fast_style.setChecked(False)
                fast_style.blockSignals(False)
                QMessageBox.warning(app.window,'GO RC Fast View',str(exc))
        fast_style.toggled.connect(on_fast_style)
        submenu.addAction(fast_style)
        def audit_perf():
            info=diagnostic_text(app.scene)
            print(info)
            QMessageBox.information(app.window,"GO RC Scene Performance Audit",info)
        audit_action=QAction("Measure scene geometry / instancing...",app.window)
        audit_action.triggered.connect(lambda checked=False: audit_perf())
        submenu.addAction(audit_action)
    # Native IngeTrazo layers, without requiring a custom host build.
    # Keep four modelling actions; the small fifth toolbar action is a
    # Wire/Solid shortcut. 'Both' + explicit refresh live in the menu.
    from .dual_display import get_mode, set_mode, refresh_wire_overlays
    view_actions = {}

    def _sync_view_actions():
        current = get_mode(app.scene)
        for name, control in view_actions.items():
            control.blockSignals(True)
            control.setChecked(name == current)
            control.blockSignals(False)
        return current

    def _apply_display_mode(mode):
        try:
            status = set_mode(app.scene, mode)
            if getattr(app.viewport, 'notify_scene_changed', None):
                app.viewport.notify_scene_changed()
            app.viewport.update()
            _sync_view_actions()
            msg = 'GO RC Display: ' + mode.upper()
            app.window.statusBar().showMessage(msg, 5000)
            if status['wire'] and status['wire']['missing_legacy_bars']:
                app.window.statusBar().showMessage(
                    msg + ' (older bars need rebuilding to obtain wire paths)', 10000)
        except Exception as exc:
            _sync_view_actions()
            QMessageBox.warning(app.window, 'GO RC Dual Display', str(exc))

    if submenu is not None:
        submenu.addSeparator()
        for mode, label in (('solid', 'Display: Solid 3D only'),
                            ('wire', 'Display: Centerline Wire only'),
                            ('both', 'Display: Wire + Solid')):
            action = QAction(label, app.window)
            action.setCheckable(True)
            action.setChecked(get_mode(app.scene) == mode)
            action.triggered.connect(lambda checked=False, m=mode: _apply_display_mode(m))
            submenu.addAction(action)
            view_actions[mode] = action

        def _refresh_display():
            try:
                result = refresh_wire_overlays(app.scene)
                app.scene.version += 1
                if getattr(app.viewport, 'notify_scene_changed', None):
                    app.viewport.notify_scene_changed()
                app.viewport.update()
                QMessageBox.information(app.window, 'GO RC Wire Refresh',
                    f"{result['assemblies']} assemblies / {result['bars']} bars / "
                    f"{result['edges']} wire edges\n"
                    f"Missing unregistered old bars: {result['missing_legacy_bars']}")
            except Exception as exc:
                QMessageBox.warning(app.window, 'GO RC Wire Refresh', str(exc))

        refresh_action = QAction('Refresh Wire from Solid positions...', app.window)
        refresh_action.triggered.connect(lambda checked=False: _refresh_display())
        submenu.addAction(refresh_action)

    tb.addSeparator()
    wire_button = QAction(_icon('wire'), 'Wire / Solid', app.window)
    wire_button.setToolTip('Switch GO RC reinforcement between Wire Only and Solid Only. '
                           'Use Extensions > GO RC Detailing for Both and Refresh.')
    wire_button.triggered.connect(lambda checked=False:
        _apply_display_mode('solid' if get_mode(app.scene) == 'wire' else 'wire'))
    tb.addAction(wire_button)
    app.window._go_rc_display_actions = view_actions
    app.window.addToolBar(Qt.ToolBarArea.TopToolBarArea,tb)
    app.window._go_rc_toolbar_installed=True
    if hasattr(app.window,"toolbars"):
        app.window.toolbars["go_rc_detailing"]=tb
    # Browser type labels make nested assemblies discoverable.
    def outliner_type(group):
        info=(getattr(group,"ext",None) or {}).get("go_rc_column")
        if not info:return None
        return {"type":"GO RC Column" if info.get("kind")=="assembly" else "RC " + info.get("kind","Part"),
                "props":[("Column",str(info.get("column_id",""))),
                         ("Shape",str(info.get("shape","")))]}
    app.add_outliner_kind(outliner_type)
    tb.show()
