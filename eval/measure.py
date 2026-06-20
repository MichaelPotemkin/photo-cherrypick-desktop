import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def run():
    for m in list(sys.modules):
        if m.startswith("pipeline") or m.startswith("eval"): del sys.modules[m]
    from eval.rescore import score_groups
    return score_groups()
def measure(label):
    ref=json.load(open("eval/reference_panel.json"))
    res=run()
    tot=un_t=un_a=maj_t=maj_a=a=0; misses=[]
    for gi,r in ref.items():
        if gi not in res or not r["pick"]: continue
        ok=res[gi]["pick"]==r["pick"]; tot+=1; a+=ok
        if r["consensus"]=="unanimous": un_t+=1; un_a+=ok
        else: maj_t+=1; maj_a+=ok
        if not ok: misses.append((gi,r["consensus"],res[gi]["pick"],r["pick"],round(res[gi]["gap"],3)))
    print(f"\n[{label}] panel agreement: {a}/{tot} ({a/tot*100:.0f}%) | unanimous {un_a}/{un_t} ({un_a/un_t*100:.0f}%) | majority {maj_a}/{maj_t} ({maj_a/maj_t*100:.0f}%)")
    print(f"  misses ({len(misses)}): "+ " ".join(f"g{gi}({c[:3]},gap{gap})" for gi,c,p,w,gap in sorted(misses,key=lambda x:int(x[0]))))
    return misses
if __name__=="__main__":
    measure(sys.argv[1] if len(sys.argv)>1 else "?")
