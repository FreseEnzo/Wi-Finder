"""Linha de comando: python3 -m wifinder [app|pull|import|estimate|report|simulate|collect]"""

import argparse
import csv
import statistics
from pathlib import Path


def main():
    from . import __version__

    ap = argparse.ArgumentParser(prog="wifinder", description=__doc__)
    ap.add_argument("--version", action="version", version=f"wifinder {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("app", help="tela inicial no navegador (é o que abre sem nenhum comando)")
    a.add_argument("--dir", help="pasta onde os voos ficam guardados (padrão: voos; no executável, ao lado dele)")
    a.add_argument("--port", type=int, default=8737)
    a.add_argument("--no-browser", action="store_true", help="não abre o navegador sozinho")

    p = sub.add_parser("pull", help="baixa os logs do ESP32 pela USB e importa no banco")
    p.add_argument("db", help="banco de saída (criado se não existir)")
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--dir", help="pasta para guardar os logs (padrão: <db>-logs)")
    p.add_argument("--rm", action="store_true", help="apaga os logs da placa depois de baixar")

    i = sub.add_parser("import", help="importa logs do ESP32 já baixados")
    i.add_argument("db")
    i.add_argument("logs", nargs="+", help="arquivos v###.log")

    c = sub.add_parser("collect", help="coleta em voo (na Raspberry Pi, como root)")
    c.add_argument("db", nargs="?", help="arquivo de saída (padrão: voo-<data>.db)")
    c.add_argument("--iface", default="wlan0")
    c.add_argument("--gps", default="/dev/serial0", help="porta serial do GPS")
    c.add_argument("--baud", type=int, default=9600)
    c.add_argument("--band", choices=["2.4", "all"], default="2.4",
                   help="2.4 varre só 2,4 GHz (mais rápido); all inclui 5 GHz")

    s = sub.add_parser("simulate", help="gera um voo sintético para testes")
    s.add_argument("db")
    s.add_argument("--ambiente", choices=["cidade", "selva"], default="cidade",
                   help="selva: drone acima da copa, perda por vegetação, roteadores esparsos")
    s.add_argument("--routers", type=int, help="número de roteadores (padrão do ambiente)")
    s.add_argument("--alt", type=float, help="altura de voo em m (padrão do ambiente)")
    s.add_argument("--lane", type=float, help="espaço entre faixas em m (padrão do ambiente)")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--esp32-log", metavar="ARQ",
                   help="grava o voo como log do ESP32 (para testar pull/import)")

    e = sub.add_parser("estimate", help="estima os roteadores e gera CSV + mapa")
    e.add_argument("db")
    e.add_argument("--ground-alt", type=float, help=argparse.SUPPRESS)   # aceitos por
    e.add_argument("--min-samples", type=int, help=argparse.SUPPRESS)    # compatibilidade

    r = sub.add_parser("report", help="gera relatório em PDF (resumo, mapa de satélite e tabela)")
    r.add_argument("db")
    r.add_argument("--out", help="arquivo PDF (padrão: <db>-relatorio.pdf)")
    r.add_argument("--ground-alt", type=float, help=argparse.SUPPRESS)
    r.add_argument("--min-samples", type=int, help=argparse.SUPPRESS)
    r.add_argument("--sem-fundo", action="store_true", help="não baixa o satélite")

    args = ap.parse_args()
    if args.cmd in (None, "app"):
        from . import app
        app.serve(getattr(args, "dir", None), getattr(args, "port", 8737),
                  open_browser=not getattr(args, "no_browser", False))
    elif args.cmd == "pull":
        from . import db, esp32
        con = db.connect(args.db)
        out = args.dir or f"{Path(args.db).with_suffix('')}-logs"
        esp32.pull(con, args.port, out, remove=args.rm)
        con.close()
        print(f"Logs em {out}/. Agora: python3 -m wifinder estimate {args.db}")
    elif args.cmd == "import":
        from . import db, esp32
        con = db.connect(args.db)
        for path in args.logs:
            res = esp32.import_log(con, Path(path).read_text(errors="replace"), Path(path).name)
            print(f"{path}: " + ("já importado" if res is None
                  else f"{res[0]} fixes, {res[1]} amostras ({res[2]} sem posição)"))
        con.close()
    elif args.cmd == "report":
        run_report(args)
    elif args.cmd == "collect":
        import time
        from . import collect
        path = args.db or time.strftime("voo-%Y%m%d-%H%M%S.db")
        collect.run(path, args.iface, args.gps, args.baud, args.band)
    elif args.cmd == "simulate":
        from . import simulate
        extra = {k: v for k, v in (("alt", args.alt), ("lane", args.lane)) if v is not None}
        simulate.run(args.db, args.ambiente, routers=args.routers, seed=args.seed,
                     esp32_log=args.esp32_log, **extra)
    else:
        run_estimate(args)


def _load(args):
    """Abre o banco e devolve (aparelhos, trajetória com tempo, resumo)."""
    from . import db, estimate

    if not Path(args.db).exists():
        raise SystemExit(f"Arquivo não encontrado: {args.db}")
    con = db.connect(args.db)
    routers, _, _ = estimate.estimate(con)
    track = estimate.load_track(con)
    samples = con.execute("SELECT count(*) FROM samples").fetchone()[0]
    con.close()
    if not routers:
        raise SystemExit("Nenhuma amostra no banco.")
    return routers, track, estimate.flight_summary(track, samples, routers)


def run_report(args):
    from . import report

    routers, track, summary = _load(args)
    out = args.out or f"{Path(args.db).with_suffix('')}-relatorio.pdf"
    cache = Path.home() / ".cache" / "wifinder-tiles"
    pages = report.write(out, routers, track, summary["amostras"], source=Path(args.db).name,
                         basemap=not args.sem_fundo, cache=cache)
    print(f"Relatório: {out} ({pages} páginas, {summary['aparelhos']} aparelhos, {summary['redes']} redes)")


def run_estimate(args):
    from . import map as map_

    routers, track, summary = _load(args)
    base = Path(args.db).with_suffix("")
    csv_path, map_path = f"{base}-roteadores.csv", f"{base}-mapa.html"
    cols = ["ssid", "bssid", "redes", "canal", "lat", "lon", "raio_m", "confianca", "amostras", "pontos", "rssi_max"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in routers:
            w.writerow([r["ssid"], r["bssid"], " | ".join(f"{n['ssid'] or '(oculta)'} {n['bssid']}" for n in r["nets"]),
                        r["channel"], f"{r['lat']:.6f}", f"{r['lon']:.6f}", round(r["radius"]), r["status"],
                        r["samples"], r["spots"], f"{r['rssi_max']:.0f}"])
    map_.write(map_path, routers, track, title=base.name, summary=summary)

    print(f"{'NOME':<26} {'BSSID':<18} {'redes':>5} {'sinal':>6} {'raio':>7}  confiança")
    for r in routers:
        err = f"  (erro real {r['error']:.1f} m)" if r["error"] is not None else ""
        print(f"{(r['ssid'] or '(oculta)')[:26]:<26} {r['bssid']:<18} {len(r['nets']):>5} {r['rssi_max']:>6.0f} "
              f"{'±%.0f m' % r['radius']:>7}  {r['status']}{err}")
    errors = [r["error"] for r in routers if r["error"] is not None]
    if errors:
        print(f"\nErro mediano: {statistics.median(errors):.1f} m | máximo: {max(errors):.1f} m")
    print(f"\n{summary['aparelhos']} aparelhos ({summary['redes']} redes).\nCSV:  {csv_path}\nMapa: {map_path}")


if __name__ == "__main__":
    main()
