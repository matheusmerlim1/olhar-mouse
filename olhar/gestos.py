"""Piscadas → cliques.

Duas camadas, ambas sem câmera (recebem números e o tempo em segundos):

1. `Palpebras`: transforma o EAR de cada olho em "aberto/fechado", usando o
   aberto e o fechado medidos NA CALIBRAÇÃO de cada usuário (é o que resolve
   óculos: a armação muda o EAR de base, mas a régua passa a ser a da pessoa),
   com mediana dos últimos quadros (reflexo na lente dá picos isolados) e
   histerese (fecha acima de 60 %, só reabre abaixo de 40 %).

2. `Gestos`: máquina de estados que lê a sequência de estados dos olhos
   (ABERTO, AMBOS, ESQ, DIR) e reconhece:
     - 2 piscadas lentas com os dois olhos ............ clique DIREITO
     - 2 piscadelas lentas (um olho só fecha) .......... clique ESQUERDO
     - um olho fica fechado e o outro pisca 2× lento ... clique ESQUERDO
   Piscada normal (rápida, involuntária) é ignorada. Olho fechado por muito
   tempo (descansando) cancela a sequência.

   Modo de um olho só: 2 piscadas lentas = DIREITO, 3 = ESQUERDO.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

ABERTO, AMBOS, ESQ, DIR = "aberto", "ambos", "esq", "dir"


@dataclass
class CalibPalpebra:
    """EAR do olho aberto e fechado de um usuário (por olho)."""
    aberto_e: float = 0.28
    fechado_e: float = 0.10
    aberto_d: float = 0.28
    fechado_d: float = 0.10

    def fechamento(self, ear: float, lado: str) -> float:
        """0 = totalmente aberto, 1 = totalmente fechado (pode passar dos limites)."""
        a, f = (self.aberto_e, self.fechado_e) if lado == "esq" else (self.aberto_d, self.fechado_d)
        faixa = max(a - f, 1e-3)
        return (a - ear) / faixa


def olho_fechado_na_coleta(calib: CalibPalpebra, ear_e: float, ear_d: float) -> bool:
    """Piscada de verdade durante a coleta de um ponto. Olhando para baixo ou bem para o
    lado a pálpebra abaixa sozinha: com o limite antigo (meio fechado) esses quadros eram
    jogados fora e pontos inteiros da calibração se perdiam."""
    return (calib.fechamento(ear_e, "esq") + calib.fechamento(ear_d, "dir")) / 2 > 0.75


class Palpebras:
    ACOMPANHA = 0.45

    def __init__(self, calib: CalibPalpebra, janela_mediana: int = 3,
                 limiar_fecha: float = 0.6, limiar_abre: float = 0.4):
        self.calib = calib
        self.lim_fecha = limiar_fecha
        self.lim_abre = limiar_abre
        self._hist = {"esq": deque(maxlen=max(1, janela_mediana)),
                      "dir": deque(maxlen=max(1, janela_mediana))}
        self.fechado = {"esq": False, "dir": False}
        self.nivel = {"esq": 0.0, "dir": 0.0}

    def atualizar(self, ear_e: float, ear_d: float) -> tuple[bool, bool]:
        for lado, ear in (("esq", ear_e), ("dir", ear_d)):
            h = self._hist[lado]
            h.append(self.calib.fechamento(ear, lado))
            nivel = sorted(h)[len(h) // 2]
            self.nivel[lado] = nivel
            if self.fechado[lado]:
                if nivel < self.lim_abre:
                    self.fechado[lado] = False
            elif nivel > self.lim_fecha:
                self.fechado[lado] = True
        fe, fd = self.fechado["esq"], self.fechado["dir"]
        # piscada dos dois olhos em que um fecha mais que o outro: se o outro está pelo menos
        # quase na metade do caminho, conta como os dois (numa piscadela ele fica aberto)
        if fe != fd and min(self.nivel["esq"], self.nivel["dir"]) > self.ACOMPANHA:
            fe = fd = True
        return fe, fd


def estado_de(fech_e: bool, fech_d: bool) -> str:
    if fech_e and fech_d:
        return AMBOS
    if fech_e:
        return ESQ
    if fech_d:
        return DIR
    return ABERTO


@dataclass
class ConfigGestos:
    lento_min: float = 0.30       # s — abaixo disso é piscada normal (ignorada)
    lento_max: float = 2.50       # s — acima disso é "descansando o olho" (cancela); medido: piscadas lentas de até 1,6 s
    janela: float = 1.50          # s — tempo máximo entre o fim de uma e o início da outra
    estabilidade: float = 0.06    # s — um estado só vale se durar isso (tira ruído)
    dominancia: float = 0.60      # fração do episódio num estado para classificá-lo
    pausa_apos_clique: float = 0.80
    um_olho: bool = False         # True: só um olho é observado (2 = direito, 3 = esquerdo)


@dataclass
class _Episodio:
    inicio: float
    segmentos: list = field(default_factory=list)  # [estado, t_inicio, t_fim]
    consumido: bool = False


class Gestos:
    """Alimente `atualizar(t, fechado_esq, fechado_dir)` a cada quadro.

    Devolve "esquerdo", "direito" ou None. `fechando` diz se algum olho está
    fechado agora (o app congela o cursor nesse período, porque fechar o olho
    arrasta a íris estimada para baixo).
    """

    def __init__(self, cfg: ConfigGestos | None = None):
        self.cfg = cfg or ConfigGestos()
        self.estado = ABERTO
        self._candidato = ABERTO
        self._cand_desde = 0.0
        self._ep: _Episodio | None = None
        self._seq: list[tuple[str, float, float]] = []  # (tipo, inicio, fim)
        self._bloqueio_ate = -1.0
        self.ultimo_evento = ""

    @property
    def fechando(self) -> bool:
        return self.estado != ABERTO or self._candidato != ABERTO

    # ------------------------------------------------------------------ entrada
    def atualizar(self, t: float, fech_e: bool, fech_d: bool) -> str | None:
        bruto = estado_de(fech_e, fech_d)
        if self.cfg.um_olho:
            bruto = AMBOS if bruto != ABERTO else ABERTO

        clique = None
        # debounce: o estado bruto precisa durar `estabilidade` para valer
        if bruto != self._candidato:
            self._candidato, self._cand_desde = bruto, t
        if self._candidato != self.estado and t - self._cand_desde >= self.cfg.estabilidade:
            clique = self._mudar(self._candidato, self._cand_desde)

        clique = clique or self._expirar(t)
        if clique and t < self._bloqueio_ate:
            clique = None
        if clique:
            self._bloqueio_ate = t + self.cfg.pausa_apos_clique
            self._seq.clear()
        return clique

    # -------------------------------------------------------------- transições
    def _mudar(self, novo: str, t: float) -> str | None:
        anterior, self.estado = self.estado, novo
        clique = None
        if anterior == ABERTO:
            self._ep = _Episodio(inicio=t)
        elif self._ep is not None:
            self._ep.segmentos[-1][2] = t
            clique = self._olho_segurado(final=(novo == ABERTO))

        if novo == ABERTO:
            if self._ep is not None:
                clique = clique or self._fim_episodio(self._ep, t)
            self._ep = None
        elif self._ep is not None:
            self._ep.segmentos.append([novo, t, t])
        return clique

    def _olho_segurado(self, final: bool) -> str | None:
        """Um olho fechado o tempo todo + o outro pisca 2× lento → esquerdo."""
        ep = self._ep
        if ep is None or ep.consumido or self.cfg.um_olho:
            return None
        segs = ep.segmentos
        if not segs or segs[0][0] not in (ESQ, DIR):
            return None
        segurado = segs[0][0]
        if any(s[0] not in (segurado, AMBOS) for s in segs):
            return None
        lentas = sum(1 for s in segs if s[0] == AMBOS
                     and self.cfg.lento_min <= s[2] - s[1] <= self.cfg.lento_max)
        if lentas >= 2:
            ep.consumido = True
            self.ultimo_evento = f"olho {'esq' if segurado == ESQ else 'dir'} fechado + 2 piscadas"
            return "esquerdo"
        return None

    def _fim_episodio(self, ep: _Episodio, t_fim: float) -> str | None:
        if ep.consumido:
            return None
        dur = t_fim - ep.inicio
        if dur < self.cfg.lento_min:
            return None  # piscada normal: não conta e não atrapalha
        if dur > self.cfg.lento_max:
            # olho segurado sem completar o gesto, ou descansando: cancela
            self._seq.clear()
            self.ultimo_evento = "fechado demais (cancelado)"
            return None
        tempo = {AMBOS: 0.0, ESQ: 0.0, DIR: 0.0}
        for est, a, b in ep.segmentos:
            tempo[est] += b - a
        if tempo[AMBOS] >= self.cfg.dominancia * dur:
            tipo = "piscada"
        elif max(tempo[ESQ], tempo[DIR]) >= self.cfg.dominancia * dur:
            tipo = "piscadela"
        else:
            self._seq.clear()
            return None

        if self._seq and (self._seq[-1][0] != tipo or ep.inicio - self._seq[-1][2] > self.cfg.janela):
            self._seq.clear()
        self._seq.append((tipo, ep.inicio, t_fim))
        self.ultimo_evento = f"{tipo} lenta {len(self._seq)}"

        if self.cfg.um_olho:
            return None  # decide quando a janela fechar (2 ou 3)
        if len(self._seq) >= 2:
            return "direito" if tipo == "piscada" else "esquerdo"
        return None

    def _expirar(self, t: float) -> str | None:
        if not self._seq or self.estado != ABERTO or self._candidato != ABERTO:
            return None
        if t - self._seq[-1][2] <= self.cfg.janela:
            return None
        n = len(self._seq)
        self._seq.clear()
        if self.cfg.um_olho:
            if n == 2:
                return "direito"
            if n >= 3:
                return "esquerdo"
        return None
