"""Suporte fechado do WiFinder para o DJI Mavic 4 Pro (paramétrico, 2 peças).

  base:  o aro do suporte de AirTag de exemplo (o encaixe no drone fica
         idêntico: o aro abraça o corpo do drone, em pé, como um anel) com
         uma caixa deitada direto em cima do drone (1 mm de folga), com a
         barra de cima do aro embutida na parede da frente da caixa;
  tampa: encaixa por cima com saia de 6 mm (a chuva escorre por fora), tem
         janela sobre a tela OLED e é presa com 4 abraçadeiras.

Dentro da caixa, lado a lado: a placa ESP32 em pé nos próprios pinos, com a
tela para cima e o USB saindo pela parede de trás; e a placa do GPS com a
antena cerâmica colada em cima dela.

Para gerar de novo depois de mudar uma medida:
  ~/Downloads/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage freecadcmd suporte.py

Eixos (como montado no drone): x = largura do drone, y = para trás, z = para
cima. O aro fica no plano x-z, com a face da frente em y = 0 e a barra de cima
terminando em z = 0. Todas as medidas em milímetros.
"""

import os

import FreeCAD
import Mesh
import Part
from FreeCAD import Vector as V

AQUI = os.path.dirname(os.path.abspath(__file__))
EXEMPLO = os.path.expanduser("~/Downloads/mavic-4-pro-air-tag-mount_1-color.stl")

# ------------------------------------------------------------- medidas
# CONFIRA ESTAS antes de imprimir (ver LEIA-ME.md).
ESP_COMP = 70.0      # placa ESP32: comprimento (medido pelo usuário, aproximado)
ESP_LARG = 30.0      # placa ESP32: largura (medido pelo usuário, aproximado)
ESP_PINOS = 8.5      # da ponta dos pinos até a face de baixo da placa
ESP_ESP = 1.6        # espessura da placa
USB_ACIMA = 1.3      # centro do conector USB acima da face de cima da placa
GPS_LARG = 30.0      # placa do GPS: largura (medida pelo usuário: placa 40 x 30, antena 30 x 30, aproximado)
ALTURA_INT = 17.0    # altura livre dentro da caixa (pinos + placa + tela; GPS + antena = ~14)
JAN_COMP, JAN_LARG = 28.0, 15.0   # janela da tela na tampa
JAN_DESLOC = 0.0     # desloca a janela ao longo da placa (+ = para trás)

FOLGA = 1.0          # folga de cada lado da placa (larga: a medida da placa é aproximada)
FOLGA_COMP = 2.0     # folga na ponta da frente da placa
PAREDE = 2.4         # paredes, fundo e tampa
SAIA, SAIA_ESP, SAIA_FOLGA = 6.0, 1.6, 0.3
USB_LARG, USB_ALT = 13.0, 8.0     # furo do plugue USB na parede de trás
FITA_C, FITA_L = 4.0, 2.0         # rasgo de abraçadeira nas orelhas

# Aro de exemplo: 68 de largura, 58 de altura, 5 de espessura, simétrico em x.
# A barra de cima tem 11 mm de altura: o corpo do drone encosta por baixo dela.
QX, QY, QZ = 68.0, 57.93, 5.0
BARRA = 11.0
FOLGA_DRONE = 1.0    # vão entre o fundo da caixa e o corpo do drone

# Caixa: centrada no aro em x, com a largura que as duas placas pedem, do plano
# da frente do aro (y = 0) para trás. A parede da frente tem a espessura do aro
# (5 mm) e engole a barra de cima.
LARG_INT = FOLGA + ESP_LARG + FOLGA + 1.2 + GPS_LARG + 1.5
BX0 = QX / 2 - LARG_INT / 2 - PAREDE
BX1 = QX / 2 + LARG_INT / 2 + PAREDE
BY0 = 0.0
BY1 = BY0 + QZ + FOLGA_COMP + ESP_COMP + 1.2 + PAREDE
Z_FUNDO = -BARRA + FOLGA_DRONE      # face de baixo do fundo
Z_PISO = Z_FUNDO + PAREDE           # face de cima do fundo
Z_BORDA = Z_PISO + ALTURA_INT       # topo das paredes
Z_TAMPA = Z_BORDA + PAREDE          # topo da tampa
IX0, IX1 = BX0 + PAREDE, BX1 - PAREDE
IY0, IY1 = BY0 + QZ, BY1 - PAREDE
ESP_X0 = IX0 + FOLGA                # a placa ESP32 fica encostada na parede esquerda
ESP_CX = ESP_X0 + ESP_LARG / 2
ESP_Y1 = IY1 - 1.2                  # ponta do USB, perto da parede de trás
DIV_X = ESP_X0 + ESP_LARG + FOLGA   # divisória entre ESP32 e GPS
ORELHAS_Y = (BY0 + 16.0, BY1 - 18.4)
ORELHA = 7.0                        # quanto a orelha sai da parede


