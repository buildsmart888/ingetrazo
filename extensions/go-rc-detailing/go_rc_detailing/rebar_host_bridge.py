"""Optional bridge between GO RC solid reinforcement and patched IngeTrazo.

No host monkey-patching.  Never changes mesh vertices, bar centreline design,
BBS, or IFC tags.  An unsupported host simply keeps the original solid view.
The passed points MUST be in the rebar mesh's local coordinates.
"""
from __future__ import annotations
import hashlib
import math
import os
import struct


def _triples(points):
    result=[]
    for p in points:
        if hasattr(p, 'x') and callable(p.x):
            xyz=(float(p.x()),float(p.y()),float(p.z()))
        else:
            xyz=tuple(float(a) for a in p)
        if len(xyz)!=3 or not all(math.isfinite(a) for a in xyz):
            raise ValueError('centreline must have finite 3D points')
        if not result or xyz!=result[-1]:
            result.append(xyz)
    if len(result)<2 or not any(a!=b for a,b in zip(result,result[1:])):
        raise ValueError('centreline needs at least one nonzero segment')
    return tuple(result)


def _definition_key(points, diameter_m):
    h=hashlib.sha256(b'go-rc-rebar-centreline-v1')
    h.update(struct.pack('<f',float(diameter_m)))
    for p in points:
        h.update(struct.pack('<3f',*p))
    return 'go-rc-' + h.hexdigest()[:24]


def path_length(points):
    p=_triples(points)
    return sum(math.dist(a,b) for a,b in zip(p,p[1:]))


def attach_local_centerline(group, points_local, diameter_mm, cache=None):
    """Return (bool, reason); failure never alters IFC/BBS/geometry.

    `cache` is per build, shared by all instances of the same local prototype.
    Never generate an invented signature: use the loaded host's API only.
    """
    if os.environ.get('GO_RC_REBAR_LOD','1') == '0':
        return False,'disabled_by_environment'
    try:
        from core.rebar_display import attach_centerline
    except (ImportError, ModuleNotFoundError):
        return False,'host_missing_rebar_display'
    if not callable(attach_centerline):
        return False,'host_missing_attach_centerline'
    if getattr(group,'xform',None) is None:
        return False,'requires_local_mesh_instance'
    if (getattr(group,'ifc',None) or {}).get('class') != 'IfcReinforcingBar':
        return False,'not_ifc_rebar'
    try:
        pts=_triples(points_local)
        diameter_m=float(diameter_mm)/1000.0
        if not math.isfinite(diameter_m) or diameter_m<=0:
            raise ValueError('diameter must be positive')
        signature_key=(id(group.mesh),diameter_m,pts)
        if cache is not None and signature_key in cache:
            block=cache[signature_key]
            ext=dict(getattr(group,'ext',None) or {})
            ext['go_rebar']=block  # identical instances share immutable path block
            group.ext=ext
            return True,'shared_proxy'
        attach_centerline(group, pts, diameter_m, _definition_key(pts,diameter_m))
        block=(getattr(group,'ext',None) or {}).get('go_rebar')
        if (not isinstance(block,dict)
                or not block.get('mesh_signature')
                or block.get('version')!=1):
            return False,'host_did_not_sign_proxy'
        if cache is not None:
            cache[signature_key]=block
        return True,'signed_proxy'
    except Exception as exc:
        # LOD is strictly optional. Invalid metadata must not abort a beam or
        # column build which had already passed its geometry acceptance.
        return False,type(exc).__name__ + ': ' + str(exc)


def attach_beam_proxies(state):
    """Attach to the accepted Phase2 beam leaves, BEFORE scene publication.

    state.bar_geom already owns authoritative world-path samples and offset
    metadata. Undo that translation, never alter the shared mesh or re-fillet.
    """
    members={g.name:g for g in state.items}
    cache={}
    totals={'attempted':0,'attached':0,'unique_definitions':0,'reasons':{}}
    for row in state.bar_geom:
        name=row['name']
        group=members.get(name)
        if group is None:
            totals['reasons']['missing_part']=totals['reasons'].get('missing_part',0)+1
            continue
        totals['attempted']+=1
        if row.get('kind')=='stirrup':
            # All stirrups share the EXACT mesh/prototype-local path.
            # Subtracting a 12 m world station again loses floating point
            # low bits (v.x()+x)-x != v.x(), and needlessly breaks sharing.
            points=list(state.tie_path)
        else:
            dx,dy,dz=(float(v) for v in row['offset'])
            points=[(float(v.x())-dx,float(v.y())-dy,float(v.z())-dz)
                    for v in row['points']]
        before=len(cache)
        ok,reason=attach_local_centerline(group,points,row['diameter_mm'],cache)
        totals['attached']+=int(ok)
        totals['unique_definitions']+=len(cache)-before
        if not ok:
            totals['reasons'][reason]=totals['reasons'].get(reason,0)+1
    return totals
