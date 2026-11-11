"""Quebra uma prova (arquivo .fit) hora a hora: km, D+, D-, FC média/máx e % parado.

Mostra o padrão de largada (FC da 1ª hora) e onde o ritmo caiu.

Uso:
    uv run --with fitdecode scripts/prova_por_hora.py prova.fit [outra.fit ...] [--limiares 144 164 176]

Para baixar o .fit de uma atividade:
    python scripts/garmin_mcp.py call garmin_download_activity '{"activity_id": 123, "directory": "provas"}'
(o arquivo vai para Downloads/garmin/provas; descompacte o .zip)
"""
import argparse
import fitdecode


def ler(path):
    recs = []
    with fitdecode.FitReader(path) as fr:
        for m in fr:
            if isinstance(m, fitdecode.FitDataMessage) and m.name == "record":
                g = lambda k: m.get_value(k) if m.has_field(k) else None
                if g("timestamp"):
                    recs.append(dict(t=g("timestamp"), d=g("distance"), hr=g("heart_rate"),
                                     alt=g("enhanced_altitude") or g("altitude"), spd=g("enhanced_speed") or g("speed")))
    return recs


def resumo(path, limiares, janela=3600):
    recs = ler(path)
    if not recs:
        print(path, "sem registros")
        return
    t0 = recs[0]["t"]
    total = (recs[-1]["t"] - t0).total_seconds()
    print(f"===== {path}  ({total/3600:.2f} h)")
    print(" hora    km    D+    D-  FCméd  FCmáx  parado")
    i = 0
    while True:
        seg = [r for r in recs if i*janela <= (r["t"]-t0).total_seconds() < (i+1)*janela]
        if not seg:
            break
        km = ((seg[-1]["d"] or 0) - (seg[0]["d"] or 0))/1000
        up = dn = 0
        for a, b in zip(seg, seg[1:]):
            if a["alt"] is not None and b["alt"] is not None:
                x = b["alt"] - a["alt"]
                up += max(x, 0)
                dn += max(-x, 0)
        hr = [r["hr"] for r in seg if r["hr"]]
        parado = sum(1 for r in seg if (r["spd"] or 0) < 0.3)/len(seg)
        print(f" {i+1:4}  {km:4.1f}  {up:4.0f}  {dn:4.0f}  {sum(hr)/len(hr) if hr else 0:5.0f}  {max(hr) if hr else 0:5}  {100*parado:5.0f}%")
        i += 1
    hr = [r["hr"] for r in recs if r["hr"]]
    for th in limiares:
        print(f"  tempo com FC >= {th}: {100*sum(h >= th for h in hr)/len(hr):.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fits", nargs="+")
    ap.add_argument("--limiares", nargs="*", type=int, default=[144, 164, 176],
                    help="FC para medir o tempo acima (padrão: início de Z3, Z4 e limiar)")
    a = ap.parse_args()
    for f in a.fits:
        resumo(f, a.limiares)
