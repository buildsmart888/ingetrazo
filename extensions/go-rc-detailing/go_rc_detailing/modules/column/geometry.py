"""Pure geometry/measurement and adapter-free per-element algorithms."""
from __future__ import annotations
import math
from ...rc_core.quantity import bar_mass_kg_per_m, helix_centerline_length_m
from ...rc_core.rebar.end_projections import vertical_main_bar_stations

DENSITY_KG_M3 = 7850.0

def _kgpm(db_mm):
    # Phase 1: column module begins consuming the shared quantity service.
    # Original expression is retained inside the pure function; golden tests
    # ensure BBS masses are unchanged.
    return bar_mass_kg_per_m(db_mm, DENSITY_KG_M3)


def _tie_positions(p):
    low = p.first_tie_mm / 1000
    high = (p.height_mm-p.first_tie_mm) / 1000
    steps = max(1, math.ceil((high-low)/(p.tie_spacing_mm/1000)))
    return [low+(high-low)*i/steps for i in range(steps+1)]


def _rect_main_positions(p):
    """Symmetric inside-corner bars (avoid contact with rounded tie corners)."""
    db = p.longitudinal_db_mm / 1000
    dt = p.tie_db_mm / 1000
    cover = p.cover_mm / 1000
    R = 3.0 * dt  # geometry from approved beam tie function
    x_tie = p.width_mm/2000-cover-dt/2
    y_tie = p.depth_mm/2000-cover-dt/2
    # Set bars behind the actual rounded tie corner, leaving clearance to
    # the swept outside tie. Not an automatic code detailing arrangement.
    lim_x = x_tie - 0.65*R
    lim_y = y_tie - 0.65*R
    if min(lim_x, lim_y) <= 0:
        raise ValueError("No clear space for longitudinal bars in this rect column")
    loc=[]
    for ix in range(p.bars_x):
        x=-lim_x+2*lim_x*ix/(p.bars_x-1)
        loc.append((x,-lim_y))
        loc.append((x,lim_y))
    for iy in range(1,p.bars_y-1):
        y=-lim_y+2*lim_y*iy/(p.bars_y-1)
        loc.append((-lim_x,y))
        loc.append((lim_x,y))
    return loc


def _circle_main_positions(p):
    dt=p.tie_db_mm/1000
    db=p.longitudinal_db_mm/1000
    cover=p.cover_mm/1000
    rtie=p.diameter_mm/2000-cover-dt/2
    r=rtie-dt/2-db/2-0.002
    if r<=0:
        raise ValueError("No clear circular bar radius")
    return [(r*math.cos(2*math.pi*i/p.circular_bar_count),
             r*math.sin(2*math.pi*i/p.circular_bar_count))
            for i in range(p.circular_bar_count)]


def _min_clearance_xy(positions, diameter_m):
    return min(math.hypot(a[0]-b[0], a[1]-b[1])-diameter_m
               for i,a in enumerate(positions) for b in positions[i+1:])


def _box(eng, *coords, color, opacity=1.0):
    return eng["solid_box"](*coords,color,opacity)


def _cylinder(eng, radius, h, color, opacity, steps=64):
    mesh=eng["Mesh"]()
    V=eng["V"]
    bottom=[V(radius*math.cos(2*math.pi*i/steps),radius*math.sin(2*math.pi*i/steps),0) for i in range(steps)]
    top=[V(v.x(),v.y(),h) for v in bottom]
    eng["coloured_face"](mesh,reversed(bottom),color,opacity)
    eng["coloured_face"](mesh,top,color,opacity)
    for i in range(steps):
        j=(i+1)%steps
        eng["coloured_face"](mesh,[bottom[i],bottom[j],top[j],top[i]],color,opacity)
    return mesh


