"""Theoretical allocation of 3D bar centreline length to support-centre spans.

Splits segments at support-centre planes (not a construction length of
reinforcement in the beam-column joint). Accepted v0.7 allocation rules.
"""
from __future__ import annotations
from ..geometry.vector import as_vec3
from ..geometry.fillet import path_length


def allocate_to_spans(centreline, spans_m: tuple[float, ...] | list[float]) -> list[float]:
    if not spans_m or min(spans_m) <= 0:
        raise ValueError("spans must be positive")
    xedges=[0.0]
    for span in spans_m:
        xedges.append(xedges[-1]+span)
    result=[0.0]*len(spans_m)
    points=[as_vec3(p) for p in centreline]
    for a,b in zip(points,points[1:]):
        total=(b-a).length()
        if total<1e-12:
            continue
        cuts=[0.,1.]
        delta=b.x()-a.x()
        if abs(delta)>1e-12:
            for x in xedges[1:-1]:
                t=(x-a.x())/delta
                if 1e-10<t<1-1e-10:
                    cuts.append(t)
        cuts=sorted(set(cuts))
        for ta,tb in zip(cuts,cuts[1:]):
            xm=a.x()+(ta+tb)/2*delta
            idx=min(len(spans_m)-1,max(0,
                next((i for i in range(len(spans_m))
                      if xedges[i]-1e-9<=xm<=xedges[i+1]+1e-9),len(spans_m)-1)))
            result[idx]+=total*(tb-ta)
    if abs(sum(result)-path_length(points))>0.00001:
        raise ValueError("Span quantity allocation lost rebar length")
    return result
