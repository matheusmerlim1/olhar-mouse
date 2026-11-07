# Olhar-mouse

Controla o mouse do Windows com os olhos, usando a webcam do computador ou a câmera do
celular. O cursor vai para onde você olha, e piscadas lentas viram cliques.

| Gesto | Ação |
|---|---|
| Olhar para um ponto da tela | move o cursor |
| **2 piscadas lentas** com os dois olhos | **clique direito** |
| **2 piscadelas lentas** (só um olho fecha, o outro fica aberto) | **clique esquerdo** |
| Manter um olho fechado e piscar o outro **2 vezes devagar** | **clique esquerdo** |

"Lenta" quer dizer olho fechado entre 0,3 s e 1,5 s, com no máximo 1,5 s entre uma piscada e a
próxima. A piscada normal (rápida, involuntária) é ignorada. Fechar os olhos por mais tempo
(para descansar) cancela o gesto. Enquanto o olho está fechado o cursor fica parado, e o clique
cai onde você estava olhando antes de piscar.

## Como usar

1. Dê dois cliques em `iniciar.bat`. Na primeira vez ele cria o ambiente Python e instala as
   dependências (precisa do Python 3.12, `py -3.12`).
2. **Calibração** (só na primeira vez, ou com F10): a tela fica preta.
   - olhe para o ponto central com os olhos abertos;
   - feche os olhos quando pedir e só abra quando ouvir o bipe;
   - siga com o olhar os 13 pontos que aparecem.
   Mantenha a cabeça mais ou menos onde vai ficar durante o uso.
3. Pronto: o cursor passa a seguir o olhar.

| Tecla | Função |
|---|---|
| **F9** | pausa / retoma (funciona com qualquer janela em foco) |
| **F10** | refaz a calibração |
| **Esc** ou **Q** (na janela da câmera) | sai |
| **P** / **C** (na janela da câmera) | pausa / calibra |

A janela da câmera mostra os olhos detectados e duas barras com o quanto cada olho está fechado
(fica vermelha quando o programa considera o olho fechado). Por ela você vê se a detecção está
boa antes de confiar nos cliques.

## Quem usa óculos

O detector de rosto (MediaPipe) continua achando olhos e íris com óculos. O que muda é a medida
de "olho aberto": a armação e o reflexo na lente deslocam a estimativa das pálpebras, e um limiar
fixo erraria. Por isso o programa **mede o seu olho aberto e fechado na calibração**. Basta
calibrar usando os óculos que vai usar.

No `config.json`:

- `"oculos": true` filtra mais (mediana de 5 quadros e estado que precisa durar 90 ms), para que
  um reflexo de um quadro só não seja confundido com uma piscada;
- `"realce_contraste": true` equaliza o contraste da imagem. Ajuda em ambiente escuro, mas num
  teste com óculos simulados não melhorou nada. Deixe desligado se a luz estiver boa.

Dicas: luz vindo de frente ou de lado (não refletindo direto na lente), câmera na altura dos
olhos, e incline levemente a armação se aparecer reflexo branco em cima da íris na janela da
câmera.

## Câmera do celular

Em `config.json`, campo `"camera"`:

- **IP Webcam** (Android): abra o app, toque em "Iniciar servidor" e use o endereço mostrado,
  terminando em `/video`, ex. `"camera": "http://192.168.0.10:8080/video"`.
- **DroidCam** (Android/iPhone): ele instala uma webcam virtual no PC; use o número dela,
  geralmente `"camera": 1`.

Também dá para trocar sem editar o arquivo: `iniciar.bat --camera 1`.

O celular funciona como câmera para o PC: quem é controlado é o mouse do computador. Para mover
um ponteiro no próprio celular seria preciso um app Android com serviço de acessibilidade, que
é outro projeto.

## Um olho só

Se só um olho pode ser usado (ou só um aparece bem na câmera), coloque
`"olho": "esquerdo"` ou `"olho": "direito"`. O olhar passa a ser medido só nesse olho e os
cliques mudam, porque piscadela não existe com um olho:

| Gesto (um olho) | Ação |
|---|---|
| 2 piscadas lentas | clique direito |
| 3 piscadas lentas | clique esquerdo |

O clique sai 1,5 s depois da última piscada (é o tempo de saber se vem mais uma).

## Ajustes (`config.json`)

| Campo | Padrão | O que faz |
|---|---|---|
| `camera` | `0` | número da webcam ou URL do celular |
| `olho` | `"ambos"` | `"ambos"`, `"esquerdo"` ou `"direito"` |
| `oculos` | `false` | filtragem extra contra reflexo na lente |
| `realce_contraste` | `false` | contraste local (CLAHE), para pouca luz |
| `mostrar_camera` | `true` | janela com a imagem da câmera |
| `som` | `true` | bipe no clique e na pausa |
| `gestos.lento_min` / `lento_max` | `0.30` / `1.50` | duração (s) de uma piscada "lenta" |
| `gestos.janela` | `1.50` | tempo máximo (s) entre as duas piscadas |
| `suavizacao.min_cutoff` | `0.6` | menor = cursor mais estável e mais lento |
| `suavizacao.beta` | `0.004` | maior = cursor responde mais rápido a movimentos grandes |

Mudou de tela, de olho ou o modo óculos? O programa percebe e calibra de novo sozinho.

## Limites

Uma webcam comum acerta o olhar com erro de alguns centímetros na tela (o erro médio aparece no
fim da calibração). Dá para clicar em botões e ícones, mas não em alvos minúsculos. Ajuda
aumentar a escala do Windows (Configurações › Tela › Escala) ou usar a Lupa. O olhar e a posição
da cabeça entram juntos no cálculo, então virar um pouco a cabeça também move o cursor, e isso
ajuda a fazer ajustes finos.

## Como funciona

```
câmera ─► MediaPipe Face Landmarker (478 pontos, com íris)
            ├─ posição da íris entre os cantos do olho + giro/inclinação da cabeça
            │     └─ regressão calibrada (13 pontos) ─► filtro One Euro ─► cursor
            └─ abertura de cada olho (EAR) normalizada pela calibração do usuário
                  └─ mediana + histerese ─► máquina de estados das piscadas ─► clique
```

| Arquivo | Conteúdo |
|---|---|
| `olhar/olhos.py` | geometria: EAR, posição da íris, pose da cabeça |
| `olhar/gestos.py` | pálpebras (aberto/fechado) e reconhecimento dos gestos |
| `olhar/modelo_olhar.py` | regressão olhar → tela, salvar/carregar calibração |
| `olhar/calibracao.py` | telas da calibração |
| `olhar/filtro.py` | filtro One Euro |
| `olhar/camera.py` | câmera/celular e detector MediaPipe |
| `olhar/mouse.py` | mover e clicar (API do Windows) |
| `olhar/app.py` | laço principal |
| `modelos/face_landmarker.task` | modelo do Google MediaPipe (Apache 2.0) |

A calibração fica em `dados/calibracao.json` (não vai para o git; é de cada pessoa e de cada
máquina).

## Testes

```
.venv\Scripts\python -m unittest discover -s tests -t .
```

São 31 testes, todos sem câmera: os gestos (sequências de piscadas sintéticas, incluindo
piscadas normais, ruído de um quadro, olhos que não fecham juntos, olho fechado demais), as
pálpebras (calibração por usuário, histerese, pico de reflexo), a geometria, a regressão, o
filtro e o congelamento do cursor.
