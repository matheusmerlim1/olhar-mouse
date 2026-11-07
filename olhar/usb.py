"""Celular Android pelo cabo USB, sem Wi-Fi e sem internet.

Usa o ADB (ferramenta oficial do Android) para criar um "túnel" pelo cabo:
`adb reverse` faz o endereço 127.0.0.1:PORTA DO CELULAR cair no servidor do
PC. Vantagens sobre o Wi-Fi:
- não depende de rede nenhuma nem do firewall (a conexão não sai do cabo);
- a página abre como http://127.0.0.1, que o navegador considera seguro:
  a câmera é liberada sem o aviso de "conexão não particular";
- o programa abre a página no celular sozinho (`am start`).

Precisa da "Depuração USB" ligada no celular (Opções do desenvolvedor) e de
aceitar o aviso "Permitir depuração USB?" na primeira vez.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np

URL_PLATFORM_TOOLS = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def achar_adb(raiz: Path) -> Path | None:
    """Procura o adb no PATH, no SDK do Android (Flutter/Android Studio) e na pasta do programa."""
    nome = "adb.exe" if sys.platform == "win32" else "adb"
    if (p := shutil.which("adb")):
        return Path(p)
    candidatos = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    if os.environ.get("LOCALAPPDATA"):
        candidatos.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"))
    candidatos += [r"C:\Android\sdk", r"C:\Android\Sdk", str(raiz / "ferramentas")]
    for base in filter(None, candidatos):
        p = Path(base) / "platform-tools" / nome
        if p.exists():
            return p
    return None


def baixar_adb(raiz: Path) -> Path:
    """Baixa o platform-tools oficial do Google (~7 MB) para ferramentas/."""
    import urllib.request
    destino = raiz / "ferramentas"
    destino.mkdir(exist_ok=True)
    zip_ = destino / "platform-tools.zip"
    urllib.request.urlretrieve(URL_PLATFORM_TOOLS, zip_)
    with zipfile.ZipFile(zip_) as z:
        z.extractall(destino)
    zip_.unlink()
    adb = destino / "platform-tools" / "adb.exe"
    if not adb.exists():
        raise RuntimeError("O pacote do ADB baixado não tem o adb.exe.")
    return adb


def ler_aparelhos(saida: str) -> list[dict]:
    """Interpreta a saída de `adb devices -l`."""
    aparelhos = []
    for linha in saida.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith(("List of devices", "*")):
            continue
        partes = linha.split()
        if len(partes) < 2:
            continue
        info = {"serial": partes[0], "estado": partes[1]}
        for p in partes[2:]:
            if ":" in p:
                k, v = p.split(":", 1)
                info[k] = v
        aparelhos.append(info)
    return aparelhos


class AdbUsb:
    def __init__(self, adb: Path):
        self.adb = adb

    def _rodar(self, *args, serial: str | None = None, timeout: float = 8) -> str:
        cmd = [str(self.adb)] + (["-s", serial] if serial else []) + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_SEM_JANELA)
        return (r.stdout or "") + (r.stderr or "")

    def aparelhos(self) -> list[dict]:
        try:
            return ler_aparelhos(self._rodar("devices", "-l"))
        except (OSError, subprocess.TimeoutExpired):
            return []

    def estado(self) -> tuple[str, dict | None]:
        """("pronto"|"nao_autorizado"|"sem_aparelho", aparelho)."""
        lista = self.aparelhos()
        for a in lista:
            if a["estado"] == "device":
                return "pronto", a
        for a in lista:
            if a["estado"] == "unauthorized":
                return "nao_autorizado", a
        return "sem_aparelho", None

    def preparar(self, serial: str, porta: int, url: str) -> None:
        """Cria o túnel 127.0.0.1:porta (celular) → PC e abre a página no navegador do celular."""
        self._rodar("reverse", f"tcp:{porta}", f"tcp:{porta}", serial=serial)
        # acorda a tela antes de abrir o navegador
        self._rodar("shell", "input", "keyevent", "KEYCODE_WAKEUP", serial=serial)
        self._rodar("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url, serial=serial)

    def desfazer(self, porta: int) -> None:
        try:
            self._rodar("reverse", "--remove", f"tcp:{porta}", timeout=3)
        except Exception:
            pass


def aguardar_usb(cam, adb: AdbUsb, janela: str, deve_parar=lambda: False) -> bool:
    """Janela de instruções até o celular (pelo cabo) começar a mandar imagem."""
    from .calibracao import Cancelado

    w, h = 900, 640
    cv2.namedWindow(janela, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(janela, w, h)
    cv2.setWindowProperty(janela, cv2.WND_PROP_TOPMOST, 1)
    fonte = cv2.FONT_HERSHEY_SIMPLEX

    def linha(img, txt, y, k=0.6, cor=(235, 235, 235), x=40):
        cv2.putText(img, txt, (x, y), fonte, k, cor, 2 if k >= 0.75 else 1, cv2.LINE_AA)

    preparado_em = None       # serial já configurado
    n_antes = cam.recebidos
    conectou = None
    prox_consulta = 0.0
    estado, aparelho = "sem_aparelho", None
    try:
        while True:
            if deve_parar():
                return False
            agora = time.monotonic()
            if agora >= prox_consulta:
                estado, aparelho = adb.estado()
                prox_consulta = agora + 1.0
                if estado == "pronto" and preparado_em != aparelho["serial"]:
                    adb.preparar(aparelho["serial"], cam.porta, cam.url)
                    preparado_em = aparelho["serial"]
                elif estado != "pronto":
                    preparado_em = None

            img = np.full((h, w, 3), 24, np.uint8)
            linha(img, "Celular pelo cabo USB (Android)", 50, 0.9)
            linha(img, "1. Ligue o celular no PC com o cabo USB.", 110)
            linha(img, "2. No celular, ligue a Depuracao USB:", 145)
            linha(img, "   Configuracoes > Sobre o telefone > toque 7x em 'Numero da versao';", 175, 0.5, (190, 190, 190))
            linha(img, "   depois Configuracoes > Sistema > Opcoes do desenvolvedor > Depuracao USB.", 200, 0.5, (190, 190, 190))
            linha(img, "3. Aceite 'Permitir depuracao USB?' no celular (marque 'sempre').", 235)
            linha(img, "4. A pagina abre sozinha no celular: toque em 'Usar camera' e permita.", 270)
            linha(img, "Apoie o celular parado, perto do monitor, virado para o seu rosto.", 320, 0.55, (190, 190, 190))
            linha(img, f"Se a pagina nao abrir, digite no navegador do celular: {cam.url}", 350, 0.5, (120, 200, 255))

            if cam.recebidos > n_antes:
                conectou = conectou or agora
                txt, cor = "Celular conectado! Comecando...", (120, 230, 120)
            elif estado == "pronto":
                nome = (aparelho or {}).get("model", "celular").replace("_", " ")
                txt, cor = f"{nome} encontrado. Abrindo a pagina no celular...", (80, 200, 255)
            elif estado == "nao_autorizado":
                txt, cor = "Celular encontrado: aceite 'Permitir depuracao USB?' na tela dele.", (80, 200, 255)
            else:
                txt, cor = "Aguardando o celular no cabo USB (com a depuracao USB ligada)...", (80, 160, 255)
            linha(img, txt, 420, 0.7, cor)
            linha(img, "Esc fecha esta janela", h - 25, 0.5, (150, 150, 150))
            cv2.imshow(janela, img)
            if (cv2.waitKey(50) & 0xFF) in (27, ord("q")):
                raise Cancelado
            if conectou and agora - conectou > 1.0:
                return True
    finally:
        try:
            cv2.destroyWindow(janela)
        except cv2.error:
            pass
