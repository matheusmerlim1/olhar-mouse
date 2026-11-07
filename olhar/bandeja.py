"""Ícone na bandeja (perto do relógio): o programa roda sem janela.

Janelas só aparecem quando precisam: QR code do celular, calibração, ou a
câmera quando a pessoa pede pelo menu. O menu do ícone só liga "bandeiras" no
objeto `Controle`; quem age é o laço principal (as janelas do OpenCV têm de
ser abertas sempre pela mesma thread).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PIL import Image, ImageDraw

CORES = {
    "carregando": "#d97706",   # laranja
    "celular": "#2563eb",      # azul: esperando o celular
    "calibrando": "#7c3aed",   # roxo
    "seguindo": "#16a34a",     # verde
    "pausado": "#6b7280",      # cinza
    "sem_rosto": "#dc2626",    # vermelho
}
TEXTO = {
    "carregando": "carregando…",
    "celular": "esperando o celular (QR code)",
    "calibrando": "calibrando",
    "seguindo": "seguindo o olhar",
    "pausado": "PAUSADO (F9 retoma)",
    "sem_rosto": "rosto não encontrado",
}


def desenhar_icone(estado: str, tamanho: int = 64) -> Image.Image:
    """Olho branco num círculo colorido (cor = estado). Desenhado em 4× e reduzido."""
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cor = CORES.get(estado, CORES["carregando"])
    d.ellipse((8, 8, S - 8, S - 8), fill=cor)
    # contorno do olho: duas curvas formando uma amêndoa
    d.chord((36, 70, 220, 250), start=200, end=340, fill="white")
    d.chord((36, 6, 220, 186), start=20, end=160, fill="white")
    d.ellipse((92, 92, 164, 164), fill=cor)            # íris
    d.ellipse((114, 114, 142, 142), fill="#111111")    # pupila
    if estado == "pausado":
        d.line((60, 60, 196, 196), fill=cor, width=30)
        d.line((60, 60, 196, 196), fill="white", width=14)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


class Controle:
    """Pedidos do menu/teclas para o laço principal (lidos a cada quadro)."""

    def __init__(self):
        self.pausado = False
        self.recalibrar = False
        self.mostrar_camera = False
        self.reiniciar = False      # config mudou (câmera, óculos, olho): reabre tudo
        self.sair = False


# ---------------------------------------------------------------- iniciar com o Windows
CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOME_RUN = "OlharMouse"


def comando_inicio(raiz: Path) -> str:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pyw}" -m olhar --pasta "{raiz}"'


def inicia_com_windows() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN) as k:
            winreg.QueryValueEx(k, NOME_RUN)
            return True
    except OSError:
        return False


def definir_inicio_com_windows(ligar: bool, raiz: Path) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, NOME_RUN, 0, winreg.REG_SZ, comando_inicio(raiz))
        else:
            try:
                winreg.DeleteValue(k, NOME_RUN)
            except OSError:
                pass


class Bandeja:
    def __init__(self, raiz: Path, cfg: dict, controle: Controle, salvar_cfg):
        import pystray
        self.raiz, self.cfg, self.ctl, self._salvar_cfg = raiz, cfg, controle, salvar_cfg
        self.estado = "carregando"
        self._icone = pystray.Icon("olhar-mouse", desenhar_icone(self.estado),
                                   "Olhar-mouse — carregando…", menu=self._menu())
        self._icone.run_detached()

    # ----- estado e avisos (chamados pelo laço principal)
    def definir_estado(self, estado: str) -> None:
        if estado == self.estado:
            return
        self.estado = estado
        self._icone.icon = desenhar_icone(estado)
        self._icone.title = f"Olhar-mouse — {TEXTO.get(estado, estado)}"
        self._icone.update_menu()

    def notificar(self, titulo: str, msg: str) -> None:
        try:
            self._icone.notify(msg, titulo)
        except Exception:
            pass

    def fechar(self) -> None:
        self._icone.stop()

    # ----- ações do menu (rodam na thread do ícone: só mexem em bandeiras)
    def _pausar(self, *_):
        self.ctl.pausado = not self.ctl.pausado

    def _recalibrar(self, *_):
        self.ctl.recalibrar = True

    def _camera_janela(self, *_):
        self.ctl.mostrar_camera = not self.ctl.mostrar_camera

    def _mudar(self, chave, valor):
        def acao(*_):
            if self.cfg.get(chave) == valor:
                return
            self.cfg[chave] = valor
            self._salvar_cfg(self.cfg)
            self.ctl.reiniciar = True
        return acao

    def _alternar(self, chave, reinicia=True):
        def acao(*_):
            self.cfg[chave] = not self.cfg.get(chave)
            self._salvar_cfg(self.cfg)
            if reinicia:
                self.ctl.reiniciar = True
        return acao

    def _inicio(self, *_):
        definir_inicio_com_windows(not inicia_com_windows(), self.raiz)
        self._icone.update_menu()

    def _firewall(self, *_):
        script = self.raiz / "ferramentas" / "liberar-firewall.ps1"
        # o próprio script pede a confirmação de administrador do Windows
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _sair(self, *_):
        self.ctl.sair = True

    def _menu(self):
        import pystray
        M, Sep = pystray.MenuItem, pystray.Menu.SEPARATOR
        cam = lambda: str(self.cfg.get("camera")).lower()
        return pystray.Menu(
            M(lambda _: self._icone.title if getattr(self, "_icone", None) else "Olhar-mouse", None, enabled=False),
            Sep,
            M(lambda _: "Retomar (F9)" if self.ctl.pausado else "Pausar (F9)", self._pausar, default=True),
            M("Recalibrar (F10)", self._recalibrar),
            M("Mostrar a câmera", self._camera_janela, checked=lambda _: self.ctl.mostrar_camera),
            Sep,
            M("Câmera", pystray.Menu(
                M("Webcam do computador", self._mudar("camera", 0), radio=True,
                  checked=lambda _: cam() not in ("celular",) and not cam().startswith("http")),
                M("Celular (QR code)", self._mudar("camera", "celular"), radio=True,
                  checked=lambda _: cam() == "celular"),
            )),
            M("Olho usado", pystray.Menu(
                M("Os dois", self._mudar("olho", "ambos"), radio=True,
                  checked=lambda _: self.cfg.get("olho") == "ambos"),
                M("Só o esquerdo", self._mudar("olho", "esquerdo"), radio=True,
                  checked=lambda _: self.cfg.get("olho") == "esquerdo"),
                M("Só o direito", self._mudar("olho", "direito"), radio=True,
                  checked=lambda _: self.cfg.get("olho") == "direito"),
            )),
            M("Uso óculos", self._alternar("oculos"), checked=lambda _: bool(self.cfg.get("oculos"))),
            M("Bipes", self._alternar("som", reinicia=False), checked=lambda _: bool(self.cfg.get("som"))),
            Sep,
            M("Iniciar com o Windows", self._inicio, checked=lambda _: inicia_com_windows()),
            M("Liberar firewall para o celular…", self._firewall),
            M("Abrir configurações (config.json)", lambda *_: os.startfile(self.raiz / "config.json")),
            M("Ver registro", lambda *_: os.startfile(self.raiz / "dados" / "olhar.log")),
            Sep,
            M("Sair", self._sair),
        )
