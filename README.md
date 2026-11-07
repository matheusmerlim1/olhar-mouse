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

## Instalar

Página de download: **https://matheusmerlim1.github.io/olhar-mouse/**

1. Baixe o [olhar-mouse.zip](https://github.com/matheusmerlim1/olhar-mouse/releases/latest/download/olhar-mouse.zip) e extraia numa pasta.
2. Dois cliques em `instalar.bat`: instala o Python 3.12 se faltar (winget), cria o ambiente do
   programa, baixa as dependências (~380 MB) e cria o atalho **Olhar-mouse** na Área de Trabalho e
   no menu Iniciar. Pode rodar de novo para atualizar ou reparar.
3. Para remover: `desinstalar.bat` (tira atalhos e a abertura com o Windows) e apague a pasta.

### Atualização automática

Toda vez que abre, o programa procura uma versão nova no GitHub e **atualiza antes de rodar**
(sem internet, segue normalmente). Sua calibração e preferências (`dados/`) nunca são
sobrescritas. Depois de atualizar, mostra um card com as **Novidades** e **Correções**. No menu do
ícone há também *Procurar atualizações agora*. Para desligar: `"atualizar_automaticamente": false`
no `config.json`.

## Como usar

O programa roda **sem janela**, como o ditado por voz (projeto 24). Ao abrir, ele mostra só a
escolha da câmera e a calibração; depois fica apenas um **ícone de olho perto do relógio**.

**Para abrir:** ícone **Olhar-mouse** na Área de Trabalho ou no menu Iniciar. Se não existirem,
rode `iniciar.bat` uma vez e use, no menu do ícone, *Criar atalhos*.

O olho fica junto com os outros ícones escondidos, na setinha **^** ao lado do relógio (como o
ditado por voz); se quiser à vista, arraste-o dali para a barra de tarefas. Fechar a tela de
escolha ou cancelar a calibração **não fecha o programa**: ele fica parado na bandeja (olho
cinza riscado). Clique duas vezes no olho para escolher a câmera e começar. Para fechar de
vez: menu do ícone › *Sair*.

**Três opções de câmera**, escolhidas numa tela ao abrir (clique ou teclas 1, 2, 3; Enter repete
a última):

| | Opção | Quando usar |
|---|---|---|
| 1 | **Câmera do computador** | webcam ou outra câmera que o Windows enxergue (inclui celular em modo webcam USB) |
| 2 | **Celular pelo QR code** | celular no mesmo Wi-Fi; nada para instalar |
| 3 | **Celular pelo cabo USB** | Android; sem Wi-Fi e sem internet |

Os atalhos `iniciar-webcam.bat`, `iniciar-celular.bat` e `iniciar-usb.bat` vão direto para a opção,
sem perguntar. A abertura junto com o Windows usa a última escolhida. No menu do ícone, *Câmera*
traz as mesmas três opções e *Perguntar ao abrir* (desmarcado, ele usa sempre a última).

Na primeira vez o ambiente Python é criado e as dependências instaladas pelo `iniciar.bat` (precisa
do Python 3.12, `py -3.12`).

1. **Celular**: abre uma janela com o QR code (Wi-Fi) ou com as instruções do cabo (USB) (veja [Celular pelo Wi-Fi](#celular-pelo-wi-fi-qr-code-sem-instalar-nada) e [pelo cabo USB](#celular-pelo-cabo-usb-android-sem-wi-fi)).
2. **Calibração** (só na primeira vez, ou quando a câmera, o olho ou os óculos mudam). A tela fica
   preta e mostra a câmera até achar o seu rosto. Depois:
   - olhe para o ponto central com os olhos abertos;
   - feche os olhos quando pedir e só abra quando ouvir o bipe;
   - siga com o olhar os 13 pontos que aparecem.
   Mantenha a cabeça mais ou menos onde vai ficar durante o uso. Se o rosto sumir no meio, ele
   avisa com um bipe grave e recomeça.
3. Pronto: a tela volta ao normal e o cursor segue o olhar, em qualquer programa.

**Funciona como um segundo mouse.** O mouse de verdade sempre funciona: se você mexer nele, o
olhar não puxa o cursor de volta e só volta a mandar quando você olhar para outro lugar da tela.
Olhando para um ponto, o cursor fica parado (não fica "tremendo"); a zona de repouso se ajusta
sozinha ao tremido da sua câmera. Se a cabeça sair da posição da calibração (virada, olhando o
teclado), o cursor fica parado e os cliques por piscada ficam desligados até você voltar.
Os cliques por piscada caem onde o cursor estiver.

Cor do ícone: **verde** seguindo o olhar · **cinza riscado** pausado ou parado · **azul-petróleo** mouse físico em
uso · **âmbar** olhar fora da área calibrada · **vermelho** rosto não encontrado · **azul** esperando o celular · **roxo** calibrando · **laranja** carregando.

Menu do ícone (botão direito): escolher câmera e começar (quando parado), pausar/retomar, trocar de câmera, recalibrar, mostrar a câmera, trocar entre webcam e
celular, olho usado (os dois, só o esquerdo ou só o direito), uso óculos, bipes, iniciar com o
Windows, criar atalhos, liberar firewall para o celular, abrir o `config.json`, ver o registro, sair. As trocas
ficam gravadas no `config.json`.

| Tecla | Função |
|---|---|
| **F9** | pausa / retoma (funciona com qualquer janela em foco) |
| **F10** | refaz a calibração |
| **Esc** (na calibração) | cancela |

**Mostrar a câmera** (no menu) abre uma janela com os olhos detectados e duas barras com o quanto
cada olho está fechado. A barra fica vermelha quando o programa considera o olho fechado. Serve para
conferir a detecção; feche quando quiser (Esc ou o X), que o programa continua rodando.

Só abre uma cópia por vez, porque duas moveriam o mouse ao mesmo tempo. Erros aparecem como
notificação do Windows e ficam em `dados/olhar.log`. Para ver tudo no terminal:
`.venv\Scripts\python -m olhar --console`.

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

## Celular pelo cabo USB (Android, sem Wi-Fi)

Dois jeitos, ambos sem internet e sem rede:

**A. Android 14 ou mais novo: o celular vira uma webcam.** Ligue o cabo, puxe a barra de
notificações, toque em *"Carregando este dispositivo via USB"* e escolha **Webcam**. Em
alguns aparelhos isso não existe; aí use o jeito B. O celular aparece como câmera no Windows:
no menu do ícone, *Câmera* › escolha o nome dele. A lista se atualiza sozinha em poucos
segundos.

**B. Qualquer Android: `iniciar-usb.bat`** (ou *Câmera › Celular pelo cabo USB*). A mesma
página do QR code passa pelo cabo, pelo túnel do ADB (ferramenta oficial do Android):

1. No celular, ligue a **Depuração USB**, uma vez só: *Configurações › Sobre o telefone* ›
   toque 7 vezes em *Número da versão*; depois *Configurações › Sistema › Opções do
   desenvolvedor* › **Depuração USB**.
2. Ligue o cabo e aceite **"Permitir depuração USB?"** no celular (marque "sempre").
3. A página abre sozinha no navegador do celular. Toque em *Usar câmera* e permita.

Pelo cabo, a página abre como `http://127.0.0.1`, que o navegador já considera seguro. Por isso
não aparece o aviso de certificado, o firewall não entra na história e o servidor nem fica
visível na rede. O ADB é procurado no SDK do Android (Flutter/Android Studio). Se não existir,
o programa baixa o oficial do Google (~7 MB) para `ferramentas/platform-tools/`.

iPhone: não tem modo webcam nem ADB no Windows. Use o Wi-Fi (QR code) ou um app de webcam
pelo cabo (DroidCam, Camo), que aparece como câmera no menu.

## Celular pelo Wi-Fi (QR code, sem instalar nada)

1. Dê dois cliques em `iniciar-celular.bat` (ou escolha *Câmera › Celular* no menu do ícone).
2. A tela do PC mostra um **QR code**. Aponte a câmera do celular para ele e abra o link.
3. Na primeira vez o navegador avisa **"conexão não particular"**. Toque em *Avançado* e
   *Continuar*. O aviso aparece porque o certificado HTTPS foi gerado pelo seu próprio PC, e o
   HTTPS é obrigatório: navegador de celular só libera a câmera em página segura.
4. Permita o uso da câmera. A página mostra quantos quadros por segundo está enviando, e o PC
   segue para a calibração.

Precisa de:
- PC e celular na **mesma rede** (o celular no Wi-Fi do mesmo roteador do PC);
- **liberar o firewall do Windows** uma vez: botão direito em `ferramentas/liberar-firewall.ps1`
  e depois *Executar com o PowerShell* (o Windows pede confirmação de administrador). O script libera
  só as portas 8443–8452, só em rede privada. Sem isso a página fica "carregando" para sempre no
  celular, porque o firewall descarta a conexão em silêncio;
- celular **parado**, em pé, perto do monitor e de frente para o rosto. Se ele mudar de lugar,
  aperte F10 para calibrar de novo. Ao trocar de câmera o programa recalibra sozinho;
- a página aberta e a tela do celular acesa (a página pede para a tela não apagar). Se a conexão
  cair, o QR code volta para a tela do PC.

O endereço tem um código aleatório (guardado em `dados/`), então outro aparelho da rede não
consegue mandar imagem sem ter lido o QR. As imagens vão direto do celular para o seu PC e não
passam pela internet.

Ainda funciona: um app de câmera IP (`"camera": "http://IP:8080/video"`, app IP Webcam) ou o
DroidCam como webcam virtual (`"camera": 1`).

O celular é só a câmera: quem é controlado é o mouse do computador.

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
| `camera` | `0` | número ou nome da câmera, `"usb"` (celular no cabo), `"celular"` (QR code) ou URL de câmera IP |
| `olho` | `"ambos"` | `"ambos"`, `"esquerdo"` ou `"direito"` |
| `oculos` | `false` | filtragem extra contra reflexo na lente |
| `realce_contraste` | `false` | contraste local (CLAHE), para pouca luz |
| `mostrar_camera` | `false` | abrir já com a janela da câmera |
| `perguntar_camera` | `true` | mostrar a escolha das 3 câmeras ao abrir |
| `som` | `true` | bipe no clique e na pausa |
| `gestos.lento_min` / `lento_max` | `0.30` / `1.50` | duração (s) de uma piscada "lenta" |
| `gestos.janela` | `1.50` | tempo máximo (s) entre as duas piscadas |
| `estabilidade` | `"media"` | `"baixa"` (mais rápido), `"media"` ou `"alta"` (mais firme); também pelo menu |

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
| `olhar/camera.py` | webcam/câmera IP e detector MediaPipe |
| `olhar/celular.py` | câmera do celular pelo navegador: servidor HTTPS, certificado, QR code |
| `olhar/usb.py` | celular pelo cabo: ADB, túnel `adb reverse`, abre a página no celular |
| `olhar/mouse.py` | mover e clicar (API do Windows) |
| `olhar/app.py` | laço principal |
| `olhar/bandeja.py` | ícone na bandeja, menu, iniciar com o Windows, atalhos |
| `olhar/escolha.py` | tela inicial com as 3 opções de câmera |
| `olhar/atualizador.py` | procura e aplica versão nova ao abrir (git ou ZIP), protege `dados/` |
| `olhar/novidades.py` | card "O que mudou" depois de uma atualização |
| `modelos/face_landmarker.task` | modelo do Google MediaPipe (Apache 2.0) |

A calibração fica em `dados/calibracao.json` e as escolhas do menu em `dados/config.json` (não vão
para o git; são de cada pessoa e de cada máquina). O `config.json` da raiz guarda os padrões e os
ajustes finos.

## Testes

```
.venv\Scripts\python -m unittest discover -s tests -t .
```

São 64 testes, todos sem câmera nem celular: os gestos (sequências de piscadas sintéticas, incluindo
piscadas normais, ruído de um quadro, olhos que não fecham juntos, olho fechado demais), as
pálpebras (calibração por usuário, histerese, pico de reflexo), a geometria, a regressão, o
filtro e o congelamento do cursor.
