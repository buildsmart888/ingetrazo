"""Schematic centerline fillet algorithm ported from accepted GO RC v0.7.

This reproduces the polygonal fillet that the legacy beam uses for its BBS,
NOT a bending-pin or cut-length calculation for workshop fabrication.
"""
from __future__ import annotations
import math
from .vector import Vec3, as_vec3
EPS = 1e-9


def dedupe(points, tol: float = 1e-7) -> list[Vec3]:
    out: list[Vec3] = []
    for pt in points:
        p = as_vec3(pt)
        if not out or (p-out[-1]).length() > tol:
            out.append(p)
    return out


def fillet_corner(p0: Vec3, p1: Vec3, p2: Vec3, r: float, segments: int = 8) -> list[Vec3]:
    """Mathematically identical construction to v0.7 _fillet_corner."""
    a1, a2 = p0-p1, p2-p1
    L1, L2 = a1.length(), a2.length()
    if L1 < EPS or L2 < EPS or r <= 0:
        return [p1]
    v1, v2 = a1/L1, a2/L2
    dot = max(-1.0, min(1.0, Vec3.dotProduct(v1, v2)))
    angle = math.acos(dot)
    if angle < 1e-4 or abs(angle-math.pi) < 1e-4:
        return [p1]
    half = math.tan(angle/2.0)
    t = r/half
    max_t = 0.5*min(L1, L2)
    if t > max_t:
        t = max_t
        r = t*half
    t1, t2 = p1+v1*t, p1+v2*t
    bisector = (v1+v2).normalized()
    if bisector.length() < EPS:
        return [p1]
    center = p1 + bisector*(r/math.sin(angle/2.0))
    u = t1-center
    v = t2-center
    n = Vec3.crossProduct(u,v).normalized()
    if n.length() < EPS:
        return [p1]
    u_ortho = Vec3.crossProduct(n,u).normalized()*u.length()
    arc = math.pi-angle
    return [center+u*math.cos(arc*i/segments)+u_ortho*math.sin(arc*i/segments)
            for i in range(segments+1)]


def fillet_path(points, radius_m: float, segments: int = 8, closed: bool = False) -> list[Vec3]:
    if segments < 2:
        raise ValueError("fillet segments must be >= 2")
    pts = dedupe(points)
    n = len(pts)
    if n < 3 or radius_m <= 0:
        return list(pts)
    out: list[Vec3] = []
    if closed:
        rng = range(n)
    else:
        out.append(pts[0])
        rng = range(1,n-1)
    for i in rng:
        out.extend(fillet_corner(pts[i-1],pts[i],pts[(i+1)%n],radius_m,segments))
    if not closed:
        out.append(pts[-1])
    return out


def path_length(points) -> float:
    pts = [as_vec3(p) for p in points]
    return sum((pts[i+1]-pts[i]).length() for i in range(len(pts)-1))


def segment_distance(p0, p1, q0, q1) -> float:
    """v0.7 finite segment closest-distance algorithm for shadow parity."""
    p0,p1,q0,q1=map(as_vec3,(p0,p1,q0,q1))
    u=p1-p0;v=q1-q0;w=p0-q0
    a=Vec3.dotProduct(u,u);b=Vec3.dotProduct(u,v)
    c=Vec3.dotProduct(v,v);d=Vec3.dotProduct(u,w)
    e=Vec3.dotProduct(v,w);det=a*c-b*b
    s=0.;t=0.
    if det>1e-17:
        s=max(0.,min(1.,(b*e-c*d)/det))
    elif a>EPS:
        s=max(0.,min(1.,-d/a))
    if c>EPS:
        t=max(0.,min(1.,(b*s+e)/c))
    if a>EPS:
        s=max(0.,min(1.,(b*t-d)/a))
    if c>EPS:
        t=max(0.,min(1.,(b*s+e)/c))
    return (w+u*s-v*t).length()


def minimum_polyline_distance(line_a,line_b) -> float:
    if len(line_a)<2 or len(line_b)<2:
        return 1e9
    return min(segment_distance(a,c,b,d)
               for a,c in zip(line_a,line_a[1:])
               for b,d in zip(line_b,line_b[1:]))
