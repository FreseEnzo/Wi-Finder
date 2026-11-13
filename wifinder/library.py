"""Biblioteca de voos: uma pasta com um log do ESP32 por voo.

Cada voo é o arquivo bruto baixado da placa, guardado como
`<data>_<hora>_<nome>.log` (data e hora UTC do primeiro fix do GPS). O banco,
o mapa e o relatório são gerados a partir dele quando pedidos, então a pasta
pode ser copiada ou sincronizada à vontade.
"""

import json
import re
import threading
import time
from pathlib import Path

from . import db, esp32, estimate

PREVIEW_PTS = 80


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    # --------------------------------------------------------------- índice

    def _index(self):
        try:
            return json.loads((self.root / "index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, index):
        tmp = self.root / "index.json.tmp"
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / "index.json")

    def ids(self):
        return sorted(p.stem for p in self.root.glob("*.log"))

    def path(self, fid):
        if fid not in self.ids():  # também barra nomes com "/" ou ".."
            raise KeyError(fid)
        return self.root / f"{fid}.log"

    # ------------------------------------------------------------- entrada

    def add_log(self, name, data):
        """Guarda um log baixado da placa. Retorna (id, situação), com situação
        "novo", "atualizado" (o mesmo voo, agora com mais dados), "igual" ou
        "vazio" (sem nenhum fix nem rede: não é guardado, id None)."""
        fixes, samples = esp32.parse_log(data.decode("utf-8", "replace"))
        if not fixes and not samples:
            return None, "vazio"
        stem = re.sub(r"[^A-Za-z0-9_-]", "", Path(name).stem) or "voo"
        when = time.strftime("%Y-%m-%d_%H%M", time.gmtime(fixes[0][1])) if fixes else "sem-gps"
        with self.lock:
            n = 1
            while True:
                fid = f"{when}_{stem}" + ("" if n == 1 else f"-{n}")
                path = self.root / f"{fid}.log"
                if not path.exists():
                    path.write_bytes(data)
                    return fid, "novo"
                old = path.read_bytes()
                if old == data:
                    return fid, "igual"
                if data.startswith(old):  # o arquivo cresceu depois do último download
                    path.write_bytes(data)
                    return fid, "atualizado"
                if old.startswith(data):
                    return fid, "igual"
                n += 1

    def rename(self, fid, title):
        self.path(fid)
        with self.lock:
            index = self._index()
            index.setdefault(fid, {})["title"] = title.strip()[:80]
            self._save(index)

    def delete(self, fid):
        path = self.path(fid)
        with self.lock:
            path.unlink()
            index = self._index()
            index.pop(fid, None)
            self._save(index)

    # --------------------------------------------------------------- leitura

    def connect(self, ids):
        """Banco em memória com os voos pedidos."""
        con = db.connect(":memory:")
        for fid in ids:
            esp32.import_log(con, self.path(fid).read_text(encoding="utf-8", errors="replace"), fid)
        return con

    def load(self, ids):
        """(aparelhos, trajetória com tempo, resumo) dos voos pedidos, juntos."""
        con = self.connect(ids)
        routers, _, _ = estimate.estimate(con)
        track = estimate.load_track(con)
        samples = con.execute("SELECT count(*) FROM samples").fetchone()[0]
        con.close()
        return routers, track, estimate.flight_summary(track, samples, routers)

    def title(self, fid, index=None):
        saved = (index if index is not None else self._index()).get(fid, {}).get("title")
        if saved:
            return saved
        m = re.search(r"_v0*(\d+)(-\d+)?$", fid)
        return f"Voo {m.group(1)}" if m else fid

    def _meta(self, fid):
        path = self.path(fid)
        fixes, samples = esp32.parse_log(path.read_text(encoding="utf-8", errors="replace"))
        meta = dict(fixes=len(fixes), heard=len(samples), nets=len({s[1] for s in samples}),
                    start=fixes[0][1] if fixes else None, devices=None, duration=None, distance=None, preview=[])
        if fixes:
            routers, track, s = self.load([fid])
            meta.update(devices=len(routers), nets=s["redes"] or meta["nets"],
                        duration=s.get("duracao"), distance=s.get("distancia"))
            step = max(1, len(track) // PREVIEW_PTS)
            meta["preview"] = [[round(p[0], 6), round(p[1], 6)] for p in track[::step]]
        return meta

    def flights(self):
        """Lista dos voos, do mais recente ao mais antigo, com os números de cada um."""
        from . import __version__

        with self.lock:
            index = self._index()
        out, changed = [], False
        for fid in self.ids():
            size = (self.root / f"{fid}.log").stat().st_size
            entry = index.setdefault(fid, {})
            if entry.get("size") != size or entry.get("version") != __version__ or "meta" not in entry:
                entry.update(size=size, version=__version__, meta=self._meta(fid))
                changed = True
            out.append(dict(entry["meta"], id=fid, title=self.title(fid, index), size=size))
        if changed:
            with self.lock:
                current = self._index()
                for fid, entry in index.items():
                    if fid in current and "title" in current[fid]:
                        entry["title"] = current[fid]["title"]  # renomeado enquanto calculava
                self._save({fid: e for fid, e in index.items() if (self.root / f"{fid}.log").exists()})
        out.sort(key=lambda f: (f["start"] is not None, f["start"] or 0, f["id"]), reverse=True)
        return out
