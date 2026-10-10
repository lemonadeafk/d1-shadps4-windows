r"""Decode a Director destination's activity rules from the running game (and what each needs).

    python tools\director_rules.py [dest_index]     # 12 = Tower book (default), 10 = Earth

Each Director entry carries a rule list; rules are tried from the highest index down and the first
whose unlock expression is true gives the entry's status: 0 hidden, 2 "Requirements Not Met",
3/4 selectable. FLAG(n)=v shows the flag's current value in the client's unlock table (2 = set).
Found 2026-10-10: Tower entry 0 is status 4 only with FLAG(131) or FLAG(3136); the launch
validator (0x546B30) separately requires NOT FLAG(3389) and NOT FLAG(308) ("banned from social
spaces" otherwise).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import argparse, contextlib, io, struct
from d1guest_win import d1guest
ns = argparse.Namespace(symbols=d1guest.SYMBOLS, eboot=None, ignore_build_gate=False, full_scan=False,
                        no_cache=False, allow_dead=True, account_soid=None, require=0)
with contextlib.redirect_stdout(io.StringIO()):
    syms, image, proc, g = d1guest.open_guest(ns)
B = g.base
def q(a): return struct.unpack('<Q', proc.read(a, 8))[0]
def d(a): return struct.unpack('<I', proc.read(a, 4))[0]
import ctypes,sys
OPS={1:'FLAG',2:'NOT',3:'OR',4:'AND',5:'NOR',6:'NE',7:'NAND',8:'EQ',9:'NE',10:'VALUE',11:'CONST',12:'GT',13:'GE',14:'LT',15:'LE',16:'ADD',17:'SUB',18:'MUL',19:'DIV',20:'MOD',21:'NEG'}
plane=q(B+0x26A34B0+0x38)+0xC
def resolve(t):
    t=ctypes.c_int32(t).value
    ecx=t>>13; esi=((ecx & 0xffffffff)>>18 | 0x3ff) & ecx & 0xffffffff
    reg=q(q(B+0x1A0B420)); e=reg+esi*0x40
    data=q(e+0x10); stride=d(e+0x30); mask=ctypes.c_int32(d(e+0x34)).value & 0xffffffffffffffff
    p=data+(t&0x1fff)*stride
    return (p-(q(p+8)&mask))%2**64
def arr(L): return q(L), L+8+q(L+8)+0x10
def expr(E):
    n,base=arr(E); out=[]
    for i in range(min(n,32)):
        s=proc.read(base+i*8,8); op=s[0]; operand=struct.unpack_from('<I',s,4)[0]
        t=OPS.get(op,str(op))
        if op==1: t+=f'({operand&0xffff})={proc.read(plane+(operand&0xffff),1)[0]}'
        elif op==10: t+=f'({operand&0xffff})={struct.unpack("<i",proc.read(plane+0x2000+4*(operand&0xffff),4))[0]}'
        elif op==11: t+=f'({operand})'
        out.append(t)
    return ' '.join(out) if out else '<always>'
igc=q(B+0x2639AF8)
T=resolve(d(igc+0x38))+8; tn=ctypes.c_int32(d(T)).value; tb=T+8+q(T+8)+0x10
dest=int(sys.argv[1]) if len(sys.argv)>1 else 12
tag=d(tb+dest*0x18+0x10); book=resolve(tag)
n,eb=arr(book+8)
print(f'dest {dest}: book tag {tag:#x} @ {book:#x}, {n} entries; head {proc.read(book,0x20).hex(" ",4)}')
X=q(B+0x26A3BA0+0x10); st=proc.read(X+0x5E0+dest*0x4C+8,0x44)
for j in range(min(n,0x44)):
    e=eb+j*0x28; rn,rb=arr(e+0x18)
    print(f' entry {j} status_now={st[j]} raw {proc.read(e,0x18).hex(" ",4)}')
    for k in range(rn-1,-1,-1):
        r=rb+k*0x18; print(f'     rule {k}: status {proc.read(r,1)[0]}  if  {expr(r+8)}')
