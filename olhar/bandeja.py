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
    "parado": "#475569",       # cinza-azulado: sem câmera ligada, esperando a escolha
    "sem_rosto": "#dc2626",    # vermelho
    "fora": "#b45309",         # âmbar: olhar fora da área calibrada
    "cedido": "#0e7490",       # azul-petróleo: mouse físico em uso
}
TEXTO = {
    "carregando": "carregando…",
    "celular": "esperando o celular (QR code)",
    "calibrando": "calibrando",
    "seguindo": "seguindo o olhar",
    "pausado": "PAUSADO (F9 retoma)",
    "parado": "parado — clique para escolher a câmera",
    "sem_rosto": "rosto não encontrado",
    "fora": "olhar fora da área calibrada (F10 recalibra)",
    "cedido": "mouse físico em uso — olhe para outro ponto para o olhar retomar",
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
    if estado in ("pausado", "parado"):
        d.line((60, 60, 196, 196), fill=cor, width=30)
        d.line((60, 60, 196, 196), fill="white", width=14)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


class Controle:
    """Pedidos do menu/teclas para o laço principal (lidos a cada quadro)."""

    def __init__(self):
        self.pausado = False
        self.recalibrar = False
        self.testar = False         # abrir o teste de mira
        self.mostrar_camera = False
        self.reiniciar = False      # config mudou (câmera, óculos, olho): reabre tudo
        self.escolher = False       # mostrar a tela das 3 opções de câmera
        self.parado = False         # na bandeja, sem câmera ligada (saiu da escolha/calibração)
        self.reabrir = False        # atualizou pelo menu: sair e abrir a versão nova
        self.refiltrar = False      # mudou a estabilidade do cursor (vale na hora)
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


# ---------------------------------------------------------------- atalhos com ícone
def gerar_ico(raiz: Path) -> Path:
    """Ícone do olho (verde) em .ico, vários tamanhos, para os atalhos do Windows."""
    destino = raiz / "olhar.ico"
    desenhar_icone("seguindo", 256).save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                                          (64, 64), (128, 128), (256, 256)])
    return destino


def pasta_atalhos() -> list[Path]:
    """Área de Trabalho e menu Iniciar do usuário (com OneDrive, a Área de Trabalho muda de lugar)."""
    import ctypes
    from ctypes import wintypes
    pastas = []
    for csidl in (0x0010, 0x0002):  # CSIDL_DESKTOPDIRECTORY, CSIDL_PROGRAMS
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
            pastas.append(Path(buf.value))
    return pastas


def criar_atalhos(raiz: Path) -> list[Path]:
    """Cria "Olhar-mouse.lnk" na Área de Trabalho e no menu Iniciar, com o ícone do olho.

    Abre o pythonw direto (sem a janela preta do .bat) e mostra a escolha da câmera.
    """
    ico = gerar_ico(raiz)
    pyw = raiz / ".venv" / "Scripts" / "pythonw.exe"
    feitos = []
    for pasta in pasta_atalhos():
        lnk = pasta / "Olhar-mouse.lnk"
        # caminhos com acento vão por variável de ambiente, sem brigar com aspas
        env = dict(os.environ, OM_LNK=str(lnk), OM_ALVO=str(pyw), OM_PASTA=str(raiz), OM_ICO=str(ico))
        script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:OM_LNK);"
                  "$s.TargetPath = $env:OM_ALVO; $s.Arguments = '-m olhar';"
                  "$s.WorkingDirectory = $env:OM_PASTA; $s.IconLocation = $env:OM_ICO + ',0';"
                  "$s.Description = 'Controla o mouse com o olhar'; $s.Save()")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, capture_output=True,
                           text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and lnk.exists():
            feitos.append(lnk)
        else:
            print(f"Atalho não criado em {pasta}: {r.stderr.strip()}")
    return feitos


