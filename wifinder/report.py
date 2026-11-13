"""Relatório em PDF: resumo do voo, mapa de satélite, panorama (canais e sinal)
e tabela dos aparelhos.

Usa só matplotlib e Pillow. O fundo de satélite (Esri World Imagery) é baixado
tile a tile; sem internet o mapa sai em metros locais, sem fundo.
"""

import io
import math
import time
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

from .estimate import flight_summary  # noqa: E402
from .geo import to_local  # noqa: E402

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE = 256
A4 = (8.27, 11.69)

INK, MUTED, RULE, SOFT, ACCENT = "#14181f", "#5f6877", "#e3e6eb", "#f5f6f8", "#1c5cab"
BAR = "#2a78d6"
TRACK = "#29b6f6"
# Sinal mais forte ouvido: do fraco (claro) ao forte (escuro). Igual ao mapa interativo.
RAMP = [(-95, "#ffe9a8"), (-85, "#ffb347"), (-75, "#f4622a"), (-65, "#b3122a")]
CMAP = LinearSegmentedColormap.from_list("sinal", [c for _, c in RAMP])
SIZE = {"boa": 8.5, "média": 6.5, "fraca": 4.5}


def sig_color(rssi):
    return CMAP(min(max((rssi - RAMP[0][0]) / (RAMP[-1][0] - RAMP[0][0]), 0.0), 1.0))


def _txt(s):
    """Nome de rede é texto arbitrário: '$' ligaria o modo matemático do matplotlib."""
    return str(s).replace("$", r"\$")


def _name(r):
    return r["ssid"] or "(rede oculta)"


# ------------------------------------------------------------ fundo (tiles)

def _merc(lat, lon, z):
    """Pixel global (x, y) no esquema Web Mercator, nível z."""
    n = TILE * 2 ** z
    lat = max(min(lat, 85.0), -85.0)
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _get_tile(z, x, y, cache, timeout):
    path = cache / f"{z}-{x}-{y}.jpg" if cache else None
    if path and path.exists():
        return path.read_bytes()
    req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": "WiFinder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except Exception:
        return None
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return data