def _cylinder_shell(eng, inner_radius, outer_radius, h, color, opacity, steps=64):
    """Closed annulus with 4 faceted surfaces; no top/bottom formwork contact."""
    mesh=eng["Mesh"]()
    V=eng["V"]
    for i in range(steps):
        a=2*math.pi*i/steps
        b=2*math.pi*(i+1)/steps
        inn0=V(inner_radius*math.cos(a),inner_radius*math.sin(a),0)
        inn1=V(inner_radius*math.cos(b),inner_radius*math.sin(b),0)
        int0=V(inn0.x(),inn0.y(),h)
        int1=V(inn1.x(),inn1.y(),h)
        out0=V(outer_radius*math.cos(a),outer_radius*math.sin(a),0)
        out1=V(outer_radius*math.cos(b),outer_radius*math.sin(b),0)
        oot0=V(out0.x(),out0.y(),h)
        oot1=V(out1.x(),out1.y(),h)
        for face in ([out0,out1,oot1,oot0], [inn1,inn0,int0,int1],
                     [int0,oot0,oot1,int1],[out0,inn0,inn1,out1]):
            eng["coloured_face"](mesh,face,color,opacity)
    return mesh


def _spiral_rebar(eng, p):
    """A *single continuous* 3D helical reinforcement bar, not hoop copies.

    Uses a faceted centreline whose chordal length is distinct from the
    analytical spiral length. Returned analytical length for preliminary BBS:
    sqrt((2*pi*R*N)**2 + rise**2).
    """
    V=eng["V"]
    r=(p.diameter_mm/2.0-p.cover_mm-p.tie_db_mm/2.0)/1000.0
    if r <= 0:
        raise ValueError("No radius remains for spiral reinforcement")
    start=p.first_tie_mm/1000.0
    finish=(p.height_mm-p.first_tie_mm)/1000.0
    height=finish-start
    turns=max(1, math.ceil(height/(p.tie_spacing_mm/1000.0)))
    pitch=height/turns
    if pitch*1000 < p.tie_db_mm+2.0:
        raise ValueError("Actual spiral pitch causes self-contact")
    n=max(12, int(p.spiral_segments_per_turn))*turns
    pts=[V(r*math.cos(2*math.pi*turns*i/n),
           r*math.sin(2*math.pi*turns*i/n),
           start+height*i/n) for i in range(n+1)]
    tube,polyline_len=eng["make_rebar_mesh"](
        pts,p.tie_db_mm/1000.0,0.0,(0.85,0.74,0.30),closed=False)
    true_centerline_len=helix_centerline_length_m(r,turns,height)
    return tube, true_centerline_len, {
        "turns":turns,"pitch_actual_mm":pitch*1000.0,
        "polyline_length_m":polyline_len,"radius_centerline_m":r,
        "height_reinforced_m":height,"segments":n,
        "z_start_m":start,"z_end_m":finish}


def _hooked_main_bar(eng, p):
    """Share one main-bar prototype, bending independently at each end.

    Local -X points toward the column centre; +X splays radially outward.
    The swept centreline uses the same accepted 90-degree fillet math.
    """
    V=eng["V"]
    db=p.longitudinal_db_mm/1000.0
    r=4.0*db                # prototype centreline radius, not code approval
    stations = vertical_main_bar_stations(
        height_m=p.height_mm/1000.0,
        legacy_end_inset_m=(p.cover_mm+p.longitudinal_db_mm/2.0)/1000.0,
        top_projection_m=p.main_top_projection_mm/1000.0,
        bottom_projection_m=p.main_bottom_projection_mm/1000.0,
        top_hook=p.main_hook_top,
        bottom_hook=p.main_hook_bottom,
        bend_radius_m=r,
        top_hook_tail_m=p.main_hook_top_tail_mm/1000.0,
        bottom_hook_tail_m=p.main_hook_bottom_tail_mm/1000.0,
    )
    z0=stations.bottom_virtual_z_m
    z1=stations.top_virtual_z_m
    pts=[]
    if p.main_hook_bottom:
        reach=r+p.main_hook_bottom_tail_mm/1000.0
        bottom_sign = 1 if p.main_hook_bottom_direction == "outward" else -1
        pts += [V(bottom_sign*reach,0,z0),V(0,0,z0)]
    else:
        pts.append(V(0,0,z0))
    pts.append(V(0,0,z1))
    if p.main_hook_top:
        reach=r+p.main_hook_top_tail_mm/1000.0
        top_sign = 1 if p.main_hook_top_direction == "outward" else -1
        pts.append(V(top_sign*reach,0,z1))
    radius=r if len(pts)>2 else 0.0
    mesh,length=eng["make_rebar_mesh"](pts,db,radius,(0.26,0.42,0.80),closed=False)
    return mesh,length,pts,r


