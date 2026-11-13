"""Fatia um STL com o CuraEngine do Cura 5.14 usando o perfil da Ender-3 V2.

O CuraEngine de linha de comando não calcula as fórmulas ("value") das
definições, então este script resolve todas elas antes (como o Cura faz) e
passa os valores prontos com -s.

uso: fatiar.py <montagem do AppImage> <modelo.stl> <saida.gcode> [chave=valor ...]

A montagem é a pasta /tmp/.mount_UltiMa* que existe enquanto o Cura está
aberto (ou a saída de `UltiMaker-Cura-...AppImage --appimage-mount`).

As duas peças do suporte foram fatiadas assim (PLA, 0,2 mm, 4 paredes, 25 %):
  comum:  center_object=true material_print_temperature=205
          material_bed_temperature=60 retraction_amount=5 retraction_speed=45
          wall_thickness=1.6 infill_sparse_density=25 support_enable=true
          support_structure=tree support_type=everywhere support_angle=50
  base:   + adhesion_type=brim brim_width=8
"""
import configparser
import json
import math
import os
import subprocess
import sys

RES = ""      # <montagem>/share/cura/resources, definido em main()


def carregar(nome, pasta):
    d = json.load(open(os.path.join(RES, pasta, nome + ".def.json")))
    cadeia = [d]
    while "inherits" in cadeia[-1]:
        pai = cadeia[-1]["inherits"]
        for p in ("definitions", "extruders"):
            arq = os.path.join(RES, p, pai + ".def.json")
            if os.path.exists(arq):
                cadeia.append(json.load(open(arq)))
                break
    return cadeia[::-1]      # da raiz para a folha


def achatar(settings, saida):
    for chave, s in settings.items():
        saida[chave] = {k: v for k, v in s.items() if k != "children"}
        achatar(s.get("children", {}), saida)


def definicoes(cadeia):
    props = {}
    for d in cadeia:
        achatar(d.get("settings", {}), props)
        for chave, o in d.get("overrides", {}).items():
            props.setdefault(chave, {}).update(o)
            # Uma folha que só dá default_value ainda perde para um "value" herdado
            # no Cura; aqui não há esse caso relevante além dos textos de gcode.
    return props


def perfil(caminho):
    c = configparser.ConfigParser(interpolation=None)
    c.optionxform = str
    c.read(caminho)
    return dict(c["values"]) if c.has_section("values") else {}


class Resolver(dict):
    """Namespace preguiçoso: cada nome de ajuste é calculado quando pedido."""

    def __init__(self, props, camadas):
        super().__init__()
        self.props = props
        self.camadas = camadas          # da mais prioritária para a menos
        self.em_curso = set()
        self.funcs = {
            "math": math, "extruderValue": lambda n, k: self[k],
            "extruderValues": lambda k: [self[k]],
            "resolveOrValue": lambda k: self[k],
            "defaultExtruderPosition": lambda: "0",
            "anyExtruderWithMaterial": lambda k: False,
            "anyExtruderNrWithOrDefault": lambda k: "0",
            "valueFromContainer": lambda i, k: self[k],
            "extruderValueFromContainer": lambda n, k, i: self[k],
        }

    def __missing__(self, chave):
        if chave in self.funcs:
            return self.funcs[chave]
        if chave not in self.props:
            raise KeyError(chave)
        if chave in self.em_curso:
            raise RecursionError("ciclo em " + chave)
        self.em_curso.add(chave)
        try:
            v = self.calcular(chave)
        finally:
            self.em_curso.discard(chave)
        self[chave] = v
        return v

    def converter(self, chave, texto):
        """Valor vindo de um perfil .inst.cfg ou da linha de comando."""
        if texto.startswith("="):
            return self.avaliar(texto[1:])
        tipo = self.props[chave].get("type")
        if tipo == "bool":
            return texto.strip().lower() in ("true", "1", "yes")
        if tipo == "int":
            return int(float(texto))
        if tipo == "float":
            return float(texto)
        return texto

    def avaliar(self, expr):
        return eval(expr, {"__builtins__": __builtins__}, self)

    def calcular(self, chave):
        for camada in self.camadas:
            if chave in camada:
                return self.converter(chave, camada[chave])
        p = self.props[chave]
        if "value" in p:
            v = p["value"]
            return self.avaliar(v) if isinstance(v, str) else v
        return p.get("default_value")


def texto(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def main():
    global RES
    montagem, modelo, saida = sys.argv[1:4]
    RES = os.path.join(montagem, "share", "cura", "resources")
    usuario = dict(a.split("=", 1) for a in sys.argv[4:])
    props = definicoes(carregar("creality_ender3", "definitions"))
    props_ext = definicoes(carregar("creality_base_extruder_0", "extruders"))
    so_extrusor = {k: v for k, v in props_ext.items() if k not in props}
    props.update(so_extrusor)
    q = os.path.join(RES, "quality", "creality", "base")
    camadas = [usuario,
               perfil(os.path.join(q, "base_0.4_PLA_standard.inst.cfg")),
               perfil(os.path.join(q, "base_global_standard.inst.cfg")),
               {"machine_nozzle_size": "0.4"}]
    r = Resolver(props, camadas)
    valores, falhas = {}, []
    for chave, p in props.items():
        if p.get("type") == "category":
            continue
        try:
            v = r[chave]
        except Exception as e:                      # noqa: BLE001
            falhas.append(f"{chave}: {type(e).__name__} {e}")
            continue
        if v is not None:
            valores[chave] = v
    for chave in ("machine_start_gcode", "machine_end_gcode"):
        g = valores[chave]
        for nome in list(valores):
            if "{" + nome + "}" in g:
                g = g.replace("{" + nome + "}", texto(valores[nome]))
        valores[chave] = g
    if falhas:
        print("Ajustes que não consegui resolver:", *falhas, sep="\n  ", file=sys.stderr)

    cmd = ["/lib64/ld-linux-x86-64.so.2", "--library-path", montagem, os.path.join(montagem, "CuraEngine"),
           "slice", "-j", os.path.join(RES, "definitions", "creality_ender3.def.json")]
    for chave, v in valores.items():
        if chave not in so_extrusor:
            cmd += ["-s", f"{chave}={texto(v)}"]
    cmd += ["-e0"]
    for chave, v in valores.items():
        cmd += ["-s", f"{chave}={texto(v)}"]
    cmd += ["-l", modelo, "-o", saida]
    amb = dict(os.environ, CURA_ENGINE_SEARCH_PATH=os.path.join(RES, "definitions") + ":" + os.path.join(RES, "extruders"))
    res = subprocess.run(cmd, env=amb, capture_output=True, text=True)
    log = res.stdout + res.stderr
    if res.returncode != 0:
        open(saida + ".log", "w").write(log)
    linhas = [l for l in log.splitlines() if "[error]" in l or "[warning]" in l or "Print time" in l or "Filament" in l]
    print("\n".join(l[:300] for l in linhas[-25:]))
    print("código de saída:", res.returncode)


if __name__ == "__main__":
    main()
