"""Zoom automático: recorta a imagem em volta do rosto.

Rosto pequeno na imagem = íris com poucos pixels = cursor impreciso. A câmera filma em
resolução alta e só o recorte em volta do rosto vai para o detector, o que dá mais pixels de
verdade no olho (ampliar uma imagem pequena não daria).

Recortes são (x, y, l, a) em frações da imagem inteira. O recorte só muda quando precisa
(rosto saiu do centro ou ficou grande/pequeno demais), para a imagem não ficar "dançando".
As medidas do olhar são relativas ao próprio rosto, então o recorte não invalida a calibração.
"""
from __future__ import annotations

INTEIRA = (0.0, 0.0, 1.0, 1.0)


class Zoom:
    def __init__(self, ligado: bool = True, ocupacao: float = 0.42, largura_min: float = 0.30,
                 tempo_sem_rosto: float = 1.2):
        self.ligado = ligado
        self.ocupacao, self.largura_min, self.tempo_sem_rosto = ocupacao, largura_min, tempo_sem_rosto
        self.recorte = INTEIRA
        self._rosto_t = None

    @property
    def fator(self) -> float:
        return 1.0 / self.recorte[2]

    def atualizar(self, caixa, usado, t: float) -> bool:
        """caixa: (x0, y0, x1, y1) do rosto em frações do quadro RECEBIDO, ou None sem rosto.
        usado: recorte com que aquele quadro foi feito. Devolve True se o recorte mudou."""
        antes = self.recorte
        if not self.ligado:
            self.recorte = INTEIRA
            return antes != self.recorte
        if caixa is None:
            # perdeu o rosto: abre a imagem inteira para achá-lo de novo
            if self._rosto_t is None or t - self._rosto_t > self.tempo_sem_rosto:
                self.recorte = INTEIRA
            return antes != self.recorte
        self._rosto_t = t

        ux, uy, ul, ua = usado
        x0, x1 = ux + caixa[0] * ul, ux + caixa[2] * ul
        y0, y1 = uy + caixa[1] * ua, uy + caixa[3] * ua
        larg, alt = x1 - x0, y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

        rx, ry, rl, ra = self.recorte
        ocup = larg / rl
        fora_centro = abs(cx - (rx + rl / 2)) / rl > 0.18 or abs(cy - (ry + ra / 2)) / ra > 0.18
        if 0.30 <= ocup <= 0.55 and not fora_centro:
            return False
        if rl >= 1.0 and ocup >= 0.30:
            return False                # imagem inteira e rosto já grande: não há o que ampliar

        lado = min(1.0, max(self.largura_min, larg / self.ocupacao, alt / 0.85))
        self.recorte = (min(max(cx - lado / 2, 0.0), 1.0 - lado),
                        min(max(cy - lado / 2, 0.0), 1.0 - lado), lado, lado)
        return self.recorte != antes