def _point_segment_distance_2d(a,b,c,d):
    # Conservative 2D capsule distance for horizontal hooked legs.
    def dot(u,v): return u[0]*v[0]+u[1]*v[1]
    ux=b[0]-a[0];uy=b[1]-a[1]
    vx=d[0]-c[0];vy=d[1]-c[1]
    wx=a[0]-c[0];wy=a[1]-c[1]
    aa=ux*ux+uy*uy;bb=ux*vx+uy*vy;cc=vx*vx+vy*vy
    dd=ux*wx+uy*wy;ee=vx*wx+vy*wy;den=aa*cc-bb*bb
    ss=0.0;tt=0.0
    sn=0.0;sd=den;tn=0.0;td=den
    if den < 1e-14:
        sn=0.;sd=1.;tn=ee;td=cc
    else:
        sn=(bb*ee-cc*dd);tn=(aa*ee-bb*dd)
        if sn < 0: sn=0.;tn=ee;td=cc
        elif sn>sd: sn=sd;tn=ee+bb;td=cc
    if tn<0:
        tn=0.
        if -dd<0:sn=0.
        elif -dd>aa:sn=sd
        else:sn=-dd;sd=aa
    elif tn>td:
        tn=td
        if (-dd+bb)<0:sn=0.
        elif (-dd+bb)>aa:sn=sd
        else:sn=-dd+bb;sd=aa
    ss=0. if abs(sn)<1e-15 else sn/sd
    tt=0. if abs(tn)<1e-15 else tn/td
    return math.hypot(wx+ss*ux-tt*vx,wy+ss*uy-tt*vy)


def _validate_main_hooks(p,positions):
    if not (p.main_hook_bottom or p.main_hook_top):
        return
    db=p.longitudinal_db_mm/1000.0
    cover=p.cover_mm/1000.0
    for end in ("bottom","top"):
        if not getattr(p,"main_hook_"+end):continue
        reach=4*db+getattr(p,"main_hook_"+end+"_tail_mm")/1000.0
        outward = getattr(p,"main_hook_"+end+"_direction") == "outward"
        legs=[]
        for x,y in positions:
            r=math.hypot(x,y)
            if r < 1e-9: raise ValueError("Cannot direct hook for centred longitudinal bar")
            sign = 1 if outward else -1
            tip=(x+sign*x*reach/r,y+sign*y*reach/r)
            if not outward:
                # Inward hooks MUST stay within the column cover envelope.
                if p.shape=="rect":
                    ok=(abs(tip[0])+db/2 <= p.width_mm/2000-cover+1e-8 and
                        abs(tip[1])+db/2 <= p.depth_mm/2000-cover+1e-8)
                else:
                    ok=math.hypot(*tip)+db/2 <= p.diameter_mm/2000-cover+1e-8
                if not ok:
                    raise ValueError(f"{end} 90-degree bar hook escapes concrete cover: shorten tail")
            else:
                # Explicitly OUTSIDE the column: don't falsely reject based
                # on its cover, or claim the footing/slab concrete exists.
                # Host embedment must be inspected independently.
                pass
            legs.append(((x,y),tip))
        # Intersections of horizontal hook tails -> physically overlapping ends.
        for i,(a,b) in enumerate(legs):
            for c,d in legs[i+1:]:
                if _point_segment_distance_2d(a,b,c,d) < db + .002:
                    raise ValueError(
                        f"{end} main bar hook tails clash in XY: reduce tail length or enlarge column")

