"""Geometria dos olhos a partir dos 478 pontos do Face Landmarker do MediaPipe.

Tudo aqui é numpy puro: recebe os pontos já em pixels (N x 2) e devolve números.
Assim dá para testar sem câmera.

"Esquerdo" e "direito" são do ponto de vista do USUÁRIO (o olho esquerdo dele
aparece do lado direito da imagem da câmera, que não é espelhada).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Índices da malha facial do MediaPipe (com refinamento de íris, 478 pontos).
# Ordem para o EAR: canto externo, pálpebra sup. 1, sup. 2, canto interno, inf. 2, inf. 1
OLHO = {
    "direito": {
        "ear": (33, 160, 158, 133, 153, 144),
        "externo": 33,
        "interno": 133,
        "superior": 159,
        "inferior": 145,
        "iris": (468, 469, 470, 471, 472),  # centro + 4 bordas
        "contorno": (33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7),
    },
    "esquerdo": {
        "ear": (263, 387, 385, 362, 380, 373),
        "externo": 263,
        "interno": 362,
        "superior": 386,
        "inferior": 374,
        "iris": (473, 474, 475, 476, 477),
        "contorno": (263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249),
    },
}
NARIZ = 1          # ponta do nariz
TESTA = 10         # meio da testa
QUEIXO = 152


def ear(pts: np.ndarray, lado: str) -> float:
    """Eye Aspect Ratio: altura média da abertura / largura do olho.

    Olho aberto fica em torno de 0,25–0,35; fechado cai para perto de 0,05–0,12.
    O valor exato varia de pessoa para pessoa (e com óculos, porque a armação
    puxa a estimativa das pálpebras) — por isso o programa calibra o aberto e o
    fechado de cada usuário em vez de usar um limiar fixo.
    """
    p1, p2, p3, p4, p5, p6 = (pts[i] for i in OLHO[lado]["ear"])
    largura = np.linalg.norm(p1 - p4)
    if largura < 1e-6:
        return 0.0
    return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2.0 * largura))


def posicao_iris(pts: np.ndarray, lado: str) -> tuple[float, float]:
    """Posição da íris dentro do olho, normalizada pela largura do olho.

    u: ao longo do eixo canto-externo → canto-interno (0 = no meio dos cantos).
    v: perpendicular a esse eixo (para baixo positivo).
    Usar o eixo dos cantos (e não x/y da imagem) torna a medida independente de
    a cabeça estar inclinada para o lado.
    """
    o = OLHO[lado]
    ext, inn = pts[o["externo"]], pts[o["interno"]]
    centro_iris = pts[list(o["iris"])].mean(axis=0)
    eixo = inn - ext
    largura = float(np.linalg.norm(eixo))
    if largura < 1e-6:
        return 0.0, 0.0
    eixo = eixo / largura
    normal = np.array([-eixo[1], eixo[0]])
    if normal[1] < 0:  # garante "para baixo" positivo
        normal = -normal
    rel = centro_iris - (ext + inn) / 2.0
    return float(rel @ eixo / largura), float(rel @ normal / largura)


def pose_cabeca(pts: np.ndarray) -> tuple[float, float]:
    """Giro (yaw) e inclinação (pitch) aproximados da cabeça, sem unidade.

    Mede onde está a ponta do nariz em relação ao ponto médio entre os olhos,
    dividido pela distância entre os olhos. Basta para a regressão aprender —
    não precisa ser um ângulo de verdade.
    """
    centro_d = (pts[OLHO["direito"]["externo"]] + pts[OLHO["direito"]["interno"]]) / 2
    centro_e = (pts[OLHO["esquerdo"]["externo"]] + pts[OLHO["esquerdo"]["interno"]]) / 2
    meio = (centro_d + centro_e) / 2
    eixo = centro_e - centro_d
    dist = float(np.linalg.norm(eixo))
    if dist < 1e-6:
        return 0.0, 0.0
    eixo = eixo / dist
    normal = np.array([-eixo[1], eixo[0]])
    if normal[1] < 0:
        normal = -normal
    rel = pts[NARIZ] - meio
    return float(rel @ eixo / dist), float(rel @ normal / dist)


@dataclass
class Medida:
    """O que o programa extrai de um quadro com rosto."""
    ear_e: float
    ear_d: float
    iris_e: tuple[float, float]
    iris_d: tuple[float, float]
    yaw: float
    pitch: float
    pontos: np.ndarray  # em pixels, para desenhar


def medir(pts: np.ndarray) -> Medida:
    yaw, pitch = pose_cabeca(pts)
    return Medida(
        ear_e=ear(pts, "esquerdo"),
        ear_d=ear(pts, "direito"),
        iris_e=posicao_iris(pts, "esquerdo"),
        iris_d=posicao_iris(pts, "direito"),
        yaw=yaw,
        pitch=pitch,
        pontos=pts,
    )


def vetor_olhar(m: Medida, usar: str) -> np.ndarray:
    """Vetor de características para a regressão olhar → tela.

    usar: "ambos" (média dos dois olhos), "esquerdo" ou "direito".
    """
    if usar == "esquerdo":
        u, v = m.iris_e
    elif usar == "direito":
        u, v = m.iris_d
    else:
        # o eixo canto-externo→interno aponta para +x da imagem no olho direito e
        # para -x no esquerdo; a diferença dá os dois no mesmo sentido (+x)
        u = (m.iris_d[0] - m.iris_e[0]) / 2
        v = (m.iris_e[1] + m.iris_d[1]) / 2
    return np.array([u, v, m.yaw, m.pitch], dtype=float)
