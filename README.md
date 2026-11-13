# WiFinder

Localiza roteadores WiFi a partir de RSSI + GPS coletados em voo. A coleta
roda num ESP32 com telinha OLED e GPS NEO-6M; a estimativa e o mapa são
gerados no computador.

```
ESP32 em voo ──(flash)──> logs v###.log ──(USB)──> voo.db ──> CSV + mapa HTML
```

## Estrutura

| Pasta / arquivo | O que é |
|---|---|
| `firmware/wifinder/` | Firmware Arduino do ESP32 (coleta WiFi + GPS, tela OLED, logs na flash) |
| `wifinder/` | Programa em Python: tela inicial, importação, estimativa, mapa, relatório, simulador |
| `suporte/` | Suporte impresso em 3D para levar a coleta em cima de um DJI Mavic 4 Pro (ver `suporte/LEIA-ME.md`) |
| `tests/` | Testes (`python3 -m pytest tests`) |
| `empacotar.sh` | Gera o executável único para Linux |
| `CHANGELOG.md` | Novidades de cada versão |

## Hardware

- ESP32 WROOM-32 com OLED 0,96" (SSD1306, I2C). O firmware acha a tela
  sozinho nos pinos mais comuns (21/22, 5/4, Heltec 4/15).
- GPS GY-NEO6M V2, ligado na UART2 do ESP32:

| GPS NEO-6M | ESP32           |
|------------|-----------------|
| VCC        | VIN (5 V) ou 3V3 |
| GND        | GND             |
| TX         | GPIO16 (RX2)    |
| RX         | GPIO17 (TX2), opcional |

O TX do GPS é 3,3 V, pode ir direto no ESP32. Se a tela for Heltec (reset no
GPIO16), o firmware troca o GPS para GPIO17 (RX) e GPIO13 (TX) e avisa na
tela e na serial.

## Firmware (`firmware/wifinder`)

```sh
arduino-cli core install esp32:esp32
arduino-cli lib install TinyGPSPlus U8g2
firmware/flash.sh /dev/ttyUSB0
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200
```

A tela mostra: arquivo atual, estado do GPS (sem dados / sem fix / satélites e
HDOP), hora UTC e altitude, redes ouvidas na última volta, amostras gravadas e
flash livre. Quando o PC manda comandos ela passa para "PC conectado", com
barra de progresso durante a transferência e um check no fim.

Botões: **EN** reinicia a placa e começa uma missão nova (arquivo novo; os
anteriores ficam guardados até serem baixados). **BOOT** segurado por 3 s
apaga todos os logs, com contagem na tela (solte antes para cancelar). Na serial sai uma linha de status (`#...`) a cada 2 s, e aceita
os comandos `help`, `ls`, `dump <arq>`, `rm <arq>`, `rmall`, `pause`, `resume`,
`info`.

Como funciona: varre um canal por vez (120 ms, canais 1 a 13) e grava cada
rede ouvida com o instante da varredura; o GPS grava um fix por segundo. Tudo
vai para a flash (LittleFS, ~1,9 MB, dá para várias horas de voo). A posição
de cada amostra é interpolada no computador entre os fixes vizinhos.

Diagnóstico do GPS na tela: `GPS SEM DADOS` = nada chega no GPIO16 (fiação);
`GPS lixo na serial` = chegam bytes mas nenhuma sentença válida (baud);
`GPS SEM FIX n sat` = módulo ok, esperando satélites (a céu aberto leva de 1 a
15 min no primeiro uso).

## No computador

```sh
pip install -r requirements.txt
python3 -m wifinder                        # tela inicial no navegador
```

A tela inicial mostra quando o ESP32 está na USB, baixa os voos com um clique
e guarda cada um na pasta `voos/` (um `.log` por voo). Cada voo abre no mapa
ou vira relatório PDF; marcando vários, eles abrem juntos num mapa só. Ela só
atende o próprio computador; Ctrl+C no terminal fecha. `--dir` muda a pasta
dos voos e `--port` a porta.

Executável para Linux: `./empacotar.sh` gera o arquivo `WiFinder` (um só,
~46 MB, não precisa de Python em quem for usar); `./empacotar.sh --atalho`
também põe o WiFinder no menu de aplicativos. Ele guarda os voos na pasta
`voos/` ao lado do executável. Abrir duas vezes só mostra a tela que já está
aberta; o botão "Encerrar o WiFinder" no rodapé fecha o programa.

Os mesmos passos pela linha de comando:

```sh
python3 -m wifinder pull voo.db            # baixa os logs pela USB e importa
python3 -m wifinder estimate voo.db        # gera voo-roteadores.csv e voo-mapa.html
python3 -m wifinder report voo.db          # gera voo-relatorio.pdf (resumo, panorama, tabela)
```

`pull` guarda os logs em `voo-logs/` e não importa duas vezes o mesmo arquivo;
`--rm` apaga da placa depois de baixar. `import` importa logs já baixados
(para ver um voo só: `python3 -m wifinder import voo20.db voo-logs/v020.log`).

Como a posição é estimada: para cada aparelho, a média dos pontos do percurso
onde o sinal chegou mais forte. As redes que o mesmo roteador anuncia
(principal, visitantes, operadora) são juntadas num item só. Cada aparelho sai
com um raio provável (± m) e uma confiança: boa (ouvido forte e em muitos
pontos), média ou fraca (ouvido em 1 ou 2 pontos). Um percurso em linha reta
não distingue o lado; passe dos dois lados ou em zigue-zague para afinar.

O mapa HTML tem vista 2D e 3D (botão no painel; botão direito do mouse inclina
e gira), zoom até o nível 22, busca, filtros por confiança e sinal, lista dos
aparelhos, os pontos onde o aparelho selecionado foi ouvido, coordenadas em
decimal, graus/minutos/segundos ou MGRS (cursor, clique no mapa e em cada
aparelho, com botão de copiar) e exportação dos visíveis em CSV e KML (Google
Earth). Precisa de internet para o fundo e para as bibliotecas.

`report` gera resumo com mapa, uma página de panorama (canais, sinal, os mais
fortes) e a tabela completa. Precisa de internet para o fundo de satélite
(Esri); sem ela, sai o mapa em metros com `--sem-fundo`. `simulate` gera um voo
sintético para testar sem hardware (`--ambiente selva` modela a perda pela
vegetação, `--esp32-log` grava no formato do firmware), e `collect` é a versão
antiga para Raspberry Pi.

Testes: `python3 -m pytest tests`.

Para experimentar sem hardware:

```sh
python3 -m wifinder simulate demo.db       # voo sintético
python3 -m wifinder estimate demo.db       # demo-roteadores.csv e demo-mapa.html
```

## Suporte para o drone

`suporte/` tem uma caixa fechada (base + tampa) que leva o ESP32 e o GPS em
cima de um DJI Mavic 4 Pro: modelo paramétrico do FreeCAD (`suporte.py`),
STL, STEP e G-code pronto para Ender-3 V2. Medidas, montagem, vedação e
impressão estão em `suporte/LEIA-ME.md`.