class Bandeja:
    def __init__(self, raiz: Path, cfg: dict, controle: Controle, salvar_cfg):
        import pystray
        self.raiz, self.cfg, self.ctl, self._salvar_cfg = raiz, cfg, controle, salvar_cfg
        self.estado = "carregando"
        self._cameras: list[str] = []
        from .atualizador import versao_curta
        self._versao = versao_curta(raiz)
        self._icone = pystray.Icon("olhar-mouse", desenhar_icone(self.estado),
                                   "Olhar-mouse — carregando…", menu=self._menu())
        # o ícone roda numa thread só dele, com o próprio laço de mensagens do
        # Windows. (run_detached exige que outra parte do programa trate as
        # mensagens — no ditado é o tkinter; aqui ninguém faz isso e o ícone
        # nunca aparecia na bandeja.)
        self._pronto = threading.Event()

        def preparar(icone):
            icone.visible = True
            self._pronto.set()

        threading.Thread(target=self._icone.run, args=(preparar,), daemon=True, name="bandeja").start()
        self._pronto.wait(5)
        threading.Thread(target=self._vigiar_cameras, daemon=True).start()

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
    def _principal(self, *_):
        """Clique duplo no ícone: parado → escolher a câmera; rodando → pausar/retomar."""
        if self.ctl.parado:
            self.ctl.escolher = True
        else:
            self.ctl.pausado = not self.ctl.pausado

    def _escolher(self, *_):
        self.ctl.escolher = True

    def _testar(self, *_):
        self.ctl.testar = True

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

    def _estabilidade(self, nivel):
        def acao(*_):
            self.cfg["estabilidade"] = nivel
            self._salvar_cfg(self.cfg)
            self.ctl.refiltrar = True
        return acao

    def _zoom(self, modo):
        def acao(*_):
            self.cfg["zoom"] = modo
            self._salvar_cfg(self.cfg)
            self.ctl.refiltrar = True
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

    def _procurar_atualizacao(self, *_):
        def tarefa():
            from .atualizador import procurar_e_aplicar
            atualizou, msg = procurar_e_aplicar(self.raiz)
            print(f"Atualização (menu): {msg}")
            if atualizou:
                self.notificar("Olhar-mouse atualizado", "Reabrindo com a versão nova…")
                self.ctl.reabrir = True
                self.ctl.sair = True
            else:
                self.notificar("Atualizações", msg[:1].upper() + msg[1:] + ".")
        threading.Thread(target=tarefa, daemon=True).start()

    def _atalhos(self, *_):
        feitos = criar_atalhos(self.raiz)
        self.notificar("Atalhos criados" if feitos else "Atalhos não criados",
                       "Ícone \"Olhar-mouse\" na Área de Trabalho e no menu Iniciar." if feitos
                       else "Veja o registro (dados/olhar.log).")

    def _firewall(self, *_):
        script = self.raiz / "ferramentas" / "liberar-firewall.ps1"
        # o próprio script pede a confirmação de administrador do Windows
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _sair(self, *_):
        self.ctl.sair = True

    def _itens_camera(self):
        """Submenu gerado na hora: câmeras do Windows pelo nome + modos do celular."""
        import pystray
        M = pystray.MenuItem
        from .escolha import eh_virtual
        atual = self.cfg.get("camera")
        itens = [M("1. Câmera do computador:", None, enabled=False)]
        reais = 0
        for i, nome in enumerate(self._cameras):
            if eh_virtual(nome):
                continue  # OBS Virtual Camera e afins não filmam o rosto: não são oferecidas
            reais += 1
            marcado = atual == nome or (isinstance(atual, int) and atual == i)
            itens.append(M(f"     {nome}", self._mudar("camera", nome), radio=True,
                           checked=lambda _, m=marcado: m))
        if not reais:
            itens.append(M("     (nenhuma câmera encontrada)", None, enabled=False))
        itens += [
            pystray.Menu.SEPARATOR,
            M("2. Celular pelo QR code (Wi-Fi)", self._mudar("camera", "celular"), radio=True,
              checked=lambda _: str(self.cfg.get("camera")).lower() == "celular"),
            M("3. Celular pelo cabo USB (Android)", self._mudar("camera", "usb"), radio=True,
              checked=lambda _: str(self.cfg.get("camera")).lower() == "usb"),
            pystray.Menu.SEPARATOR,
            M("Perguntar ao abrir", self._alternar("perguntar_camera", reinicia=False),
              checked=lambda _: bool(self.cfg.get("perguntar_camera", True))),
        ]
        return itens

    def _vigiar_cameras(self):
        """Atualiza a lista de câmeras (ligar o cabo do celular em modo webcam cria uma nova)."""
        import time
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        from .camera import listar_cameras
        while True:
            nomes = listar_cameras()
            if nomes != self._cameras:
                self._cameras = nomes
                try:
                    self._icone.update_menu()
                except Exception:
                    pass
            time.sleep(5)

    def _menu(self):
        import pystray
        M, Sep = pystray.MenuItem, pystray.Menu.SEPARATOR
        return pystray.Menu(
            M(lambda _: self._icone.title if getattr(self, "_icone", None) else "Olhar-mouse", None, enabled=False),
            Sep,
            M(lambda _: "Escolher câmera e começar…" if self.ctl.parado
              else ("Retomar (F9)" if self.ctl.pausado else "Pausar (F9)"), self._principal, default=True),
            M("Trocar de câmera…", self._escolher, visible=lambda _: not self.ctl.parado),
            M("Testar e ajustar a mira (F8)", self._testar, visible=lambda _: not self.ctl.parado),
            M("Recalibrar (F10)", self._recalibrar),
            M("Mostrar a câmera", self._camera_janela, checked=lambda _: self.ctl.mostrar_camera),
            Sep,
            M("Câmera", pystray.Menu(self._itens_camera)),
            M("Olho usado", pystray.Menu(
                M("Os dois", self._mudar("olho", "ambos"), radio=True,
                  checked=lambda _: self.cfg.get("olho") == "ambos"),
                M("Só o esquerdo", self._mudar("olho", "esquerdo"), radio=True,
                  checked=lambda _: self.cfg.get("olho") == "esquerdo"),
                M("Só o direito", self._mudar("olho", "direito"), radio=True,
                  checked=lambda _: self.cfg.get("olho") == "direito"),
            )),
            M("Estabilidade do cursor", pystray.Menu(
                M("Baixa (mais rápido)", self._estabilidade("baixa"), radio=True,
                  checked=lambda _: self.cfg.get("estabilidade") == "baixa"),
                M("Média", self._estabilidade("media"), radio=True,
                  checked=lambda _: self.cfg.get("estabilidade", "media") == "media"),
                M("Alta (mais firme)", self._estabilidade("alta"), radio=True,
                  checked=lambda _: self.cfg.get("estabilidade") == "alta"),
            )),
            M("Zoom da câmera", pystray.Menu(
                M("Automático", self._zoom("auto"), radio=True,
                  checked=lambda _: self.cfg.get("zoom", "auto") != "off"),
                M("Desligado", self._zoom("off"), radio=True,
                  checked=lambda _: self.cfg.get("zoom", "auto") == "off"),
            )),
            M("Ponteiro separado do mouse", self._alternar("ponteiro_separado", reinicia=False),
              checked=lambda _: bool(self.cfg.get("ponteiro_separado", True))),
            M("Uso óculos", self._alternar("oculos"), checked=lambda _: bool(self.cfg.get("oculos"))),
            M("Clique por piscada", self._alternar("clique_piscada", reinicia=False),
              checked=lambda _: bool(self.cfg.get("clique_piscada", True))),
            M("Bipes", self._alternar("som", reinicia=False), checked=lambda _: bool(self.cfg.get("som"))),
            Sep,
            M("Iniciar com o Windows", self._inicio, checked=lambda _: inicia_com_windows()),
            M(lambda _: f"Procurar atualizações agora (versão {self._versao})", self._procurar_atualizacao),
            M("Criar atalhos (Área de Trabalho e menu Iniciar)", self._atalhos),
            M("Liberar firewall para o celular…", self._firewall),
            M("Abrir configurações (config.json)", lambda *_: os.startfile(self.raiz / "config.json")),
            M("Ver registro", lambda *_: os.startfile(self.raiz / "dados" / "olhar.log")),
            Sep,
            M("Sair", self._sair),
        )
