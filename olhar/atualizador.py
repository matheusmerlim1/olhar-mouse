"""Atualização automática: ao abrir, procura versão nova no GitHub e atualiza ANTES de rodar.

- Instalação com git (pasta de desenvolvimento) -> git fetch + merge --ff-only, só se não
  houver alteração local no código.
- Instalação pelo ZIP -> compara a versão gravada no ZIP (olhar/versao.txt, preenchido pelo
  git archive via export-subst) com o último commit do GitHub; se mudou, baixa o ZIP do ramo e
  copia por cima, sem tocar em dados/ (calibração e preferências) nem em .venv/.
Depois de atualizar, o programa reabre já com o código novo. Sem internet, segue normalmente.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "matheusmerlim1/olhar-mouse"
RAMO = "main"
PROTEGIDOS = {"dados", ".venv", ".git", "ferramentas/platform-tools"}
SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0     # CREATE_NO_WINDOW
AGENTE = {"User-Agent": "olhar-mouse-atualizador", "Accept": "application/vnd.github+json"}


def _git(raiz: Path, *args, timeout=20) -> subprocess.CompletedProcess:
    # git escreve em UTF-8; sem encoding explícito o Python lê como cp1252 e os acentos
    # dos títulos dos commits ("caía", "câmera") viravam lixo no card de novidades
    return subprocess.run(["git", "-c", "safe.directory=*", "-c", "i18n.logOutputEncoding=utf-8",
                           "-C", str(raiz), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=SEM_JANELA)


def versao_local(raiz: Path) -> str:
    """Commit desta instalação: do git, ou o gravado no ZIP (olhar/versao.txt)."""
    if (raiz / ".git").exists():
        try:
            r = _git(raiz, "rev-parse", "HEAD")
            if r.returncode == 0:
                return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    arq = raiz / "olhar" / "versao.txt"
    if arq.exists():
        v = arq.read_text(encoding="utf-8").strip()
        if v and "$Format" not in v:
            return v
    return ""


def versao_curta(raiz: Path) -> str:
    v = versao_local(raiz)
    return v[:7] if v else "?"


def commit_remoto(timeout: float = 6) -> str | None:
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/commits/{RAMO}", headers=AGENTE)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["sha"]
    except Exception:
        return None


def aplicar_zip(dados: bytes, raiz: Path) -> list[str]:
    """Copia o conteúdo do ZIP do GitHub por cima da pasta, sem tocar nos protegidos."""
    trocados = []
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        nomes = z.namelist()
        prefixo = nomes[0].split("/")[0] + "/"            # "olhar-mouse-main/"
        for nome in nomes:
            if nome.endswith("/") or not nome.startswith(prefixo):
                continue
            rel = nome[len(prefixo):]
            if any(rel == p or rel.startswith(p + "/") for p in PROTEGIDOS):
                continue
            destino = raiz / rel
            destino.parent.mkdir(parents=True, exist_ok=True)
            novo = z.read(nome)
            if destino.exists() and destino.read_bytes() == novo:
                continue
            tmp = destino.with_name(destino.name + ".novo")
            tmp.write_bytes(novo)
            os.replace(tmp, destino)
            trocados.append(rel)
    return trocados


def _instalar_dependencias(raiz: Path) -> None:
    py = raiz / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    print("requirements.txt mudou: instalando dependências…")
    r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                        "-r", str(raiz / "requirements.txt")],
                       capture_output=True, text=True, creationflags=SEM_JANELA)
    if r.returncode != 0:
        print("pip falhou:\n" + r.stdout[-2000:] + r.stderr[-2000:])


def procurar_e_aplicar(raiz: Path) -> tuple[bool, str]:
    """Devolve (atualizou, mensagem). Nunca levanta exceção: sem internet, só segue.

    Quando atualiza, grava em dados/novidades.json o que mudou (títulos dos commits entre a
    versão antiga e a nova), para a versão nova mostrar o card de novidades ao abrir.
    """
    antes = versao_local(raiz)
    try:
        if (raiz / ".git").exists():
            atualizou, msg = _via_git(raiz)
        else:
            atualizou, msg = _via_zip(raiz)
    except Exception as e:
        return False, f"falha ao procurar atualização: {e!r}"
    if atualizou:
        try:
            depois = versao_local(raiz)
            guardar_novidades(raiz, antes, depois, titulos_entre(raiz, antes, depois))
        except Exception as e:
            print(f"não consegui montar as novidades: {e!r}")
    return atualizou, msg


def titulos_entre(raiz: Path, antes: str, depois: str) -> list[str]:
    """Títulos dos commits de `antes` (exclusivo) até `depois`, do mais novo ao mais antigo."""
    if (raiz / ".git").exists() and antes:
        r = _git(raiz, "log", "--format=%s", f"{antes}..{depois}")
        if r.returncode == 0:
            return [l for l in r.stdout.splitlines() if l.strip()]
    if antes:
        url = f"https://api.github.com/repos/{REPO}/compare/{antes}...{depois}"
    else:  # versão antiga desconhecida: mostra as mudanças mais recentes
        url = f"https://api.github.com/repos/{REPO}/commits?sha={RAMO}&per_page=8"
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=10) as r:
        dados = json.load(r)
    commits = dados["commits"][::-1] if isinstance(dados, dict) else dados
    return [c["commit"]["message"].splitlines()[0] for c in commits]


def guardar_novidades(raiz: Path, antes: str, depois: str, titulos: list[str]) -> None:
    arq = raiz / "dados" / "novidades.json"
    arq.parent.mkdir(exist_ok=True)
    arq.write_text(json.dumps({"de": antes[:7], "para": depois[:7], "titulos": titulos},
                              ensure_ascii=False, indent=2), encoding="utf-8")


def _via_git(raiz: Path) -> tuple[bool, str]:
    if _git(raiz, "remote", "get-url", "origin").returncode != 0:
        return False, "sem repositório remoto"
    if _git(raiz, "fetch", "--quiet", "origin", RAMO, timeout=15).returncode != 0:
        return False, "sem conexão com o GitHub"
    atras = _git(raiz, "rev-list", "--count", f"HEAD..origin/{RAMO}").stdout.strip()
    if atras in ("", "0"):
        return False, f"já está na versão mais nova ({versao_curta(raiz)})"
    if _git(raiz, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        return False, "há versão nova, mas existem alterações locais no código: atualize à mão"
    req_antes = (raiz / "requirements.txt").read_bytes()
    if _git(raiz, "merge", "--ff-only", f"origin/{RAMO}").returncode != 0:
        return False, "há versão nova, mas o histórico local divergiu: atualize à mão"
    if (raiz / "requirements.txt").read_bytes() != req_antes:
        _instalar_dependencias(raiz)
    return True, f"atualizado pelo git ({atras} alteração(ões))"


def _via_zip(raiz: Path) -> tuple[bool, str]:
    remoto = commit_remoto()
    if remoto is None:
        return False, "sem conexão com o GitHub"
    local = versao_local(raiz)
    if local == remoto:
        return False, f"já está na versão mais nova ({remoto[:7]})"
    url = f"https://codeload.github.com/{REPO}/zip/refs/heads/{RAMO}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENTE), timeout=60) as r:
        dados = r.read()
    req_antes = (raiz / "requirements.txt").read_bytes() if (raiz / "requirements.txt").exists() else b""
    trocados = aplicar_zip(dados, raiz)
    if "requirements.txt" in trocados and (raiz / "requirements.txt").read_bytes() != req_antes:
        _instalar_dependencias(raiz)
    return True, f"atualizado para {remoto[:7]} ({len(trocados)} arquivo(s))"


def reabrir(raiz: Path, argv: list[str]) -> None:
    """Abre uma instância nova (com o código novo) que espera esta terminar."""
    exe = raiz / ".venv" / "Scripts" / "pythonw.exe"
    if not exe.exists() or "--console" in argv:
        exe = Path(sys.executable)
    limpos, pular = [], False
    for a in argv:                     # tira marcas de reinícios anteriores
        if pular:
            pular = False
        elif a == "--aguardar-pid":
            pular = True
        elif a != "--sem-atualizar":
            limpos.append(a)
    cmd = [str(exe), "-m", "olhar", *limpos, "--sem-atualizar", "--aguardar-pid", str(os.getpid())]
    flags = 0x00000200 | 0x00000008 if sys.platform == "win32" else 0   # NEW_PROCESS_GROUP | DETACHED
    subprocess.Popen(cmd, cwd=str(raiz), creationflags=flags, close_fds=True)


def aguardar_processo(pid: int, segundos: float = 30) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)     # SYNCHRONIZE
    if h:
        k.WaitForSingleObject(h, int(segundos * 1000))
        k.CloseHandle(h)
