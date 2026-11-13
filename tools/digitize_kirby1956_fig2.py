"""Reproducible digitization of Kirby (1956) Fig. 2 (PTFE expansion, 0-110 C).

Used to build the 274-383 K segment of ``data/seal_materials.yaml`` (ptfe).

Steps (run from any directory, Python with numpy + pillow):
  1. Download https://nvlpubs.nist.gov/nistpubs/jres/057/jresv57n2p91_A1b.pdf
  2. pdftoppm -f 3 -l 3 -r 600 -gray -png jresv57n2p91_A1b.pdf kh
  3. Crop rows 2960:5020, cols 240:2240 of kh-3.png -> fig2.png
  4. python tools/digitize_kirby1956_fig2.py fig2.png > ptfe_rows.json

Axis calibration: tick-mark pixel rows on the left and right frame (page skew is
interpolated between them); x: frame at 0 C and 110 C. The curve is traced column-wise
from both ends and row-wise through the steep ~20 C transition. Above 28 C the trace is
replaced by a cubic least-squares fit (marker artefacts), then isotonic smoothing, then a
piecewise-linear anchor to Kirby's Table 2 values at 0, 25, 50, 100 C.
"""
import sys
FIG = sys.argv[1]
from PIL import Image; import numpy as np, json
a=np.array(Image.open(FIG).convert('L')).astype(int)
d=a<140
vals=np.array([1.2,1.0,0.8,0.6,0.4,0.2,0.0,-0.2,-0.4,-0.6])
left=np.array([29,246.5,464.5,682,899,1118.5,1337.5,1555.5,1776,1994.5])
right=np.array([25,243.2,461,678.5,897.5,1115.5,1334.5,1554.5,1772.5,1993.5])
XL,XR=190.5,1961.5
x_to_C=lambda x:(x-XL)/(XR-XL)*110.0
def y_to_pct(x,y):
    f=(x-XL)/(XR-XL); return float(np.interp(y, left*(1-f)+right*f, vals))
def clusters(idx):
    if len(idx)==0: return []
    cl=[];cur=[idx[0]]
    for v in idx[1:]:
        if v-cur[-1]<=2: cur.append(v)
        else: cl.append(cur); cur=[v]
    cl.append(cur); return [(float(np.mean(c)),len(c)) for c in cl]
def track_cols(xs, y0, maxlen=12):
    pts=[]
    for x in xs:
        cands=clusters(np.where(d[40:1985,x])[0]+40)
        if not cands: continue
        if len(pts)<2: pred, tol = (y0 if not pts else pts[-1][1]), 40
        else:
            (x1,y1)=pts[-12] if len(pts)>12 else pts[0]; (x2,y2)=pts[-1]
            pred=y2+(y2-y1)/(x2-x1)*(x-x2); tol=6+0.5*abs(x-x2)
        c=min(cands,key=lambda c:abs(c[0]-pred))
        if abs(c[0]-pred)>tol or c[1]>maxlen: continue
        pts.append((x,c[0]))
    return pts
yfor=lambda pct,x: float(np.interp(pct, vals[::-1], (left*(1-(x-XL)/(XR-XL))+right*(x-XL)/(XR-XL))[::-1]))
L=track_cols(range(196, int(XL+16.1*17)), yfor(-0.49,196))
R=track_cols(range(1955, int(XL+16.1*23), -1), yfor(1.07,1955))
R=R[::-1]
# middle: row-wise between last L y and first R y
yL=L[-1][1]; yR=R[0][1]; xprev=L[-1][0]; mid=[]
for y in range(int(yL)-1, int(yR), -1):
    row=np.where(d[y, int(XL+16.1*15):int(XL+16.1*25)])[0]+int(XL+16.1*15)
    cands=clusters(row)
    if not cands: continue
    c=min(cands,key=lambda c:abs(c[0]-xprev))
    if abs(c[0]-xprev)>20 or c[1]>14: continue
    xprev=c[0]; mid.append((c[0],float(y)))
pts=[(x_to_C(x),y_to_pct(x,y)) for x,y in L+mid+R]
pts.sort()
# collapse duplicate/near x (row-wise pts) by averaging into 0.1 C bins, enforce monotone
arr=np.array(pts)
bins=np.round(arr[:,0],1); ub=np.unique(bins)
res=np.array([[b, arr[bins==b,1].mean()] for b in ub])

y = res[:, 1].copy(); T = res[:, 0]
m = (T >= 27) & (T <= 110)
p = np.polyfit(T[m], y[m], 3)
y = np.where(T >= 28, np.polyval(p, T), y)


def pav(v):
    out = []
    for i, x in enumerate(v):
        out.append([x, 1, [i]])
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            a2 = out.pop(); b2 = out.pop()
            out.append([(a2[0] * a2[1] + b2[0] * b2[1]) / (a2[1] + b2[1]), a2[1] + b2[1], b2[2] + a2[2]])
    r = np.empty(len(v))
    for x, _, ii in out:
        r[ii] = x
    return r


yi = pav(y)
tr = lambda t: float(np.interp(t, T, yi))
aT = [0, 25, 50, 100]; aV = [-0.500, 0.0, 0.310, 0.930]  # Kirby Table 2, percent
resid = [v - tr(t) for t, v in zip(aT, aV)]
grid = list(range(1, 46)) + list(range(50, 111, 5))
out = [(round(273.15 + t, 2), round(tr(t) + float(np.interp(t, aT, resid)), 4)) for t in grid]
print(json.dumps(out))
