"""Support-face based left/middle/right stirrup stations.

Port of v0.7 span_stirrups with explicit parameters, no global state.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class TieZones:
    left_zone_m: float = 0.60
    left_spacing_m: float = 0.10
    mid_spacing_m: float = 0.15
    right_zone_m: float = 0.60
    right_spacing_m: float = 0.10
    first_left_m: float = 0.05
    first_right_m: float = 0.05

    def __post_init__(self):
        if any(getattr(self,k)<=0 for k in self.__dataclass_fields__):
            raise ValueError("tie zones, maximum spacings, and offsets must all be >0")


def span_stirrups(span_number: int, x0: float, x1: float, support_width_m: float,
                  cfg: TieZones) -> list[dict]:
    """Generate de-duplicated X-stations, preserving the v0.7 algorithm."""
    if x1 <= x0 or support_width_m <= 0:
        raise ValueError("span and support width must be positive")
    face_left=x0+support_width_m/2
    face_right=x1-support_width_m/2
    first=face_left+cfg.first_left_m
    last=face_right-cfg.first_right_m
    if not first < last:
        raise ValueError(f"Span {span_number}: tie start and end cross each other")
    usable=last-first
    len_l=cfg.left_zone_m;len_r=cfg.right_zone_m
    if len_l+len_r<=usable:
        a=first+len_l
        b=last-len_r
    else:
        a=first+usable*len_l/(len_l+len_r)
        b=a
    zones=[('left',first,a,cfg.left_spacing_m),
           ('middle',a,b,cfg.mid_spacing_m),
           ('right',b,last,cfg.right_spacing_m)]
    stations=[]
    for label,lo,hi,maxspacing in zones:
        if hi-lo<1e-9:
            continue
        pieces=max(1,math.ceil((hi-lo)/maxspacing-1e-10))
        for j in range(pieces+1):
            x=lo+(hi-lo)*j/pieces
            if stations and x-stations[-1]['x'] < 1e-7:
                if label not in stations[-1]['zones']:
                    stations[-1]['zones'].append(label)
                continue
            stations.append({'x':x,'zones':[label]})
    if len(stations)<2:
        raise ValueError(f"Span {span_number}: insufficient stirrup stations")
    if abs(stations[0]['x']-first)>1e-7 or abs(stations[-1]['x']-last)>1e-7:
        raise ValueError(f"Span {span_number}: first/last tie station incorrect")
    for a,b in zip(stations,stations[1:]):
        mid=(a['x']+b['x'])/2
        allowed=[maxspacing for lab,lo,hi,maxspacing in zones if lo<=mid<=hi and hi-lo>1e-9]
        if not allowed or b['x']-a['x'] > min(allowed)+1e-7:
            raise ValueError(f"Span {span_number}: tie spacing exceeded")
    return stations
