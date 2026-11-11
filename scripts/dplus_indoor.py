"""Estima o D+ de esteira inclinada e escada, que o Garmin grava como zero.

Para cada sessão de esteira ou escada no período:
1. Baixa o treino estruturado (garmin_get_activity_workouts). Se o treinador escreveu a
   inclinação no passo (ex.: "15% DE INCLINAÇÃO"), D+ = distância da volta x inclinação.
   As voltas do .fit trazem wkt_step_index, que liga cada volta ao passo do treino.
   "°" é tratado como %: em esteira o painel mostra %, e a FC confirma.        [confiança alta]
2. Sem anotação: voltas caminhando (cadência < 70 por pé) com FC >= 130 viram subida.
   A inclinação sai da equação de caminhada do ACSM, com o VO2 estimado pela FC usando a
   relação VO2/FC do próprio atleta (tirada das voltas correndo no plano).       [confiança média]
3. Escada (simulador): equação de step do ACSM com degrau de 20 cm, VO2 pela FC. [confiança baixa]

Uso:
    uv run --with fitdecode scripts/dplus_indoor.py --inicio 2026-01-01 --fim 2026-11-30 -o dplus.csv

Os .fit são baixados em Downloads/garmin/indoor (exigência do servidor) e lidos de lá.
Se o atleta colocar "D+ 400" no título da atividade, esse valor tem prioridade.
"""
import argparse
import csv
import json
import os
import re
import statistics as st
import zipfile
from pathlib import Path

import fitdecode

from garmin_mcp import GarminMCP

FC_REPOUSO = 46        # ajuste para o atleta (FC de repouso média)
DEGRAU_M = 0.20
TIPOS = ("treadmill_running", "stair_climbing")


def voltas(fit_path):
    laps, sess = [], {}
    with fitdecode.FitReader(fit_path) as fr:
        for m in fr:
            if not isinstance(m, fitdecode.FitDataMessage):
                continue
            g = lambda k: m.get_value(k) if m.has_field(k) else None
            if m.name == "lap":
                laps.append(dict(t=g("total_timer_time"), d=g("total_distance"), hr=g("avg_heart_rate"),
                                 cad=g("avg_running_cadence") or g("avg_cadence"), passo=g("wkt_step_index")))
            elif m.name == "session":
                sess = dict(t=g("total_timer_time"), d=g("total_distance"))
    return laps, sess


def notas_inclinacao(workouts):
    """{indice_do_passo: inclinação em %} a partir das anotações do treinador."""
    out = {}
    for w in workouts.get("results", []):
        for s in w.get("steps") or []:
            n = (s.get("notes") or "").strip()
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(%|°|º)", n)
            if m:
                out[s["stepIndex"]] = float(m.group(1).replace(",", "."))
            elif re.search(r"plano", n, re.I):
                out[s["stepIndex"]] = 0.0
    return out


def vo2_corrida(v):          # v em m/min, plano
    return 0.2 * v + 3.5


def inclinacao_caminhada(vo2, v):
    return (vo2 - 3.5 - 0.1 * v) / (1.8 * v)


def baixar_fit(g, aid):
    info = g.call_json("garmin_download_activity", {"activity_id": aid, "directory": "indoor"})
    with zipfile.ZipFile(info["path"]) as z:
        nome = [n for n in z.namelist() if n.lower().endswith(".fit")][0]
        destino = Path(info["path"]).with_suffix(".fit")
        destino.write_bytes(z.read(nome))
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inicio", required=True)
    ap.add_argument("--fim", required=True)
    ap.add_argument("-o", "--out", default="dplus_indoor.csv")
    ap.add_argument("--fc-repouso", type=int, default=FC_REPOUSO)
    a = ap.parse_args()

    with GarminMCP() as g:
        atividades = [x for x in g.all_activities(a.inicio, a.fim) if x["activityType"]["typeKey"] in TIPOS]
        print(f"{len(atividades)} sessões de esteira/escada")
        dados = []
        for x in atividades:
            aid = x["activityId"]
            try:
                wk = g.call_json("garmin_get_activity_workouts", {"activity_id": aid})
            except RuntimeError:
                wk = {}
            laps, sess = voltas(baixar_fit(g, aid))
            dados.append((x, wk, laps, sess))

    # relação VO2/FC pessoal, a partir das voltas correndo no plano
    def k_de(laps):
        ks = []
        for l in laps:
            if l["t"] and l["t"] > 120 and l["d"] and l["hr"] and (l["cad"] or 0) >= 75:
                v = l["d"] / l["t"] * 60
                if 120 < v < 220:
                    ks.append(vo2_corrida(v) / (l["hr"] - a.fc_repouso))
        return ks
    k_geral = st.median([k for _, _, laps, _ in dados for k in k_de(laps)] or [0.3])

    linhas = []
    for x, wk, laps, sess in sorted(dados, key=lambda d: d[0]["startTimeLocal"]):
        titulo = x.get("activityName") or ""
        manual = re.search(r"D\+\s*(\d+)", titulo)
        notas = notas_inclinacao(wk)
        ks = k_de(laps)
        k = st.median(ks) if len(ks) >= 2 else k_geral
        dplus, base = 0.0, set()
        if manual:
            dplus, base = float(manual.group(1)), {"título da atividade"}
        elif x["activityType"]["typeKey"] == "treadmill_running":
            for l in laps:
                if not l["t"] or l["t"] < 60 or not l["d"]:
                    continue
                if l["passo"] is not None and l["passo"] in notas:
                    if notas[l["passo"]]:
                        dplus += l["d"] * notas[l["passo"]] / 100
                        base.add("texto do treinador")
                elif (l["cad"] or 99) < 70 and l["hr"] and l["hr"] >= 130:
                    v = l["d"] / l["t"] * 60
                    incl = max(0.0, min(0.20, inclinacao_caminhada(k * (l["hr"] - a.fc_repouso), v)))
                    if incl >= 0.03:
                        dplus += l["d"] * incl
                        base.add("estimado pela FC")
        elif laps and laps[0]["hr"] and sess.get("t"):
            vo2 = k * (laps[0]["hr"] - a.fc_repouso)
            passos_min = (vo2 - 3.5) / (0.2 + 1.33 * 1.8 * DEGRAU_M)
            dplus = passos_min * DEGRAU_M * sess["t"] / 60
            base.add("escada: estimado pela FC")
        linhas.append([x["startTimeLocal"][:10], x["activityType"]["typeKey"], titulo,
                       round((sess.get("t") or 0) / 60), round(dplus), " + ".join(sorted(base)) or "sem subida", x["activityId"]])

    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["data", "tipo", "titulo", "minutos", "dplus_m", "base", "activity_id"])
        w.writerows(linhas)
    for l in linhas:
        print(f"{l[0]}  {l[1][:9]:9}  {l[3]:4} min  {l[4]:5} m  {l[5]}")
    print(f"TOTAL ~{sum(l[4] for l in linhas)} m · VO2/FC pessoal = {k_geral:.3f} · salvo em {a.out}")


if __name__ == "__main__":
    main()