def fetch_basemap(lat_min, lat_max, lon_min, lon_max, max_px=2048, cache=None, timeout=10):
    """Mosaico de satélite cobrindo a área. Retorna (imagem, (x0, y0), z) ou None."""
    # Há imagem até o nível 19 nas cidades e só até o 17 em área remota, onde
    # os níveis acima devolvem um aviso cinza (um arquivo bem pequeno).
    top = 17
    for z in (19, 18):
        cx, cy = _merc((lat_min + lat_max) / 2, (lon_min + lon_max) / 2, z)
        data = _get_tile(z, int(cx // TILE), int(cy // TILE), cache, timeout)
        if data and len(data) > 4000:
            top = z
            break
    for z in range(top, 9, -1):
        x0, y0 = _merc(lat_max, lon_min, z)
        x1, y1 = _merc(lat_min, lon_max, z)
        if x1 - x0 <= max_px and y1 - y0 <= max_px:
            break
    tx0, ty0, tx1, ty1 = int(x0 // TILE), int(y0 // TILE), int(x1 // TILE), int(y1 // TILE)
    img = Image.new("RGB", ((tx1 - tx0 + 1) * TILE, (ty1 - ty0 + 1) * TILE), (225, 225, 225))
    got = 0
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            data = _get_tile(z, tx, ty, cache, timeout)
            if data:
                img.paste(Image.open(io.BytesIO(data)).convert("RGB"), ((tx - tx0) * TILE, (ty - ty0) * TILE))
                got += 1
    return (img, (tx0 * TILE, ty0 * TILE), z) if got else None


# ------------------------------------------------------------------- mapa

def _bbox(routers, track, aspect=1.0):
    """Área do mapa: percurso + aparelhos, com folga, na proporção largura/altura pedida."""
    lats = [p[0] for p in track] + [r["lat"] for r in routers]
    lons = [p[1] for p in track] + [r["lon"] for r in routers]
    lat0, lon0 = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    k = 111320.0 * math.cos(math.radians(lat0))
    w = (max(lons) - min(lons)) * k
    h = (max(lats) - min(lats)) * 111320.0
    pad = max(35.0, 0.12 * max(w, h))
    w, h = w + 2 * pad, h + 2 * pad
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect
    return lat0 - h / 2 / 111320.0, lat0 + h / 2 / 111320.0, lon0 - w / 2 / k, lon0 + w / 2 / k


def draw_map(ax, routers, track, basemap=True, cache=None):
    """Desenha o mapa no eixo. Retorna True se usou fundo de satélite."""
    fig = ax.figure
    box = ax.get_position()
    aspect = (box.width * fig.get_figwidth()) / (box.height * fig.get_figheight())
    lat_min, lat_max, lon_min, lon_max = _bbox(routers, track, aspect)
    bm = fetch_basemap(lat_min, lat_max, lon_min, lon_max, cache=cache) if basemap else None
    if bm:
        img, (ox, oy), z = bm
        proj = lambda lat, lon: _merc(lat, lon, z)  # noqa: E731
        m_per_px = 156543.03 * math.cos(math.radians((lat_min + lat_max) / 2)) / 2 ** z
        ax.imshow(img, extent=[ox, ox + img.width, oy + img.height, oy], interpolation="bilinear")
        x0, y0 = proj(lat_max, lon_min)
        x1, y1 = proj(lat_min, lon_max)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
        fg, halo = "white", "#0b0f15"
    else:
        lat0, lon0 = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
        proj = lambda lat, lon: to_local(lat, lon, lat0, lon0)  # noqa: E731
        m_per_px = 1.0
        x0, y0 = proj(lat_min, lon_min)
        x1, y1 = proj(lat_max, lon_max)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_facecolor(SOFT)
        ax.grid(True, color=RULE, lw=0.6)
        fg, halo = INK, "white"
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
    for s in ax.spines.values():
        s.set_color(RULE)

    # Um traço por trecho: com vários voos juntos não liga o fim de um ao começo do outro.
    segs = []
    for i, p in enumerate(track):
        if not segs or (len(p) > 3 and not 0 <= p[3] - track[i - 1][3] <= 30):
            segs.append([])
        segs[-1].append(proj(p[0], p[1]))
    for seg in segs:
        tx, ty = zip(*seg)
        ax.plot(tx, ty, color="#06324a", lw=3.2, alpha=0.6, solid_capstyle="round")
        ax.plot(tx, ty, color=TRACK, lw=1.5, solid_capstyle="round")

    # Os mais fracos primeiro, para os fortes ficarem por cima.
    order = sorted(range(len(routers)), key=lambda i: routers[i]["rssi_max"])
    for i in order:
        r = routers[i]
        px, py = proj(r["lat"], r["lon"])
        if r.get("truth"):
            qx, qy = proj(*r["truth"])
            ax.plot([px, qx], [py, qy], color="#1baf7a", lw=0.8, ls="--")
            ax.plot(qx, qy, "o", color="#1baf7a", ms=4, mec="white", mew=0.6)
        if r["status"] == "boa":
            ax.add_patch(Circle((px, py), r["radius"] / m_per_px, fill=False, ec=fg, lw=0.7, ls=(0, (4, 3)), alpha=0.75))
        ax.plot(px, py, "o", color=sig_color(r["rssi_max"]), ms=SIZE[r["status"]], mec="white", mew=1.0,
                alpha=0.85 if r["status"] == "fraca" else 1.0, zorder=3)

    # Nomes: do sinal mais forte ao mais fraco, só onde couber sem encavalar.
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    limits = ax.get_window_extent(rend)
    placed = []
    for i, r in enumerate(routers):
        px, py = proj(r["lat"], r["lon"])
        for dx, dy, ha, va in ((7, 0, "left", "center"), (-7, 0, "right", "center"), (6, 7, "left", "bottom"),
                               (6, -7, "left", "top"), (-6, 7, "right", "bottom"), (-6, -7, "right", "top")):
            t = ax.annotate(_txt(f"{i + 1} {_name(r)}"[:26]), (px, py), xytext=(dx, dy), textcoords="offset points",
                            ha=ha, va=va, fontsize=6.3, color=fg, fontweight="bold", zorder=5,
                            path_effects=[pe.withStroke(linewidth=2, foreground=halo)])
            bb = t.get_window_extent(rend).expanded(1.04, 1.25)
            inside = (bb.x0 >= limits.x0 and bb.x1 <= limits.x1 and bb.y0 >= limits.y0 and bb.y1 <= limits.y1)
            if inside and not any(bb.overlaps(o) for o in placed):
                placed.append(bb)
                break
            t.remove()

    # Escala.
    span_m = abs(ax.get_xlim()[1] - ax.get_xlim()[0]) * m_per_px
    bar = 10 ** math.floor(math.log10(span_m / 4))
    bar = bar * (5 if span_m / 4 >= 5 * bar else 2 if span_m / 4 >= 2 * bar else 1)
    xl, yl = ax.get_xlim(), ax.get_ylim()
    bx = xl[0] + 0.04 * (xl[1] - xl[0])
    by = yl[0] + 0.045 * (yl[1] - yl[0])
    ax.plot([bx, bx + bar / m_per_px], [by, by], color=fg, lw=3, solid_capstyle="butt",
            path_effects=[pe.withStroke(linewidth=5, foreground=halo)], zorder=6)
    ax.text(bx, by + 0.014 * (yl[1] - yl[0]), f"{bar:g} m", color=fg, fontsize=7.5, fontweight="bold",
            path_effects=[pe.withStroke(linewidth=2, foreground=halo)], zorder=6)
    return bool(bm)


# ------------------------------------------------------------- formatação

def _fmt_time(t):
    return time.strftime("%d/%m/%Y %H:%M UTC", time.gmtime(t)) + time.strftime(" (%H:%M no computador)", time.localtime(t))


def _fmt_dur(sec):
    return f"{round(sec / 60)} min" if sec < 3600 else f"{int(sec // 3600)} h {int(sec % 3600 // 60):02d} min"


def _fmt_dist(m):
    return f"{m / 1000:.2f} km" if m >= 1000 else f"{m:.0f} m"


def _page(pdf, source, n):
    """Figura A4 com faixa de marca no topo e rodapé."""
    fig = plt.figure(figsize=A4)
    fig.add_artist(Rectangle((0, 0.985), 1, 0.015, transform=fig.transFigure, fc=ACCENT, ec="none"))
    fig.text(0.07, 0.022, f"WiFinder  ·  {_txt(source)}", fontsize=7, color=MUTED)
    fig.text(0.93, 0.022, f"página {n}", fontsize=7, color=MUTED, ha="right")
    return fig


def _legend(fig, x, y, has_truth):
    """Legenda do mapa: cor = sinal, tamanho = confiança."""
    fig.text(x, y, "Sinal mais forte ouvido", fontsize=7.5, fontweight="bold", color=INK)
    ax = fig.add_axes([x, y - 0.019, 0.20, 0.009])
    ax.imshow(np.linspace(0, 1, 256)[None, :], aspect="auto", cmap=CMAP)
    ax.axis("off")
    fig.text(x, y - 0.031, "−95 dBm (fraco)", fontsize=6.5, color=MUTED)
    fig.text(x + 0.20, y - 0.031, "−65 dBm (forte)", fontsize=6.5, color=MUTED, ha="right")

    x2 = x + 0.27
    fig.text(x2, y, "Confiança da posição", fontsize=7.5, fontweight="bold", color=INK)
    lg = fig.add_axes([x2, y - 0.034, 0.34, 0.026])
    lg.set_xlim(0, 34)
    lg.set_ylim(0, 2.6)
    lg.axis("off")
    for k, (st, lab) in enumerate((("boa", "boa (com raio provável)"), ("média", "média"), ("fraca", "fraca"))):
        cx = (0.6, 17.5, 25.5)[k]
        lg.plot(cx, 1.3, "o", color=sig_color(-75), ms=SIZE[st], mec="white", mew=1.0,
                path_effects=[pe.withStroke(linewidth=2.2, foreground="#9aa3b0")])
        lg.text(cx + 1.3, 1.3, lab, fontsize=7, color=INK, va="center")

    x3 = x + 0.70
    lg2 = fig.add_axes([x3, y - 0.034, 0.16, 0.045])
    lg2.set_xlim(0, 16)
    lg2.set_ylim(0, 4.5)
    lg2.axis("off")
    lg2.plot([0.2, 2.6], [3.6, 3.6], color=TRACK, lw=2)
    lg2.text(3.6, 3.6, "percurso", fontsize=7, color=INK, va="center")
    if has_truth:
        lg2.plot(1.4, 1.5, "o", color="#1baf7a", ms=5, mec="white", mew=0.8)
        lg2.text(3.6, 1.5, "posição verdadeira", fontsize=7, color=INK, va="center")


def _bars(ax, xs, ys, title, xlabel, ticks=None):
    """Barras de uma série só: grade discreta, sem moldura."""
    ax.bar(xs, ys, width=0.72 * (xs[1] - xs[0] if len(xs) > 1 else 1), color=BAR, linewidth=0)
    ax.set_title(title, fontsize=9.5, fontweight="bold", color=INK, loc="left", pad=8)
    ax.set_xlabel(xlabel, fontsize=7.5, color=MUTED)
    ax.set_xticks(ticks if ticks is not None else xs)
    ax.tick_params(labelsize=7, colors=MUTED, length=0)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5, integer=True))
    ax.grid(axis="y", color=RULE, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c5cad3")


# -------------------------------------------------------------------- PDF

# Colunas da tabela: (título, posição x, alinhamento).
COLS = [("#", 0.092, "right"), ("Nome", 0.115, "left"), ("Redes", 0.375, "right"), ("Endereço (BSSID)", 0.39, "left"),
        ("Canal", 0.565, "right"), ("Latitude", 0.655, "right"), ("Longitude", 0.752, "right"),
        ("± m", 0.795, "right"), ("Sinal", 0.838, "right"), ("Confiança", 0.855, "left")]
PER_PAGE = 44


def write(path, routers, track, samples=0, title="Relatório do voo", source="",
          basemap=True, cache=None):
    """Gera o PDF. track: [(lat, lon, alt[, t]), ...]. Retorna o número de páginas."""
    summary = flight_summary(track, samples, routers)
    has_truth = any(r.get("error") is not None for r in routers)
    n_nets = sum(len(r["nets"]) for r in routers)
    pages = 0
    with PdfPages(path) as pdf:
        # ------------------------------------------------ página 1: resumo + mapa
        pages += 1
        fig = _page(pdf, source, pages)
        fig.text(0.07, 0.955, "WIFINDER", fontsize=8, fontweight="bold", color=ACCENT)
        fig.text(0.07, 0.928, _txt(title), fontsize=20, fontweight="bold", color=INK)
        sub = [_txt(source)] if source else []
        if "inicio" in summary:
            sub.append("início " + _fmt_time(summary["inicio"]))
        sub.append("gerado em " + time.strftime("%d/%m/%Y %H:%M"))
        fig.text(0.07, 0.910, "   ·   ".join(sub), fontsize=8, color=MUTED)

        best = max((r["rssi_max"] for r in routers), default=None)
        tiles = [(str(len(routers)), "aparelhos"), (str(n_nets), "redes WiFi")]
        if "duracao" in summary:
            tiles.append((_fmt_dur(summary["duracao"]), "duração"))
        if "distancia" in summary:
            tiles.append((_fmt_dist(summary["distancia"]), "percurso"))
        tiles.append((str(summary["amostras"]), "amostras"))
        if best is not None:
            tiles.append((f"{best:.0f} dBm", "sinal mais forte"))
        gap = 0.012
        w = (0.86 - gap * (len(tiles) - 1)) / len(tiles)
        for k, (v, lab) in enumerate(tiles):
            x = 0.07 + k * (w + gap)
            fig.add_artist(FancyBboxPatch((x, 0.835), w, 0.052, boxstyle="round,pad=0,rounding_size=0.006",
                                          transform=fig.transFigure, fc=SOFT, ec="none"))
            fig.text(x + 0.012, 0.862, v, fontsize=11.5, fontweight="bold", color=INK)
            fig.text(x + 0.012, 0.844, lab, fontsize=7.5, color=MUTED)

        ax = fig.add_axes([0.07, 0.125, 0.86, 0.69])
        used_bm = draw_map(ax, routers, track, basemap, cache)
        _legend(fig, 0.07, 0.100, has_truth)
        fig.text(0.07, 0.045, "Os nomes aparecem onde cabem, do sinal mais forte ao mais fraco; o número é o da tabela. "
                 + ("Fundo: Esri World Imagery." if used_bm else "Sem fundo de satélite."), fontsize=6.8, color=MUTED)
        pdf.savefig(fig)
        plt.close(fig)

        # ---------------------------------------------------- página 2: panorama
        pages += 1
        fig = _page(pdf, source, pages)
        fig.text(0.07, 0.94, "Panorama", fontsize=16, fontweight="bold", color=INK)
        fig.text(0.07, 0.922, f"{len(routers)} aparelhos anunciando {n_nets} redes.", fontsize=8.5, color=MUTED)

        chans = [r["channel"] for r in routers]
        lo, hi = (1, 13) if all(1 <= c <= 13 for c in chans) else (min(chans), max(chans))
        xs = np.arange(lo, hi + 1)
        _bars(fig.add_axes([0.09, 0.70, 0.38, 0.17]), xs, [chans.count(c) for c in xs],
              "Aparelhos por canal", "canal WiFi")
        edges = np.arange(-100, -39, 5)
        hist, _ = np.histogram([r["rssi_max"] for r in routers], bins=edges)
        keep = slice(0, max(np.flatnonzero(hist).max() + 2, 4)) if hist.any() else slice(0, 4)
        _bars(fig.add_axes([0.55, 0.70, 0.38, 0.17]), (edges[:-1] + 2.5)[keep], hist[keep],
              "Aparelhos por sinal mais forte", "dBm (mais à direita = mais forte)", ticks=edges[:-1][keep][::2])

        fig.text(0.07, 0.635, "Os mais fortes", fontsize=11, fontweight="bold", color=INK)
        y = 0.612
        for label, xx, ha in (("#", 0.092, "right"), ("Nome", 0.115, "left"), ("Sinal", 0.47, "right"),
                              ("Canal", 0.54, "right"), ("Posição (lat, lon)", 0.575, "left"), ("Confiança", 0.80, "left")):
            fig.text(xx, y, label, fontsize=7.5, fontweight="bold", color=MUTED, ha=ha)
        fig.add_artist(Rectangle((0.07, y - 0.007), 0.86, 0.0008, transform=fig.transFigure, fc="#c5cad3", ec="none"))
        for i, r in enumerate(routers[:10]):
            yy = y - 0.024 - i * 0.022
            fig.text(0.092, yy, str(i + 1), fontsize=8, color=MUTED, ha="right")
            fig.text(0.115, yy, _txt(_name(r)[:38]), fontsize=8.5, fontweight="bold", color=INK)
            fig.add_artist(Rectangle((0.385, yy - 0.001), 0.045 * min(max((r["rssi_max"] + 100) / 40, 0.05), 1.0), 0.009,
                                     transform=fig.transFigure, fc=sig_color(r["rssi_max"]), ec="none"))
            fig.text(0.47, yy, f"{r['rssi_max']:.0f}", fontsize=8.5, color=INK, ha="right")
            fig.text(0.54, yy, str(r["channel"]), fontsize=8.5, color=INK, ha="right")
            fig.text(0.575, yy, f"{r['lat']:.6f}, {r['lon']:.6f}", fontsize=8, color=INK, family="monospace")
            fig.text(0.80, yy, f"{r['status']}  (±{r['radius']:.0f} m)", fontsize=8.5, color=INK)

        yb = y - 0.024 - 10 * 0.022 - 0.03
        fig.add_artist(FancyBboxPatch((0.07, yb - 0.175), 0.86, 0.175, boxstyle="round,pad=0,rounding_size=0.006",
                                      transform=fig.transFigure, fc=SOFT, ec="none"))
        fig.text(0.09, yb - 0.028, "Como ler este relatório", fontsize=9.5, fontweight="bold", color=INK)
        n_by = {s: sum(r["status"] == s for r in routers) for s in ("boa", "média", "fraca")}
        notes = [
            "Aparelho: um roteador. As redes que ele anuncia (principal, visitantes, operadora) foram juntadas num item só.",
            "Posição: média dos pontos do percurso onde o sinal chegou mais forte. É onde o aparelho foi ouvido melhor,",
            "    não um endereço exato: ele costuma estar dentro do raio provável (± m) em volta do ponto marcado.",
            f"Confiança boa ({n_by['boa']}): ouvido forte e em muitos pontos.  Média ({n_by['média']}): ouvido em alguns pontos.",
            f"    Fraca ({n_by['fraca']}): ouvido em 1 ou 2 pontos; a marca mostra só onde o percurso passou perto.",
            "Percurso em linha reta não distingue o lado: para afinar a posição, passe dos dois lados ou em zigue-zague.",
        ]
        for k, line in enumerate(notes):
            fig.text(0.09, yb - 0.052 - k * 0.019, line, fontsize=7.8, color=INK)
        pdf.savefig(fig)
        plt.close(fig)

        # ------------------------------------------------- páginas seguintes: tabela
        for start in range(0, len(routers), PER_PAGE):
            pages += 1
            fig = _page(pdf, source, pages)
            fig.text(0.07, 0.94, "Aparelhos encontrados", fontsize=16, fontweight="bold", color=INK)
            fig.text(0.07, 0.922, "Do sinal mais forte ao mais fraco. Coordenadas em graus decimais (WGS84); "
                     "± m é o raio provável; sinal em dBm." + ("  Erro real: distância até a posição simulada." if has_truth else ""),
                     fontsize=7.5, color=MUTED)
            y0, dy = 0.895, 0.0192
            for label, xx, ha in COLS:
                fig.text(xx, y0, label, fontsize=7.2, fontweight="bold", color=MUTED, ha=ha)
            if has_truth:
                fig.text(0.93, y0, "Erro real", fontsize=7.2, fontweight="bold", color=MUTED, ha="right")
            fig.add_artist(Rectangle((0.07, y0 - 0.007), 0.86, 0.0008, transform=fig.transFigure, fc="#c5cad3", ec="none"))
            for j, r in enumerate(routers[start:start + PER_PAGE]):
                i = start + j
                yy = y0 - 0.022 - j * dy
                if j % 2:
                    fig.add_artist(Rectangle((0.07, yy - 0.0055), 0.86, dy, transform=fig.transFigure, fc=SOFT, ec="none"))
                fig.add_artist(Rectangle((0.07, yy - 0.0055), 0.006, dy, transform=fig.transFigure,
                                         fc=sig_color(r["rssi_max"]), ec="none"))
                cells = [str(i + 1), _txt(_name(r)[:34]), str(len(r["nets"])), r["bssid"], str(r["channel"]),
                         f"{r['lat']:.6f}", f"{r['lon']:.6f}", f"{r['radius']:.0f}", f"{r['rssi_max']:.0f}", r["status"]]
                for (label, xx, ha), v in zip(COLS, cells):
                    mono = label.startswith("Endereço")
                    fig.text(xx, yy, v, fontsize=6.6 if mono else 7.4, color=INK, ha=ha,
                             family="monospace" if mono else None,
                             fontweight="bold" if label == "Nome" else "normal")
                if has_truth and r.get("error") is not None:
                    fig.text(0.93, yy, f"{r['error']:.0f} m", fontsize=7.4, color=INK, ha="right")
            pdf.savefig(fig)
            plt.close(fig)
    return pages
