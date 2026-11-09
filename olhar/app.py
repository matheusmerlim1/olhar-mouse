"""Laço principal: câmera → olhos → cursor e cliques.

Roda sem janela, com um ícone na bandeja (como o ditado por voz do projeto 24).
Janelas só na abertura (QR code do celular, calibração) ou quando pedidas.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from . import mouse
from .calibracao import Cancelado, bipe, calibrar
from .camera import Detector, abrir_camera
from .celular import CameraCelular, aguardar_celular
from .filtro import ESTABILIDADE, Estabilizador, MedianaVetor, OneEuro2D
from .gestos import ConfigGestos, Gestos, Palpebras
from .mira import AjusteCabeca, salvar_ajuste, testar as testar_mira, vetor_cabeca
from .modelo_olhar import carregar, salvar
from .olhos import OLHO, vetor_olhar
from .ponteiro import PonteiroOlhar
from .zoom import Zoom

RAIZ = Path(__file__).resolve().parent.parent
PADRAO = {
    "camera": 0,
    "olho": "ambos",
    "oculos": False,
    "realce_contraste": False,
    "mostrar_camera": False,
    "perguntar_camera": True,
    "atualizar_automaticamente": True,
    "som": True,
    "pontos_calibracao": 13,
    "gestos": {"lento_min": 0.30, "lento_max": 1.50, "janela": 1.50},
    "ponteiro_separado": True, # anel próprio do olhar, sem tocar no cursor do Windows
    "zoom": "auto",            # auto / off
    "estabilidade": "media",   # baixa / media / alta (menu "Estabilidade do cursor")
}
JANELA = "olhar-mouse - camera (Esc fecha, P pausa, C calibra)"
JANELA_QR = "Celular - olhar-mouse"


ESCOLHAS_DO_MENU = ("camera", "olho", "oculos", "som", "mostrar_camera", "realce_contraste", "perguntar_camera",
                    "estabilidade", "ponteiro_separado", "zoom")


def ler_config(caminho: Path, pessoal: Path | None = None) -> dict:
    """Padrões do programa ← config.json (ajustes finos) ← dados/config.json (escolhas do menu).

    As escolhas feitas pelo menu ficam em dados/, fora do git: atualizar o
    programa não apaga as preferências da pessoa e o repositório não muda a
    cada clique no menu.
    """
    cfg = json.loads(json.dumps(PADRAO))
    for arq in (caminho, pessoal):
        if arq is None or not arq.exists():
            continue
        dado = json.loads(arq.read_text(encoding="utf-8"))
        for k, v in dado.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            elif not k.startswith("_"):
                cfg[k] = v
    if cfg["olho"] not in ("ambos", "esquerdo", "direito"):
        raise SystemExit('config.json: "olho" deve ser "ambos", "esquerdo" ou "direito".')
    return cfg


def salvar_config(cfg: dict, pessoal: Path) -> None:
    """Grava as escolhas do menu em dados/config.json."""
    pessoal.parent.mkdir(parents=True, exist_ok=True)
    dado = {k: cfg[k] for k in ESCOLHAS_DO_MENU if k in cfg}
    pessoal.write_text(json.dumps(dado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def montar_gestos(cfg: dict) -> tuple[ConfigGestos, int]:
    g = ConfigGestos(**{k: v for k, v in cfg["gestos"].items() if k in ConfigGestos.__dataclass_fields__})
    g.um_olho = cfg["olho"] != "ambos"
    mediana = 3
    if cfg["oculos"]:
        # óculos: reflexo na lente dá picos isolados no EAR → mais filtragem
        g.estabilidade = max(g.estabilidade, 0.09)
        mediana = 5
    return g, mediana


class Suavizador:
    """Do vetor do olhar ao ponto do cursor, sem tremer:
    mediana dos últimos quadros → regressão → filtro One Euro → zona de repouso."""

    def __init__(self, nivel: str):
        p = ESTABILIDADE.get(nivel, ESTABILIDADE["media"])
        self.mediana = MedianaVetor(p["mediana"])
        self.euro = OneEuro2D(min_cutoff=p["min_cutoff"], beta=p["beta"])
        self.repouso = Estabilizador(raio=p["raio"])

    def __call__(self, vetor, modelo, t: float, correcao=(0.0, 0.0)) -> tuple[float, float] | None:
        """Ponto do cursor, ou None quando o olhar cedeu ao mouse físico."""
        alvo = modelo.prever(self.mediana(vetor))
        x, y = self.euro(float(alvo[0]) + correcao[0], float(alvo[1]) + correcao[1], t)
        return self.repouso(x, y, t)

    def ceder(self):
        self.repouso.ceder()

    @property
    def cedido(self) -> bool:
        return self.repouso.cedido


class Congelador:
    """Segura o cursor enquanto os olhos estão fechando/fechados.

    Fechar o olho puxa a íris estimada para baixo, então o cursor fica na
    posição de ~0,15 s ANTES de a piscada começar — é ali que o clique cai.
    Depois de reabrir, espera um pouco antes de voltar a seguir o olhar.
    """

    def __init__(self, recuo: float = 0.15, espera: float = 0.20):
        self.recuo, self.espera = recuo, espera
        self.hist: deque = deque(maxlen=90)
        self.ponto = None
        self._aberto_desde = None

    def registrar(self, t, x, y):
        self.hist.append((t, x, y))

    def atualizar(self, t: float, fechando: bool) -> tuple[int, int] | None:
        """Devolve o ponto congelado, ou None se o cursor pode se mover."""
        if fechando:
            self._aberto_desde = None
            if self.ponto is None and self.hist:
                alvo = t - self.recuo
                antes = [h for h in self.hist if h[0] <= alvo] or [self.hist[0]]
                self.ponto = (antes[-1][1], antes[-1][2])
            return self.ponto
        if self.ponto is not None:
            if self._aberto_desde is None:
                self._aberto_desde = t
            if t - self._aberto_desde < self.espera:
                return self.ponto
            self.ponto = None
        return None


def desenhar_previa(frame, m, palp: Palpebras, status: str, olho: str, ultimo: str):
    img = frame.copy()
    if m is not None:
        for lado, cor in (("esquerdo", (80, 220, 80)), ("direito", (80, 180, 255))):
            if olho != "ambos" and lado != olho:
                continue
            cont = m.pontos[list(OLHO[lado]["contorno"])].astype(np.int32)
            cv2.polylines(img, [cont], True, cor, 1, cv2.LINE_AA)
            c = m.pontos[OLHO[lado]["iris"][0]].astype(int)
            cv2.circle(img, tuple(c), 2, (0, 0, 255), -1)
    img = cv2.flip(img, 1)  # espelho: mais natural para quem se olha
    h, w = img.shape[:2]
    # na imagem espelhada o olho esquerdo do usuário fica à esquerda
    for i, (lado, nome) in enumerate((("esq", "olho esq"), ("dir", "olho dir"))):
        nivel = float(np.clip(palp.nivel[lado], 0, 1))
        x0 = 10 + i * 130
        cv2.rectangle(img, (x0, h - 26), (x0 + 110, h - 12), (60, 60, 60), -1)
        cv2.rectangle(img, (x0, h - 26), (x0 + int(110 * nivel), h - 12),
                      (0, 0, 255) if palp.fechado[lado] else (0, 200, 0), -1)
        cv2.putText(img, nome, (x0, h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, status, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    if ultimo:
        cv2.putText(img, ultimo, (10, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    return img


def sem_acento(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


class _Console:
    """Substitui a bandeja no modo --console (mensagens no terminal)."""
    console = True

    def definir_estado(self, estado):
        pass

    def notificar(self, titulo, msg):
        print(f"[{titulo}] {msg}")

    def fechar(self):
        pass


def _fechar_janela(nome: str) -> None:
    try:
        cv2.destroyWindow(nome)
    except cv2.error:
        pass


def executar(cfg: dict, arq_calib: Path, ctl, ui, forcar_calibracao: bool = False) -> None:
    """Abre a câmera, calibra se preciso e segue o olhar até Sair ou mudar a config."""
    tela = mouse.tamanho_tela()
    console = getattr(ui, "console", False)

    def parar():
        return ctl.sair or ctl.reiniciar or ctl.escolher

    modo = str(cfg["camera"]).strip().lower()
    celular = modo in ("celular", "usb")
    adb = None
    if modo == "usb":
        from .usb import AdbUsb, achar_adb, baixar_adb
        caminho = achar_adb(RAIZ)
        if caminho is None:
            ui.notificar("Baixando o ADB", "Ferramenta oficial do Android para usar o celular pelo cabo (~7 MB).")
            caminho = baixar_adb(RAIZ)
        adb = AdbUsb(caminho)
        print(f"ADB: {caminho}")

    def esperar_celular() -> bool:
        if adb is not None:
            from .usb import aguardar_usb
            return aguardar_usb(cap, adb, JANELA_QR, parar)
        return aguardar_celular(cap, tela, JANELA_QR, False, parar)

    if celular:
        cap = CameraCelular(RAIZ / "dados", porta=8470 if adb else 8443, usb=adb is not None)
        print(f"Câmera do celular: {cap.url}")
        ui.definir_estado("celular")
        try:
            if not esperar_celular():
                cap.release()
                return
        except BaseException:
            cap.release()
            raise
    else:
        ui.definir_estado("carregando")
        cap = abrir_camera(cfg["camera"])
    zoom = Zoom(ligado=cfg.get("zoom", "auto") != "off")
    detector = Detector(RAIZ / "modelos" / "face_landmarker.task", realce=cfg["realce_contraste"],
                        zoom=zoom, remoto=cap if celular else None)
    ponteiro = PonteiroOlhar()
    olho = cfg["olho"]

    def fazer_calibracao():
        ponteiro.esconder()
        ui.definir_estado("calibrando")
        modelo, palp = calibrar(cap, detector, tela, olho, cfg["pontos_calibracao"])
        salvar(arq_calib, modelo, palp, {"tela": list(tela), "olho": olho, "oculos": cfg["oculos"],
                                         "camera": str(cfg["camera"])})
        print(f"Calibração salva (erro médio {modelo.erro_px:.0f} px).")
        print(f"Modelo: {modelo.forma}, ridge {modelo.ridge}, desvio u/v/yaw/pitch {modelo.desvio.round(4).tolist()}, "
              f"horizontal {modelo.coef[:, 0].round(0).tolist()}, vertical {modelo.coef[:, 1].round(0).tolist()}")
        return modelo, palp

    try:
        modelo = calib_palp = ajuste = None
        if arq_calib.exists() and not forcar_calibracao:
            modelo, calib_palp, extra = carregar(arq_calib)
            ajuste = AjusteCabeca.de_dict(extra.get("ajuste"))
            # a calibração vale para uma câmera numa posição: trocar a câmera
            # (webcam ↔ celular), a tela, o olho ou os óculos exige calibrar de novo
            if (extra.get("tela") != list(tela) or extra.get("olho") != olho
                    or extra.get("oculos") != cfg["oculos"] or extra.get("camera") != str(cfg["camera"])):
                print("Tela, câmera, olho ou óculos mudou desde a última calibração: calibrando de novo.")
                modelo = None
        if modelo is None:
            modelo, calib_palp = fazer_calibracao()
            ajuste = None

        cfg_g, mediana = montar_gestos(cfg)

        def novo_estado():
            return (Palpebras(calib_palp, janela_mediana=mediana), Gestos(cfg_g),
                    Suavizador(cfg.get("estabilidade", "media")), Congelador())

        palp, gestos, filtro, cong = novo_estado()
        sem_rosto_desde = None
        fora_desde = None
        colocado = None      # último ponto em que o OLHAR pôs o cursor
        fisico_t = None
        teclas_antes = {mouse.VK_F8: False, mouse.VK_F9: False, mouse.VK_F10: False}
        msg, msg_t, evento_visto = "", 0.0, ""
        pausa_antes = ctl.pausado
        previa_aberta = False
        ui.notificar("Olhar-mouse pronto",
                     "O cursor segue o seu olhar. F9 pausa, F10 recalibra. Menu no ícone do olho, perto do relógio.")

        while not parar():
            ok, frame = cap.read()
            if not ok:
                if celular and not cap.conectado(3.0):
                    # celular desconectou (tela apagou, Wi-Fi caiu…): QR numa janela comum
                    ponteiro.esconder()
                    ui.definir_estado("celular")
                    ui.notificar("Celular desconectado",
                                 "Ligue o cabo de novo." if adb else "Abra de novo a página no celular (o QR code está na tela).")
                    if previa_aberta:
                        _fechar_janela(JANELA)
                        previa_aberta = False
                    try:
                        esperar_celular()
                    except Cancelado:  # Esc só esconde o QR; continua esperando o celular
                        while not parar() and not cap.conectado(1.0):
                            time.sleep(0.2)
                    palp, gestos, filtro, cong = novo_estado()
                time.sleep(0.01)
                continue
            t = time.monotonic()
            m = detector.processar(frame)

            # --- teclas globais (funcionam com qualquer janela em foco)
            for vk in teclas_antes:
                agora = mouse.tecla_apertada(vk)
                if agora and not teclas_antes[vk]:
                    if vk == mouse.VK_F9:
                        ctl.pausado = not ctl.pausado
                    elif vk == mouse.VK_F8:
                        ctl.testar = True
                    else:
                        ctl.recalibrar = True
                teclas_antes[vk] = agora
            if ctl.pausado != pausa_antes:
                pausa_antes = ctl.pausado
                if cfg["som"]:
                    bipe(500 if ctl.pausado else 800, 90)

            congelado = None
            fora = False
            if m is None:
                sem_rosto_desde = sem_rosto_desde or t
                gestos.atualizar(t, False, False)
                status = "SEM ROSTO"
            else:
                sem_rosto_desde = None
                fe, fd = palp.atualizar(m.ear_e, m.ear_d)
                if olho == "esquerdo":
                    fe = fd = palp.fechado["esq"]
                elif olho == "direito":
                    fe = fd = palp.fechado["dir"]
                clique = gestos.atualizar(t, fe, fd)
                congelado = cong.atualizar(t, gestos.fechando)

                vetor = vetor_olhar(m, olho)
                fora = modelo.fora(vetor)      # cabeça virada / olhando para fora da tela
                fora_desde = (fora_desde or t) if fora else None

                # --- segundo mouse: se o cursor não está onde o olhar o deixou, foi o mouse
                # físico. O olhar cede e não puxa de volta (só retoma num olhar novo).
                # (no modo de ponteiro separado o olhar nunca toca no cursor: não há disputa)
                separado = bool(cfg.get("ponteiro_separado", True))
                real = mouse.posicao()
                if not separado and colocado is not None and abs(real[0] - colocado[0]) + abs(real[1] - colocado[1]) > 6:
                    filtro.ceder()
                    colocado = None
                    fisico_t = t

                if not ctl.pausado:
                    if congelado is None and not fora:
                        # a correção do teste de mira depende de onde a cabeça está agora
                        correcao = ajuste.aplicar(vetor_cabeca(detector, m)) if ajuste else (0.0, 0.0)
                        alvo = filtro(vetor, modelo, t, correcao)
                        if alvo is not None:
                            x = int(np.clip(alvo[0], 0, tela[0] - 1))
                            y = int(np.clip(alvo[1], 0, tela[1] - 1))
                            cong.registrar(t, x, y)
                            # só mexe no cursor quando o ponto MUDA: parado, o mouse físico fica livre
                            if (x, y) != colocado:
                                if not separado:
                                    mouse.mover(x, y)
                                colocado = (x, y)
                    # com o botão do mouse de verdade apertado (arrastando), a piscada não clica
                    if clique and not fora and not mouse.botao_fisico_apertado() and (colocado or not separado):
                        if separado:         # clica no anel e devolve o cursor para onde estava
                            ponteiro.marcar_clique()
                            mouse.clicar_em(clique, *colocado)
                        else:                # clica onde o cursor está
                            mouse.clicar(clique)
                        msg, msg_t = f"CLIQUE {clique.upper()}", t
                        if cfg["som"]:
                            bipe(1200 if clique == "esquerdo" else 700, 60)
                if gestos.ultimo_evento != evento_visto:
                    evento_visto = gestos.ultimo_evento
                    if not (clique and msg_t == t):
                        msg, msg_t = evento_visto, t
                status = ("PAUSADO (F9)" if ctl.pausado else "olhar fora da area calibrada" if fora
                          else "mouse fisico: olhe outro ponto" if filtro.cedido
                          else "parado (piscando)" if congelado else "seguindo o olhar")

            perdeu = (sem_rosto_desde and t - sem_rosto_desde > 1.0) or (fora_desde and t - fora_desde > 1.0)
            if cfg.get("ponteiro_separado", True) and colocado and not ctl.pausado and not perdeu:
                ponteiro.mostrar(*colocado)
            else:
                ponteiro.esconder()

            if ctl.pausado:
                ui.definir_estado("pausado")
            elif sem_rosto_desde and t - sem_rosto_desde > 1.0:
                ui.definir_estado("sem_rosto")
            elif m is not None and fora_desde and t - fora_desde > 1.0:
                ui.definir_estado("fora")
            elif m is not None and filtro.cedido:
                ui.definir_estado("cedido")
            elif m is not None:
                ui.definir_estado("seguindo")

            # --- janela da câmera: só quando pedida pelo menu
            if ctl.mostrar_camera:
                ultimo = msg if t - msg_t < 2.5 else ""
                cv2.imshow(JANELA, desenhar_previa(frame, m, palp, status, olho, sem_acento(ultimo)))
                previa_aberta = True
                k = cv2.waitKey(1) & 0xFF
                fechou = cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1
                if k in (27, ord("q")) or fechou:
                    if console and k in (27, ord("q")):
                        ctl.sair = True
                    ctl.mostrar_camera = False
                elif k == ord("p"):
                    ctl.pausado = not ctl.pausado
                elif k == ord("c"):
                    ctl.recalibrar = True
            if previa_aberta and not ctl.mostrar_camera:
                _fechar_janela(JANELA)
                previa_aberta = False

            if ctl.refiltrar:          # mudou a estabilidade no menu
                ctl.refiltrar = False
                zoom.ligado = cfg.get("zoom", "auto") != "off"
                filtro = Suavizador(cfg.get("estabilidade", "media"))

            if ctl.testar:
                ctl.testar = False
                ponteiro.esconder()
                if previa_aberta:
                    _fechar_janela(JANELA)
                    previa_aberta = False
                ui.definir_estado("calibrando")
                try:
                    novo = testar_mira(cap, detector, tela, modelo, olho, calib_palp,
                                       Suavizador(cfg.get("estabilidade", "media")), ajuste)
                    if novo is not None:
                        ajuste = novo
                        salvar_ajuste(arq_calib, ajuste)
                        ui.notificar("Mira ajustada", "A correção foi salva e acompanha a posição da cabeça.")
                except Cancelado:
                    pass
                except RuntimeError as e:
                    ui.notificar("Teste de mira", str(e))
                palp, gestos, filtro, cong = novo_estado()
                msg, evento_visto = "", ""

            if ctl.recalibrar:
                ctl.recalibrar = False
                if previa_aberta:
                    _fechar_janela(JANELA)
                    previa_aberta = False
                try:
                    modelo, calib_palp = fazer_calibracao()
                    ajuste = None
                except Cancelado:
                    ui.notificar("Calibração cancelada", "Mantive a calibração anterior.")
                palp, gestos, filtro, cong = novo_estado()
                msg, evento_visto = "", ""
    finally:
        ponteiro.fechar()
        cap.release()
        detector.fechar()
        if adb is not None:
            adb.desfazer(cap.porta)
        cv2.destroyAllWindows()


def _uma_instancia() -> bool:
    """Impede duas cópias abertas (as duas moveriam o mouse ao mesmo tempo)."""
    if sys.platform != "win32":
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    _uma_instancia.mutex = k32.CreateMutexW(None, False, "Local\\OlharMouse")
    if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            None, "O Olhar-mouse já está aberto: procure o ícone do olho perto do relógio.", "Olhar-mouse", 0x40)
        return False
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Controla o mouse com o olhar e cliques por piscada.")
    ap.add_argument("--config", default=str(RAIZ / "config.json"))
    ap.add_argument("--calibrar", action="store_true", help="refaz a calibração antes de começar")
    ap.add_argument("--camera", help='troca a câmera e grava no config: número, "celular" ou URL')
    ap.add_argument("--console", action="store_true", help="sem ícone na bandeja, mensagens no terminal")
    ap.add_argument("--pasta", help=argparse.SUPPRESS)  # só identifica o atalho de iniciar com o Windows
    ap.add_argument("--sem-atualizar", action="store_true", help="não procura versão nova ao abrir")
    ap.add_argument("--aguardar-pid", type=int, help=argparse.SUPPRESS)  # reinício após atualizar
    argv_original = list(sys.argv[1:] if argv is None else argv)
    args = ap.parse_args(argv)

    (RAIZ / "dados").mkdir(exist_ok=True)
    if not args.console or sys.stdout is None:
        # sem terminal (pythonw): tudo vai para o registro
        log = open(RAIZ / "dados" / "olhar.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
        print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} olhar-mouse iniciado")
    from . import atualizador
    if args.aguardar_pid:
        atualizador.aguardar_processo(args.aguardar_pid)   # a versão antiga terminando de sair
    if not _uma_instancia():
        return

    arq_cfg = RAIZ / "dados" / "config.json"   # escolhas do menu (fora do git)
    cfg = ler_config(Path(args.config), arq_cfg)
    print(f"Versão {atualizador.versao_curta(RAIZ)}")

    # como o ditado (projeto 24), mas ANTES de rodar: procura versão nova no GitHub e,
    # se houver, atualiza e reabre já com o código novo. Sem internet, segue normalmente.
    if not args.sem_atualizar and cfg.get("atualizar_automaticamente", True):
        atualizou, msg = atualizador.procurar_e_aplicar(RAIZ)
        print(f"Atualização: {msg}")
        if atualizou:
            atualizador.reabrir(RAIZ, argv_original)
            return

    # primeira abertura depois de uma atualização: card com o que mudou (uma vez só)
    from . import novidades
    pendente = novidades.pendentes(RAIZ)
    if pendente:
        try:
            novidades.mostrar_card(pendente)
        except Exception as e:
            print(f"card de novidades: {e!r}")
    if args.camera is not None:
        if args.camera.strip().lower() == "computador":
            # primeira câmera real do Windows (as virtuais, como a do OBS, não contam)
            from .camera import listar_cameras
            from .escolha import camera_do_computador
            escolhida = camera_do_computador(listar_cameras(), cfg["camera"])
            if escolhida is None:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None, "Nenhuma câmera encontrada no computador.\nUse o celular: iniciar-usb.bat (cabo) "
                          "ou iniciar-celular.bat (QR code).", "Olhar-mouse", 0x30)
                return
            cfg["camera"] = escolhida
        else:
            cfg["camera"] = int(args.camera) if args.camera.strip().isdigit() else args.camera
        salvar_config(cfg, arq_cfg)

    from .bandeja import Bandeja, Controle
    ctl = Controle()
    ctl.mostrar_camera = bool(cfg["mostrar_camera"]) or args.console
    ui = _Console() if args.console else Bandeja(RAIZ, cfg, ctl, lambda c: salvar_config(c, arq_cfg))
    forcar = args.calibrar
    def perguntar() -> bool:
        """Tela das três opções: computador, QR code (Wi-Fi) ou cabo USB."""
        from .camera import listar_cameras
        from .escolha import escolher_camera
        try:
            cfg["camera"] = escolher_camera(listar_cameras(), cfg["camera"])
        except Cancelado:
            print("Saiu na escolha da câmera; fica parado na bandeja.")
            return False
        salvar_config(cfg, arq_cfg)
        print(f"Câmera escolhida: {cfg['camera']}")
        return True

    try:
        # Pergunta ao abrir, a não ser que o atalho já diga qual (--camera) ou
        # que seja a abertura automática com o Windows (usa a última).
        if args.camera is None and args.pasta is None and cfg.get("perguntar_camera", True):
            ui.definir_estado("parado")
            ctl.parado = not perguntar()
        avisou_parado = False
        while not ctl.sair:
            # Como o ditado: sair da escolha ou cancelar a calibração NÃO fecha o
            # programa — ele fica parado na bandeja esperando a pessoa escolher.
            if ctl.parado:
                ui.definir_estado("parado")
                if not avisou_parado:
                    ui.notificar("Olhar-mouse parado",
                                 "Clique duas vezes no ícone do olho (perto do relógio) para escolher a câmera.")
                    avisou_parado = True
                while not (ctl.sair or ctl.escolher or ctl.reiniciar):
                    time.sleep(0.2)
                if ctl.sair:
                    break
                if ctl.escolher:
                    ctl.escolher = False
                    if not perguntar():
                        continue
                ctl.parado = False
            ctl.reiniciar = False
            try:
                executar(cfg, RAIZ / "dados" / "calibracao.json", ctl, ui, forcar)
            except Cancelado:
                print("Cancelado pelo usuário; fica parado na bandeja.")
                ctl.parado = True
                continue
            except Exception as e:
                import traceback
                traceback.print_exc()
                ui.notificar("Olhar-mouse: erro", str(e) or e.__class__.__name__)
                ctl.parado = True
                continue
            forcar = False
            if ctl.escolher:           # "Trocar de câmera…" no menu
                ctl.parado = True
            elif not ctl.reiniciar:    # saiu pelo menu
                break
    finally:
        ui.fechar()
        if ctl.reabrir:            # atualizou pelo menu do ícone
            atualizador.reabrir(RAIZ, argv_original)


if __name__ == "__main__":
    main()
