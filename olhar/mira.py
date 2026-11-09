"""Teste de mira (F8): rodadas que recalibram até o anel acertar o alvo.

Em cada rodada a pessoa olha para alvos em todas as telas e vê onde o anel cai. O erro da
rodada é medido ANTES de aprender com ela (é o erro real); depois o modelo é refeito com
tudo o que já foi medido e a rodada seguinte já usa o resultado. Para quando chega à meta,
quando deixa de melhorar, no limite de rodadas ou no Esc, e fica com a melhor versão medida.

A cabeça se mexe: parte dos alvos pede para mexer a cabeça sem tirar os olhos dele, e uma
correção depende de onde a cabeça está (posição, distância, giro e inclinação).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from .calibracao import JANELA, Cancelado, _Tela
from .modelo_olhar import ModeloOlhar
from .olhos import vetor_olhar

CHEGAR, CHEGAR_MEXENDO, MEDIR = 1.3, 2.2, 1.0
META_PX = 70
MAX_RODADAS = 6
PACIENCIA = 2             # rodadas seguidas sem melhorar antes de parar
ESPERA_RODADA = 2.5       # segundos mostrando o resultado de cada rodada
ESPERA_FINAL = 12.0
MAX_PONTOS = 150          # pontos guardados (calibração + rodadas mais recentes)
SO_OLHOS = "So com os OLHOS: cabeca parada, olhe para o alvo"
NARIZ = "Aponte o NARIZ para o alvo"
INSTRUCOES = (
    "Mova a cabeca para a ESQUERDA e continue olhando o alvo",
    "Mova a cabeca para a DIREITA e continue olhando o alvo",
    "Chegue mais PERTO e continue olhando o alvo",
    "Afaste-se um pouco e continue olhando o alvo",
    "Levante o rosto e continue olhando o alvo",
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


def reajustar(conjunto: list[dict]):
    """Refaz o modelo com todos os pontos medidos e a correção da cabeça sobre o que sobrou."""
    V = np.array([p["v"] for p in conjunto], float)
    A = np.array([p["alvo"] for p in conjunto], float)
    modelo = ModeloOlhar()
    modelo.ajustar(V, A)
    com_cabeca = [p for p in conjunto if p.get("cab") is not None]
    if len(com_cabeca) < 5:
        return modelo, None
    H = np.array([p["cab"] for p in com_cabeca], float)
    R = np.array([np.subtract(p["alvo"], modelo.prever(p["v"])) for p in com_cabeca], float)
    return modelo, ajustar(H, R)[0]


def salvar_mira(arq_calib: Path, modelo, ajuste, pontos: list[dict]) -> None:
    dados = json.loads(arq_calib.read_text(encoding="utf-8"))
    dados["olhar"] = modelo.para_dict()
    dados["ajuste"] = ajuste.para_dict() if ajuste else None
    dados["pontos"] = pontos
    arq_calib.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")


def vetor_cabeca(detector, m) -> np.ndarray:
    return np.concatenate([detector.cabeca, [m.yaw, m.pitch]])


def pontos_rodada(monitores, rodada: int, rng) -> list[tuple]:
    """Centro e cantos de cada tela, um pouco diferentes a cada rodada.

    Testa os dois jeitos de usar: 2 alvos só com os olhos, 2 apontando o nariz e 1 mexendo a
    cabeça sem tirar os olhos dele; quem faz o quê muda a cada rodada.
    """
    roteiro = []
    for n_tela, (mx, my, mw, mh) in enumerate(monitores):
        lugares = [(0.5, 0.5), (0.15, 0.15), (0.85, 0.15), (0.15, 0.85), (0.85, 0.85)]
        for i, (fx, fy) in enumerate(lugares):
            alvo = (int(mx + mw * np.clip(fx + rng.uniform(-0.07, 0.07), 0.06, 0.94)),
                    int(my + mh * np.clip(fy + rng.uniform(-0.07, 0.07), 0.06, 0.94)))
            papel = (i + rodada + n_tela) % 5
            if papel == 0:
                roteiro.append((alvo, INSTRUCOES[(rodada + n_tela) % len(INSTRUCOES)], CHEGAR_MEXENDO))
            elif papel in (1, 2):
                roteiro.append((alvo, NARIZ, CHEGAR_MEXENDO))
            else:                # 1º alvo de cada tela: tempo para virar o rosto até ela
                roteiro.append((alvo, SO_OLHOS, CHEGAR_MEXENDO if i == 0 else CHEGAR))
    return roteiro


def _alvo(img, p, cor=(60, 120, 255)):
    cv2.circle(img, p, 14, cor, 3, cv2.LINE_AA)
    cv2.circle(img, p, 3, cor, -1, cv2.LINE_AA)


def _anel(img, p):
    cv2.circle(img, p, 24, (15, 23, 42), 6, cv2.LINE_AA)
    cv2.circle(img, p, 24, (238, 211, 34), 3, cv2.LINE_AA)


def _medir_ponto(cap, detector, tela, modelo, olho, palp, suavizador, ajuste, alvo, texto, chegar):
    """Mostra o alvo e o anel ao vivo. Devolve (vetor do olhar, cabeça) ou None."""
    vetores, cabecas = [], []
    t0 = time.monotonic()
    anel = None
    tela.ativar(alvo)
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
        tela._centralizado(img, "O anel mostra para onde o programa acha que voce olha  -  Esc encerra",
                           tela.alt - 40, 0.6, (170, 170, 170))
        _alvo(img, alvo)
        if anel is not None:
            _anel(img, anel)
        cv2.imshow(JANELA, img)
        if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
            raise Cancelado
    if len(vetores) < 5:
        return None
    return np.median(vetores, axis=0), np.median(cabecas, axis=0)


def _mostrar_rodada(tela, rodada, erro, melhor, medidos, fim, motivo, detalhe="") -> bool:
    """Resultado da rodada: cada alvo ligado ao ponto em que o anel caiu. True = Esc."""
    tela.ativar(None)
    limite = time.monotonic() + (ESPERA_FINAL if fim else ESPERA_RODADA)
    while True:
        img = np.full((tela.h, tela.w, 3), 24, np.uint8)
        for alvo, ponto in medidos:
            p = (int(np.clip(ponto[0], 0, tela.w - 1)), int(np.clip(ponto[1], 0, tela.h - 1)))
            _alvo(img, alvo)
            cv2.line(img, alvo, p, (120, 230, 120), 2, cv2.LINE_AA)
            cv2.circle(img, p, 6, (120, 230, 120), -1, cv2.LINE_AA)
        tela._centralizado(img, f"Rodada {rodada}: erro {erro:.0f} px   -   melhor ate agora {melhor:.0f} px   -   meta {META_PX} px",
                           60, 1.0)
        tela._centralizado(img, motivo if fim else "Recalibrado. Proxima rodada ja usa o ajuste...", 110, 0.8, (120, 230, 120))
        if detalhe:
            tela._centralizado(img, detalhe, 155, 0.8)
        tela._centralizado(img, "Enter ou Esc: fechar" if fim else "Esc: encerrar e ficar com a melhor", tela.alt - 40, 0.7, (200, 200, 200))
        cv2.imshow(JANELA, img)
        k = cv2.waitKey(30) & 0xFF
        if k in (27, ord("q")):
            return True
        if (fim and k in (13, 10)) or time.monotonic() >= limite:
            return False


def testar(cap, detector, tela_wh, modelo, olho, palp, novo_suavizador, ajuste_atual, pontos_salvos=None):
    """Roda as rodadas. Devolve (modelo, ajuste, pontos): a melhor versão medida e tudo o que
    foi medido (serve de base para o próximo F8). None se nenhuma rodada terminou."""
    w, h = tela_wh
    tela = _Tela(w, h)
    rng = np.random.default_rng()
    conjunto = list(pontos_salvos or [])
    atual_m, atual_a = modelo, ajuste_atual
    melhor = None
    sem_melhora = 0
    try:
        for rodada in range(1, MAX_RODADAS + 1):
            roteiro = pontos_rodada(tela.monitores, rodada, rng)
            medidos = []
            try:
                modos = []
                for alvo, texto, chegar in roteiro:
                    r = _medir_ponto(cap, detector, tela, atual_m, olho, palp, novo_suavizador(), atual_a,
                                     alvo, texto, chegar)
                    if r is not None:
                        medidos.append((alvo, r[0], r[1]))
                        modos.append(texto)
            except Cancelado:
                break
            if len(medidos) < max(4, len(roteiro) // 2):
                if melhor is None:
                    raise RuntimeError("Poucos pontos medidos no teste de mira: confira a câmera e tente de novo.")
                break

            # erro REAL desta rodada: com o modelo em uso, antes de aprender com ela
            pontos = []
            for alvo, v, cab in medidos:
                corr = atual_a.aplicar(cab) if atual_a else (0.0, 0.0)
                p = atual_m.prever(v)
                pontos.append((alvo, (p[0] + corr[0], p[1] + corr[1])))
            erro = float(np.mean([np.hypot(a[0] - p[0], a[1] - p[1]) for a, p in pontos]))
            if melhor is None or erro < melhor[0]:
                melhor, sem_melhora = (erro, atual_m, atual_a), 0
            else:
                sem_melhora += 1
            por_modo = []
            for nome, marca in (("olhos", SO_OLHOS), ("nariz", NARIZ)):
                es = [np.hypot(a[0] - p[0], a[1] - p[1]) for (a, p), t in zip(pontos, modos) if t == marca]
                if es:
                    por_modo.append(f"{nome}: {np.mean(es):.0f} px")
            detalhe = "   -   ".join(por_modo)
            print(f"Teste de mira, rodada {rodada}: {len(medidos)} pontos, erro {erro:.0f} px "
                  f"(melhor {melhor[0]:.0f} px) {detalhe}")

            if erro <= META_PX:
                motivo, fim = "Meta alcancada!", True
            elif sem_melhora >= PACIENCIA:
                motivo, fim = "Parou de melhorar: fiquei com a melhor rodada.", True
            elif rodada == MAX_RODADAS:
                motivo, fim = "Limite de rodadas: fiquei com a melhor.", True
            else:
                motivo, fim = "", False
            conjunto += [{"v": np.asarray(v).tolist(), "alvo": list(a), "cab": np.asarray(c).tolist()} for a, v, c in medidos]
            conjunto = conjunto[-MAX_PONTOS:]
            atual_m, atual_a = reajustar(conjunto)
            if _mostrar_rodada(tela, rodada, erro, melhor[0], pontos, fim, motivo, detalhe) or fim:
                break
    finally:
        tela.fechar()
    if melhor is None:
        return None
    return melhor[1], melhor[2], conjunto
