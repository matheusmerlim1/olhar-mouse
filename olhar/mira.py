"""Teste de mira: olhe para o alvo, veja onde o anel cai e corrija a diferença.

A cabeça se mexe, então a correção não é um número fixo: ela depende de onde a cabeça está
(posição na imagem, distância, giro e inclinação), e a referência acompanha a cabeça. Por isso
parte do teste pede para mexer a cabeça de propósito, mantendo o olhar no alvo.

A correção só é aceita se errar menos em pontos que não foram usados para aprendê-la.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from .calibracao import JANELA, Cancelado, _Tela
from .olhos import vetor_olhar

CHEGAR, CHEGAR_MEXENDO, MEDIR = 1.2, 2.2, 1.0
PONTOS = (
    (0.50, 0.50, "Olhe para o alvo"),
    (0.15, 0.15, "Olhe para o alvo"),
    (0.85, 0.15, "Olhe para o alvo"),
    (0.15, 0.85, "Olhe para o alvo"),
    (0.85, 0.85, "Olhe para o alvo"),
    (0.50, 0.15, "Mova a cabeca para a ESQUERDA e continue olhando o alvo"),
    (0.50, 0.85, "Mova a cabeca para a DIREITA e continue olhando o alvo"),
    (0.15, 0.50, "Chegue mais PERTO e continue olhando o alvo"),
    (0.85, 0.50, "Afaste-se um pouco e continue olhando o alvo"),
    (0.50, 0.50, "Levante o rosto e continue olhando o alvo"),
)
# variação mínima de cada medida da cabeça (x, y, tamanho, giro, inclinação): abaixo disso é
# ruído, e dividir por ela amplificaria o ruído
ESCALA_MINIMA = np.array([0.03, 0.03, 0.02, 0.03, 0.03])
MELHORA_MINIMA = 0.95     # só aceita correção que reduza o erro em pelo menos 5 %


def _termos(z: np.ndarray, com_cabeca: bool) -> np.ndarray:
    uns = np.ones((len(z), 1))
    return np.hstack([uns, z]) if com_cabeca else uns


def _resolver(X: np.ndarray, y: np.ndarray, ridge: float = 1.0) -> np.ndarray:
    reg = ridge * np.eye(X.shape[1])
    reg[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + reg, X.T @ y)


class AjusteCabeca:
    """Correção em pixels em função da cabeça: constante + termo linear limitado."""

    def __init__(self, ref, escala, coef):
        self.ref, self.escala, self.coef = np.asarray(ref, float), np.asarray(escala, float), np.asarray(coef, float)

    def aplicar(self, cabeca) -> tuple[float, float]:
        z = np.clip((np.asarray(cabeca, float) - self.ref) / self.escala, -2.5, 2.5)
        d = np.concatenate([[1.0], z]) @ self.coef
        return float(np.clip(d[0], -500, 500)), float(np.clip(d[1], -500, 500))

    def para_dict(self) -> dict:
        return {"ref": self.ref.tolist(), "escala": self.escala.tolist(), "coef": self.coef.tolist()}

    @classmethod
    def de_dict(cls, d) -> "AjusteCabeca | None":
        return cls(d["ref"], d["escala"], d["coef"]) if d else None


def ajustar(cabecas: np.ndarray, residuos: np.ndarray):
    """Devolve (ajuste ou None, erro sem correção, erro estimado com a correção escolhida)."""
    H, R = np.asarray(cabecas, float), np.asarray(residuos, float)
    base = float(np.linalg.norm(R, axis=1).mean())
    ref = np.median(H, axis=0)
    escala = np.maximum(H.std(axis=0), ESCALA_MINIMA)
    z = (H - ref) / escala
    melhor, erro_melhor = None, base
    for com_cabeca in (False, True):
        X = _termos(z, com_cabeca)
        erros = []
        for i in range(len(z)):               # deixa um ponto de fora por vez
            fica = np.arange(len(z)) != i
            c = _resolver(X[fica], R[fica])
            erros.append(np.linalg.norm(X[i] @ c - R[i]))
        e = float(np.mean(erros))
        if e < erro_melhor and e < base * MELHORA_MINIMA:
            melhor, erro_melhor = com_cabeca, e
    if melhor is None:
        return None, base, base
    c = _resolver(_termos(z, melhor), R)
    if not melhor:                            # só o deslocamento constante
        c = np.vstack([c, np.zeros((H.shape[1], 2))])
    return AjusteCabeca(ref, escala, c), base, erro_melhor


def salvar_ajuste(arq_calib: Path, ajuste: AjusteCabeca) -> None:
    dados = json.loads(arq_calib.read_text(encoding="utf-8"))
    dados["ajuste"] = ajuste.para_dict()
    arq_calib.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def vetor_cabeca(detector, m) -> np.ndarray:
    return np.concatenate([detector.cabeca, [m.yaw, m.pitch]])


def _alvo(img, p, cor=(60, 120, 255)):
    cv2.circle(img, p, 14, cor, 3, cv2.LINE_AA)
    cv2.circle(img, p, 3, cor, -1, cv2.LINE_AA)


def _anel(img, p):
    cv2.circle(img, p, 24, (15, 23, 42), 6, cv2.LINE_AA)
    cv2.circle(img, p, 24, (238, 211, 34), 3, cv2.LINE_AA)


def _medir_ponto(cap, detector, tela, modelo, olho, palp, suavizador, ajuste, alvo, texto, chegar):
    """Mostra o alvo e o anel ao vivo. Devolve (previsto sem correção, cabeça) ou None."""
    vetores, cabecas = [], []
    t0 = time.monotonic()
    anel = None
    while (t := time.monotonic() - t0) < chegar + MEDIR:
        ok, frame = cap.read()
        if ok:
            m = detector.processar(frame)
            if m is not None:
                v = vetor_olhar(m, olho)
                cab = vetor_cabeca(detector, m)
                corr = ajuste.aplicar(cab) if ajuste else (0.0, 0.0)
                a = suavizador(v, modelo, time.monotonic(), corr)
                if a is not None:
                    anel = (int(np.clip(a[0], 0, tela.w - 1)), int(np.clip(a[1], 0, tela.h - 1)))
                piscou = palp.fechamento(m.ear_e, "esq") > 0.5 or palp.fechamento(m.ear_d, "dir") > 0.5
                if t >= chegar and not piscou:
                    vetores.append(v)
                    cabecas.append(cab)
        img = np.full((tela.h, tela.w, 3), 24, np.uint8)
        tela._centralizado(img, texto, 60, 0.9)
        tela._centralizado(img, "O anel mostra para onde o programa acha que voce olha  -  Esc cancela",
                           tela.h - 40, 0.6, (170, 170, 170))
        _alvo(img, alvo)
        if anel is not None:
            _anel(img, anel)
        cv2.imshow(JANELA, img)
        if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
            raise Cancelado
    if len(vetores) < 5:
        return None
    return modelo.prever(np.median(vetores, axis=0)), np.median(cabecas, axis=0)


def _resultado(tela, medidos, atual, novo, antes, depois) -> bool:
    """Mostra alvos e erros. True se a pessoa aceitou a correção nova."""
    while True:
        img = np.full((tela.h, tela.w, 3), 24, np.uint8)
        for alvo, previsto, cab in medidos:
            corr = atual.aplicar(cab) if atual else (0.0, 0.0)
            p = (int(np.clip(previsto[0] + corr[0], 0, tela.w - 1)), int(np.clip(previsto[1] + corr[1], 0, tela.h - 1)))
            _alvo(img, alvo)
            cv2.line(img, alvo, p, (120, 120, 120), 1, cv2.LINE_AA)
            cv2.circle(img, p, 5, (120, 120, 120), -1, cv2.LINE_AA)
            if novo:
                n = novo.aplicar(cab)
                q = (int(np.clip(previsto[0] + n[0], 0, tela.w - 1)), int(np.clip(previsto[1] + n[1], 0, tela.h - 1)))
                cv2.line(img, alvo, q, (120, 230, 120), 2, cv2.LINE_AA)
                cv2.circle(img, q, 6, (120, 230, 120), -1, cv2.LINE_AA)
        if novo:
            tela._centralizado(img, f"Erro atual: {antes:.0f} px   -   com a correcao: {depois:.0f} px", 60, 1.0)
            pe = "Enter: aplicar a correcao   -   Esc: descartar   (cinza = agora, verde = corrigido)"
        else:
            tela._centralizado(img, f"Erro atual: {antes:.0f} px   -   nenhuma correcao melhorou a mira", 60, 1.0)
            pe = "Enter ou Esc: fechar   -   tente recalibrar (F10)"
        tela._centralizado(img, pe, tela.h - 40, 0.7, (200, 200, 200))
        cv2.imshow(JANELA, img)
        k = cv2.waitKey(30) & 0xFF
        if k in (13, 10):
            return novo is not None
        if k in (27, ord("q")):
            return False


def testar(cap, detector, tela_wh, modelo, olho, palp, suavizador, ajuste_atual):
    """Roda o teste. Devolve a correção aceita, ou None (mantém a atual)."""
    w, h = tela_wh
    tela = _Tela(w, h)
    try:
        medidos = []
        for fx, fy, texto in PONTOS:
            alvo = (int(fx * w), int(fy * h))
            mexendo = "Olhe para o alvo" != texto
            r = _medir_ponto(cap, detector, tela, modelo, olho, palp, suavizador, ajuste_atual, alvo, texto,
                             CHEGAR_MEXENDO if mexendo else CHEGAR)
            if r is not None:
                medidos.append((alvo, r[0], r[1]))
        if len(medidos) < 5:
            raise RuntimeError("Poucos pontos medidos no teste de mira: confira a câmera e tente de novo.")
        cabecas = np.array([c for _, _, c in medidos])
        residuos = np.array([np.subtract(a, p) for a, p, _ in medidos], float)
        novo, base, depois = ajustar(cabecas, residuos)
        corr = np.array([ajuste_atual.aplicar(c) if ajuste_atual else (0.0, 0.0) for c in cabecas])
        antes = float(np.linalg.norm(residuos - corr, axis=1).mean())
        print(f"Teste de mira: {len(medidos)} pontos, erro atual {antes:.0f} px, sem correção {base:.0f} px, "
              f"com a nova {depois:.0f} px, correção encontrada: {novo is not None}")
        return novo if _resultado(tela, medidos, ajuste_atual, novo, antes, depois) else None
    finally:
        tela.fechar()
