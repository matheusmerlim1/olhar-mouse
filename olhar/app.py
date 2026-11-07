"""Laço principal: câmera → olhos → cursor e cliques."""
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
from .filtro import OneEuro2D
from .gestos import ConfigGestos, Gestos, Palpebras
from .modelo_olhar import carregar, salvar
from .olhos import OLHO, vetor_olhar

RAIZ = Path(__file__).resolve().parent.parent
PADRAO = {
    "camera": 0,
    "olho": "ambos",
    "oculos": False,
    "realce_contraste": False,
    "mostrar_camera": True,
    "som": True,
    "pontos_calibracao": 13,
    "gestos": {"lento_min": 0.30, "lento_max": 1.50, "janela": 1.50},
    "suavizacao": {"min_cutoff": 0.6, "beta": 0.004},
}
JANELA = "olhar-mouse (Esc sai, P pausa, C calibra)"


def ler_config(caminho: Path) -> dict:
    cfg = json.loads(json.dumps(PADRAO))
    if caminho.exists():
        dado = json.loads(caminho.read_text(encoding="utf-8"))
        for k, v in dado.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            elif not k.startswith("_"):
                cfg[k] = v
    if cfg["olho"] not in ("ambos", "esquerdo", "direito"):
        raise SystemExit('config.json: "olho" deve ser "ambos", "esquerdo" ou "direito".')
    return cfg


def montar_gestos(cfg: dict) -> tuple[ConfigGestos, int]:
    g = ConfigGestos(**{k: v for k, v in cfg["gestos"].items() if k in ConfigGestos.__dataclass_fields__})
    g.um_olho = cfg["olho"] != "ambos"
    mediana = 3
    if cfg["oculos"]:
        # óculos: reflexo na lente dá picos isolados no EAR → mais filtragem
        g.estabilidade = max(g.estabilidade, 0.09)
        mediana = 5
    return g, mediana


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


def executar(cfg: dict, arq_calib: Path, forcar_calibracao: bool = False) -> None:
    tela = mouse.tamanho_tela()
    cap = abrir_camera(cfg["camera"])
    detector = Detector(RAIZ / "modelos" / "face_landmarker.task", realce=cfg["realce_contraste"])
    olho = cfg["olho"]

    def fazer_calibracao():
        print("Calibrando…")
        modelo, palp = calibrar(cap, detector, tela, olho, cfg["pontos_calibracao"])
        salvar(arq_calib, modelo, palp, {"tela": list(tela), "olho": olho, "oculos": cfg["oculos"],
                                         "camera": str(cfg["camera"])})
        print(f"Calibração salva em {arq_calib} (erro médio {modelo.erro_px:.0f} px).")
        return modelo, palp

    modelo = calib_palp = None
    if arq_calib.exists() and not forcar_calibracao:
        modelo, calib_palp, extra = carregar(arq_calib)
        # a calibração vale para uma câmera numa posição: trocar a câmera
        # (webcam ↔ celular) exige calibrar de novo
        if (extra.get("tela") != list(tela) or extra.get("olho") != olho
                or extra.get("oculos") != cfg["oculos"] or extra.get("camera") != str(cfg["camera"])):
            print("A tela, a câmera, o olho ou o modo óculos mudou desde a última calibração: calibrando de novo.")
            modelo = None
    if modelo is None:
        modelo, calib_palp = fazer_calibracao()

    cfg_g, mediana = montar_gestos(cfg)

    def novo_estado():
        return (Palpebras(calib_palp, janela_mediana=mediana), Gestos(cfg_g),
                OneEuro2D(**cfg["suavizacao"]), Congelador())

    palp, gestos, filtro, cong = novo_estado()
    pausado = False
    sem_rosto_desde = None
    teclas_antes = {mouse.VK_F9: False, mouse.VK_F10: False}
    msg, msg_t, evento_visto = "", 0.0, ""
    print("Rodando. F9 pausa/retoma, F10 recalibra, Esc (na janela da câmera) sai.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            t = time.monotonic()
            m = detector.processar(frame)

            # --- teclas globais (funcionam com qualquer janela em foco)
            recal = False
            for vk in teclas_antes:
                agora = mouse.tecla_apertada(vk)
                if agora and not teclas_antes[vk]:
                    if vk == mouse.VK_F9:
                        pausado = not pausado
                        if cfg["som"]:
                            bipe(500 if pausado else 800, 90)
                    else:
                        recal = True
                teclas_antes[vk] = agora

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

                if not pausado:
                    if congelado is None:
                        alvo = modelo.prever(vetor_olhar(m, olho))
                        x, y = filtro(float(alvo[0]), float(alvo[1]), t)
                        x = int(np.clip(x, 0, tela[0] - 1))
                        y = int(np.clip(y, 0, tela[1] - 1))
                        cong.registrar(t, x, y)
                        mouse.mover(x, y)
                    if clique:
                        px, py = congelado or (cong.hist[-1][1:] if cong.hist else (None, None))
                        mouse.clicar(clique, px, py)
                        msg, msg_t = f"CLIQUE {clique.upper()}", t
                        if cfg["som"]:
                            bipe(1200 if clique == "esquerdo" else 700, 60)
                if gestos.ultimo_evento != evento_visto:
                    evento_visto = gestos.ultimo_evento
                    if not (clique and msg_t == t):
                        msg, msg_t = evento_visto, t
                status = "PAUSADO (F9)" if pausado else ("parado (piscando)" if congelado else "seguindo o olhar")

            ultimo = msg if t - msg_t < 2.5 else ""
            if cfg["mostrar_camera"]:
                cv2.imshow(JANELA, desenhar_previa(frame, m, palp, status, olho, sem_acento(ultimo)))
                k = cv2.waitKey(1) & 0xFF
                if k in (27, ord("q")):
                    break
                if k == ord("p"):
                    pausado = not pausado
                if k == ord("c"):
                    recal = True
            if recal:
                try:
                    modelo, calib_palp = fazer_calibracao()
                except Cancelado:
                    print("Calibração cancelada; mantendo a anterior.")
                palp, gestos, filtro, cong = novo_estado()
                msg, evento_visto = "", ""
    finally:
        cap.release()
        detector.fechar()
        cv2.destroyAllWindows()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Controla o mouse com o olhar e cliques por piscada.")
    ap.add_argument("--config", default=str(RAIZ / "config.json"))
    ap.add_argument("--calibrar", action="store_true", help="refaz a calibração antes de começar")
    ap.add_argument("--camera", help="sobrepõe a câmera do config (número ou URL do celular)")
    args = ap.parse_args(argv)

    cfg = ler_config(Path(args.config))
    if args.camera is not None:
        cfg["camera"] = args.camera
    try:
        executar(cfg, RAIZ / "dados" / "calibracao.json", args.calibrar)
    except Cancelado:
        print("Calibração cancelada.")
    except RuntimeError as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