def caixa(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cunha(x_parede, x_ponta, y_topo, z0, z1):
    """Reforço a 45 graus do lado da mesa de impressão (y menor) de uma orelha."""
    d = abs(x_ponta - x_parede)
    tri = Part.makePolygon([V(x_parede, y_topo, z0), V(x_ponta, y_topo, z0),
                            V(x_parede, y_topo - d, z0), V(x_parede, y_topo, z0)])
    return Part.Face(tri).extrude(V(0, 0, z1 - z0))


def juntar(pecas):
    corpo = pecas[0]
    for p in pecas[1:]:
        corpo = corpo.fuse(p)
    return corpo


def quadro():
    """Quadro em U do exemplo, sem a caixinha do AirTag: o contorno dele, cortado
    logo acima da base, extrudado na espessura original."""
    malha = Mesh.Mesh(EXEMPLO)
    bb = malha.BoundBox
    malha.translate(-bb.XMin, -bb.YMin, -bb.ZMin)
    lacos = malha.crossSections([(V(0, 0, 0.5), V(0, 0, 1))], 0.01)[0]
    faces = []
    for laco in lacos:
        pts = [V(p.x, p.y, 0) for p in laco]
        limpos = [pts[0]]
        for p in pts[1:]:
            if p.distanceToPoint(limpos[-1]) > 0.01:
                limpos.append(p)
        if limpos[0].distanceToPoint(limpos[-1]) > 0.01:
            limpos.append(limpos[0])
        else:
            limpos[-1] = limpos[0]
        if len(limpos) >= 4:
            faces.append(Part.Face(Part.makePolygon(limpos)))
    faces.sort(key=lambda f: -f.Area)
    contorno = faces[0]
    for furo in faces[1:]:
        contorno = contorno.cut(furo)
    aro = contorno.extrude(V(0, 0, QZ)).removeSplitter()
    # Deitado na mesa (x, y, z) -> em pé no drone (x, z, -y): a barra fica em cima.
    aro.rotate(V(0, 0, 0), V(1, 0, 0), -90)
    return aro


def orelhas(z0, z1, x_dentro_esq, x_dentro_dir):
    """Quatro orelhas (duas por lado) com rasgo vertical para abraçadeira."""
    solidos, rasgos = [], []
    for y in ORELHAS_Y:
        for x_in, x_out in ((x_dentro_esq, BX0 - ORELHA), (x_dentro_dir, BX1 + ORELHA)):
            solidos.append(caixa(min(x_in, x_out), max(x_in, x_out), y - 4, y + 4, z0, z1))
            sinal = -1 if x_out < x_in else 1
            xr = (BX0 if sinal < 0 else BX1) + sinal * 3.2
            rasgos.append(caixa(min(xr, xr + sinal * FITA_L), max(xr, xr + sinal * FITA_L),
                                y - FITA_C / 2, y + FITA_C / 2, z0 - 20, z1 + 20))
    return solidos, rasgos


def base():
    pecas = [quadro()]
    # Caixa.
    fora = caixa(BX0, BX1, BY0, BY1, Z_FUNDO, Z_BORDA)
    pecas.append(fora.cut(caixa(IX0, IX1, IY0, IY1, Z_PISO, Z_BORDA + 1)))
    # Divisória entre a placa ESP32 e o GPS, em dois trechos (os fios passam no meio e nas pontas).
    for y0, y1 in ((IY0 + 6, IY0 + 16), (IY1 - 16, IY1 - 6)):
        pecas.append(caixa(DIV_X, DIV_X + 1.2, y0, y1, Z_PISO, Z_PISO + 12))
    # Orelhas das abraçadeiras, logo abaixo da saia da tampa.
    z_or = Z_BORDA - SAIA - 2.0
    blocos, rasgos = orelhas(z_or - 4, z_or, BX0, BX1)
    pecas += blocos
    for y in ORELHAS_Y:
        pecas.append(cunha(BX0, BX0 - ORELHA, y - 4, z_or - 4, z_or))
        pecas.append(cunha(BX1, BX1 + ORELHA, y - 4, z_or - 4, z_or))
    corpo = juntar(pecas)

    # Furo do plugue USB na parede de trás, na altura do conector da placa.
    z_usb = Z_PISO + ESP_PINOS + ESP_ESP + USB_ACIMA
    corpo = corpo.cut(caixa(ESP_CX - USB_LARG / 2, ESP_CX + USB_LARG / 2, IY1 - 0.01, BY1 + 1,
                            z_usb - USB_ALT / 2, z_usb + USB_ALT / 2))
    # Dois drenos pequenos no fundo, nos cantos de trás (condensação).
    for x in (IX0 + 2.5, IX1 - 2.5):
        corpo = corpo.cut(Part.makeCylinder(1.1, PAREDE + 2, V(x, IY1 - 2.5, Z_FUNDO - 1)))
    for r in rasgos:
        corpo = corpo.cut(r)
    return corpo.removeSplitter(), z_usb


def tampa(z_usb):
    f = SAIA_FOLGA
    e = f + SAIA_ESP
    placa = caixa(BX0 - e, BX1 + e, BY0 - e, BY1 + e, Z_BORDA, Z_TAMPA)
    saia = caixa(BX0 - e, BX1 + e, BY0 - e, BY1 + e, Z_BORDA - SAIA, Z_BORDA)
    saia = saia.cut(caixa(BX0 - f, BX1 + f, BY0 - f, BY1 + f, Z_BORDA - SAIA - 1, Z_BORDA + 0.01))
    blocos, rasgos = orelhas(Z_BORDA - SAIA, Z_TAMPA, BX0 - e, BX1 + e)
    corpo = juntar([placa, saia] + blocos)
    # Janela da tela, com rebaixo por dentro para colar o acetato.
    jy = ESP_Y1 - ESP_COMP / 2 + JAN_DESLOC
    corpo = corpo.cut(caixa(ESP_CX - JAN_LARG / 2, ESP_CX + JAN_LARG / 2, jy - JAN_COMP / 2, jy + JAN_COMP / 2,
                            Z_BORDA - 1, Z_TAMPA + 1))
    corpo = corpo.cut(caixa(ESP_CX - JAN_LARG / 2 - 3, ESP_CX + JAN_LARG / 2 + 3,
                            jy - JAN_COMP / 2 - 3, jy + JAN_COMP / 2 + 3, Z_BORDA - 1, Z_BORDA + 0.8))
    # Recorte da saia sobre o plugue USB.
    if z_usb + USB_ALT / 2 > Z_BORDA - SAIA:
        corpo = corpo.cut(caixa(ESP_CX - USB_LARG / 2 - 1, ESP_CX + USB_LARG / 2 + 1, BY1 + f - 0.01, BY1 + e + 1,
                                Z_BORDA - SAIA - 1, min(z_usb + USB_ALT / 2 + 0.5, Z_BORDA)))
    for r in rasgos:
        corpo = corpo.cut(r)
    return corpo.removeSplitter()


def conferir(nome, forma):
    assert forma.isValid(), f"{nome}: geometria inválida"
    assert len(forma.Solids) == 1, f"{nome}: saiu em {len(forma.Solids)} pedaços"
    bb = forma.BoundBox
    vol = forma.Volume / 1000.0
    print(f"{nome}: {bb.XLength:.1f} x {bb.YLength:.1f} x {bb.ZLength:.1f} mm, {vol:.1f} cm3, "
          f"{vol * 1.27 * 0.6:.0f} a {vol * 1.27:.0f} g em PETG")
    return vol


if __name__ in ("__main__", "suporte"):
    b, z_usb = base()
    t = tampa(z_usb)
    conferir("Base", b)
    conferir("Tampa", t)
    livre = b.common(t).Volume
    assert livre < 0.01, f"base e tampa se atravessam ({livre:.2f} mm3)"
    print(f"Montado: a caixa fica {FOLGA_DRONE:.1f} mm acima do drone, sobe {Z_TAMPA + BARRA:.1f} mm acima dele "
          f"e vai {BY1:.1f} mm para trás")
    print(f"Por dentro: {IX1 - IX0:.1f} x {IY1 - IY0:.1f} x {ALTURA_INT:.1f} mm; "
          f"vão do GPS com {IX1 - DIV_X - 1.2:.1f} mm de largura (placa de {GPS_LARG:.1f})")
    # Como montado no drone, para pré-visualizar.
    Mesh.Mesh(b.fuse(t).tessellate(0.05)).write(os.path.join(AQUI, "montado-so-para-ver.stl"))
    # Base para imprimir: aro deitado na mesa (como o suporte de AirTag), caixa em pé.
    deitada = b.copy()
    deitada.rotate(V(0, 0, 0), V(1, 0, 0), 90)
    deitada.translate(V(0, -deitada.BoundBox.YMin, -deitada.BoundBox.ZMin))
    Mesh.Mesh(deitada.tessellate(0.03)).write(os.path.join(AQUI, "wifinder-mavic4pro-base.stl"))
    # A tampa vai para a mesa de cabeça para baixo (face de cima na mesa), já no STL.
    virada = t.copy()
    virada.rotate(V(0, 0, 0), V(1, 0, 0), 180)
    virada.translate(V(0, 0, -virada.BoundBox.ZMin))
    Mesh.Mesh(virada.tessellate(0.03)).write(os.path.join(AQUI, "wifinder-mavic4pro-tampa.stl"))
    Part.makeCompound([b, t]).exportStep(os.path.join(AQUI, "wifinder-mavic4pro.step"))
    doc = FreeCAD.newDocument("SuporteWiFinder")
    doc.addObject("Part::Feature", "Base").Shape = b
    doc.addObject("Part::Feature", "Tampa").Shape = t
    doc.recompute()
    doc.saveAs(os.path.join(AQUI, "wifinder-mavic4pro.FCStd"))
    print("Arquivos gravados em", AQUI)
