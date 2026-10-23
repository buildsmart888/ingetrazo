"""Read-only native / nested BIM tree for GO RC Detailing (API v2).

IngeTrazo v0.5.9 native BIM tray scans top-level tagged groups only.
GO RC supports either a native-visible flat layout or a nested assembly.
This panel works with BOTH without duplicating geometry.
"""
from __future__ import annotations


def _iter_tree(group, depth=0):
    yield group,depth
    for child in getattr(group,'children',()) or ():
        yield from _iter_tree(child,depth+1)


def _is_assembly(group):
    ext=getattr(group,'ext',None) or {}
    for key in ('go_rc_beam','go_rc_column'):
        if (ext.get(key) or {}).get('kind')=='assembly':
            return True
    return ("-RC Continuous Beam Assembly" in (group.name or '') or
            "-RC Rectangular Column Assembly" in (group.name or '') or
            "-RC Circular Column Assembly" in (group.name or ''))


def nested_bim_summary(scene):
    """Returns 1 logical assembly per beam or column in either display mode."""
    entries=[]
    flat={}
    for g in scene.groups:
        ext=getattr(g,'ext',None) or {}
        pub=ext.get('go_rc_native_bim')
        if pub:
            group_name=pub['original_parent']
            flat.setdefault(group_name,[]).append(g)
            continue
        if not _is_assembly(g):
            continue
        nodes=[]
        for part,depth in _iter_tree(g):
            ifc=getattr(part,'ifc',None) or {}
            nodes.append({'depth':depth,'name':part.name,
                          'ifc_class':ifc.get('class',''), 'has_bim_tag':bool(ifc)})
        entries.append({'parent':g.name,'mode':'NESTED', 'nodes':nodes,
                        'tagged_leaves':sum(x['has_bim_tag'] for x in nodes)})
    for group_name,leaves in flat.items():
        nodes=[{'depth':0,'name':group_name,'ifc_class':'',
                'has_bim_tag':False}]
        nodes.extend({'depth':1,'name':g.name,
                      'ifc_class':(g.ifc or {}).get('class',''),
                      'has_bim_tag':bool(g.ifc)} for g in leaves)
        entries.append({'parent':group_name,'mode':'NATIVE BIM',
                        'nodes':nodes,'tagged_leaves':sum(bool(g.ifc) for g in leaves)})
    return entries


def install_bim_panel(app):
    if not hasattr(app,'add_panel'):
        return None
    from PySide6.QtWidgets import (QWidget,QVBoxLayout,QTreeWidget,QTreeWidgetItem,
                                   QLabel,QHBoxLayout,QPushButton)
    widget=QWidget(app.window)
    box=QVBoxLayout(widget)
    intro=QLabel("Nested assemblies: GO BIM tree. Native BIM mode: tagged top-level parts are also visible in IngeTrazo BIM tray.")
    intro.setWordWrap(True)
    box.addWidget(intro)
    title=QLabel("No GO RC objects in this document")
    box.addWidget(title)
    tree=QTreeWidget(widget)
    tree.setHeaderLabels(['Object / Part', 'IFC class'])
    tree.setAlternatingRowColors(True)
    box.addWidget(tree,1)
    bottom=QHBoxLayout()
    reload=QPushButton('Refresh BIM',widget)
    bottom.addWidget(reload)
    box.addLayout(bottom)

    def refresh():
        if not widget.isVisible():
            return
        data=nested_bim_summary(app.scene)
        tree.clear()
        total=0
        for assembly in data:
            top=QTreeWidgetItem([assembly['parent'],assembly['mode']])
            tree.addTopLevelItem(top)
            stack={0:top}
            for row in assembly['nodes'][1:]:
                depth=row['depth']
                container=stack.get(depth-1,top)
                child=QTreeWidgetItem([row['name'],row['ifc_class'] or 'Group'])
                container.addChild(child)
                stack[depth]=child
                total+=int(row['has_bim_tag'])
            top.setExpanded(True)
        title.setText(f'{len(data)} assemblies / {total} tagged BIM parts')
    reload.clicked.connect(refresh)
    dock=app.add_panel('GO RC BIM',widget,name='go_rc_bim',start_hidden=True)
    app.on_document_changed(refresh)
    app.add_menu_action('GO RC BIM Browser...',lambda:(app.show_panel(dock),refresh()),
                        tip='Inspect IFC-tagged GO RC beam and column parts')
    return dock
