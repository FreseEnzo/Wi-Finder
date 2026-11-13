"""Logs do firmware ESP32 (firmware/wifinder): download pela USB e importação.

Formato do log, uma linha por registro:
    F <millis> <unix_t> <lat> <lon> <alt> <sats> <hdop>   fix do GPS
    S <millis> <bssid> <canal> <rssi> <ssid_hex>          rede ouvida
A posição de cada rede é interpolada aqui a partir dos fixes vizinhos, pelo
relógio millis() da placa.
"""

import time
from pathlib import Path

import numpy as np

MAX_GAP = 2.0  # segundos: amostra sem fix a menos que isso é descartada


def freq_of(channel):
    return 2484 if channel == 14 else 2407 + 5 * channel


def parse_log(text):
    """Retorna (fixes, samples). fixes: (ms, t, lat, lon, alt, sats, hdop);
    samples: (ms, bssid, canal, rssi, ssid)."""
    fixes, samples = [], []
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        try:
            if f[0] == "F" and len(f) == 8:
                v = [float(x) for x in f[1:]]
                fixes.append((v[0], v[1], v[2], v[3], v[4], int(v[5]), v[6]))
            elif f[0] == "S" and len(f) >= 5:
                ssid = bytes.fromhex(f[5]).decode("utf-8", "replace") if len(f) > 5 else ""
                samples.append((float(f[1]), f[2].lower(), int(f[3]), float(f[4]), ssid))
        except ValueError:
            continue
    return fixes, samples


def import_log(con, text, name=None, max_gap=MAX_GAP):
    """Grava um log no banco. Retorna (fixes, amostras gravadas, amostras descartadas).

    Se `name` for dado, o arquivo fica registrado na tabela imports e uma
    segunda importação do mesmo nome é ignorada (retorna None).
    """
    if name and con.execute("SELECT 1 FROM imports WHERE name=?", (name,)).fetchone():
        return None
    fixes, samples = parse_log(text)
    con.executemany(
        "INSERT INTO track VALUES (?,?,?,?,?,?)", [f[1:] for f in fixes]
    )
    saved = 0
    if fixes and samples:
        F = np.array([f[:5] for f in fixes], dtype=float)
        F = F[np.argsort(F[:, 0])]
        fm = F[:, 0] / 1000
        sm = np.array([s[0] for s in samples]) / 1000
        i = np.clip(np.searchsorted(fm, sm), 1, len(fm) - 1)
        gap = np.minimum(np.abs(sm - fm[i - 1]), np.abs(sm - fm[i]))
        cols = [np.interp(sm, fm, F[:, k]) for k in (1, 2, 3, 4)]  # t, lat, lon, alt
        # Fora do intervalo dos fixes a posição fica parada, mas o relógio anda.
        cols[0] = cols[0] + (sm - np.clip(sm, fm[0], fm[-1]))
        rows = [
            (float(t), float(lat), float(lon), float(alt), s[1], s[4], freq_of(s[2]), s[3])
            for s, g, t, lat, lon, alt in zip(samples, gap, *cols) if g <= max_gap
        ]
        con.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)", rows)
        saved = len(rows)
    if name:
        con.execute("INSERT INTO imports VALUES (?,?,?)", (name, len(fixes), saved))
    con.commit()
    return len(fixes), saved, len(samples) - saved


# ------------------------------------------------------------------ serial

class Board:
    """Conversa com o firmware pela USB. Abrir a porta reinicia a placa."""

    def __init__(self, port, baud=115200):
        import serial  # pyserial

        self.ser = serial.Serial(port, baud, timeout=3)
        time.sleep(2.5)  # espera o boot depois do reset
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.close()

    def _cmd(self, cmd):
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\n").encode())

    def _readline(self):
        """Próxima linha que não seja status (#). Lança TimeoutError se parar."""
        while True:
            raw = self.ser.readline()
            if not raw:
                raise TimeoutError("a placa não respondeu")
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line.startswith("#"):
                return line

    def ls(self):
        """Lista [(nome, bytes)] dos logs na flash."""
        self._cmd("ls")
        while self._readline() != "--- LS ---":
            pass
        out = []
        while True:
            line = self._readline()
            if line == "--- END LS ---":
                return out
            name, size = line.rsplit(" ", 1)
            out.append((name, int(size)))

    def dump(self, name, progress=None):
        """Baixa um arquivo. progress(bytes já recebidos) é chamado a cada pedaço."""
        self._cmd(f"dump {name}")
        while True:
            line = self._readline()
            if line.startswith("err:"):
                raise FileNotFoundError(f"{name}: {line}")
            if line.startswith("--- BEGIN "):
                size = int(line.split()[3])
                break
        data = b""
        while len(data) < size:
            chunk = self.ser.read(min(size - len(data), 4096))
            if not chunk:
                raise TimeoutError(f"{name}: download parou em {len(data)}/{size} bytes")
            data += chunk
            if progress:
                progress(len(data))
        while not self._readline().startswith("--- END "):
            pass  # linhas gravadas depois do tamanho anunciado ficam para o próximo pull
        return data

    def done(self, n):
        """Mostra na telinha que a transferência terminou."""
        self._cmd(f"done {n}")
        self._readline()

    def rm(self, name):
        self._cmd(f"rm {name}")
        return self._readline().startswith("ok")


def pull(con, port, out_dir, remove=False, log=print):
    """Baixa todos os logs da placa para out_dir e importa no banco."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    board = Board(port)
    try:
        files = board.ls()
        if not files:
            log("Nenhum log na placa.")
        for name, size in files:
            dest = out_dir / name.lstrip("/")
            log(f"{name}: {size} bytes... ", end="", flush=True)
            data = board.dump(name)
            dest.write_bytes(data)
            res = import_log(con, data.decode("utf-8", "replace"), name)
            if res is None:
                log("já importado")
            else:
                log(f"{res[0]} fixes, {res[1]} amostras ({res[2]} sem posição)")
            if remove:
                board.rm(name)
        board.done(len(files))
    finally:
        board.close()
