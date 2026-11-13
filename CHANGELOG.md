# WiFinder — novidades

## 1.7.0 — 11/11/2026

Feito a partir do primeiro voo com muitas redes (voo 20: 113 redes).

### Tela inicial (novo)
- `python3 -m wifinder` abre a tela inicial no navegador (só no próprio
  computador, em http://127.0.0.1:8737/).
- Mostra sozinha quando o ESP32 é ligado na USB; um clique baixa os voos da
  placa, com barra de progresso. Apagar da placa depois é opcional.
- Biblioteca de voos na pasta `voos/`: um arquivo `.log` por voo, com data e
  hora do GPS no nome. Baixar de novo não duplica; um voo que cresceu é
  atualizado; logs vazios são ignorados.
- Cada voo tem cartão com desenho do percurso, aparelhos, redes, duração e
  distância, e botões para o mapa e o relatório PDF. Dá para renomear,
  excluir e importar arquivos `.log` do computador.
- Vários voos juntos: marque os cartões e abra um mapa ou relatório só, com
  as amostras de todos somadas na estimativa.

### Executável para Linux (novo)
- `./empacotar.sh` gera o arquivo único `WiFinder`; com `--atalho`, cria a
  entrada no menu de aplicativos.
- Abrir o programa com ele já aberto só mostra a tela existente; botão
  "Encerrar o WiFinder" no rodapé.

### Estimativa
- Posição pelo centroide dos pontos de sinal mais forte, em vez do ajuste de
  perda de percurso. Nas simulações o erro mediano caiu de ~40 m para ~20 m
  na cidade e de ~27 m para ~16 m na selva; o pior caso, de ~380 m para ~100 m.
- Ficar parado não puxa mais a estimativa: as amostras são agrupadas em
  células de 8 m antes da conta.
- Redes do mesmo aparelho (principal, visitantes, operadora) viram um item só.
  No voo 20, 113 redes são 73 aparelhos.
- Raio provável (± m) no lugar do raio de incerteza de centenas de metros;
  nas simulações a posição verdadeira fica dentro dele em 94 % dos casos.
- Confiança boa / média / fraca, conforme o sinal e em quantos pontos do
  percurso o aparelho foi ouvido.
- Fixes ruins do começo (GPS ainda se acertando) não entram na conta nem no
  desenho do percurso.

### Mapa interativo
- Zoom bem maior (até o nível 22; imagem de satélite nativa até o 19 onde
  existe, detectado sozinho).
- Vista 3D: botão 2D/3D, inclinar e girar com o botão direito do mouse,
  coluna por aparelho com altura conforme o sinal, prédios onde o
  OpenStreetMap tem, e a altura do voo como uma cortina sob o percurso.
- Cor = sinal, tamanho = confiança. Os nomes não se encavalam mais: aparecem
  os mais fortes e os outros surgem ao aproximar.
- Cabeçalho com aparelhos, redes, duração e percurso; lista com canal e
  confiança; popup com todas as redes do aparelho.
- CSV e KML com canal, redes do aparelho e confiança.

### Relatório PDF
- Página 1 com indicadores do voo e mapa de satélite mais nítido, enquadrado
  no percurso, sem os círculos gigantes e com nomes sem sobreposição.
- Página nova "Panorama": aparelhos por canal, por sinal, os dez mais fortes
  e um quadro explicando como ler o relatório.
- Tabela redesenhada (linhas alternadas, cor do sinal, canal, número de redes).

### Mudou
- `<db>-roteadores.csv` tem colunas novas: ssid, bssid, redes, canal, lat,
  lon, raio_m, confianca, amostras, pontos, rssi_max.
- `--ground-alt` e `--min-samples` continuam aceitos, mas não têm mais efeito.
- O mapa passou do Leaflet para o MapLibre GL.

### Conhecido
- O erro mediano na simulação de cidade é ~20 m; a meta antiga de 15 m do
  teste `test_simulated_flight` não foi atingida e o limite do teste passou
  para 25 m.
- Num percurso em linha reta não dá para saber de que lado o aparelho está.

## 1.6.0 — 11/11/2026

Base anterior: 1.5.1 (coleta na Raspberry Pi com `iw scan`, simulador,
estimativa e mapa simples).

### Coleta embarcada no ESP32 (novo)
- Firmware Arduino em `firmware/wifinder` para ESP32 WROOM-32 com tela OLED:
  lê o GPS NEO-6M (UART2, GPIO16/17), varre WiFi canal a canal (120 ms por
  canal, uma volta a cada ~2 s) e grava tudo na flash (LittleFS, ~1,9 MB).
- Detecção automática da tela OLED (pinos 21/22, 5/4, Heltec 4/15 e 4/5).
  Se a tela for Heltec, os pinos do GPS trocam sozinhos para 17/13.
- Tela de coleta: missão atual, estado do GPS com diagnóstico (sem dados,
  lixo na serial, sem fix, fix com satélites e HDOP), hora UTC, altitude,
  redes ouvidas, amostras gravadas e flash livre.
- Comandos pela USB: `help`, `ls`, `dump`, `rm`, `rmall`, `done`, `pause`,
  `resume`, `info`.
- Botão EN: reinicia e abre uma missão nova (tela "Nova missão: vNNN").
  Botão BOOT segurado 3 s: apaga todos os logs, com contagem na tela.
- Animações: "PC conectado" com spinner, barra de progresso durante a
  transferência e check "Pronto!" no fim.
- Pull-up no RX do GPS (sem ruído com o módulo desligado); `dump` limitado
  ao tamanho anunciado (o arquivo atual cresce durante a transferência).
- `firmware/flash.sh` compila e grava com um comando (partição no_ota:
  2 MB de app + 2 MB de logs).

### Linha de comando
- `pull`: baixa os logs pela USB, guarda em `<db>-logs/` e importa no banco,
  sem importar duas vezes o mesmo arquivo (tabela `imports`). `--rm` apaga da
  placa depois de baixar.
- `import`: importa logs já baixados. A posição de cada rede é interpolada
  entre os fixes vizinhos pelo relógio da placa (até 2 s de distância).
- `report`: relatório em PDF com resumo do voo (início, duração, distância,
  altitude, fixes, amostras, redes), mapa de satélite montado a partir dos
  tiles do Esri (com cache em `~/.cache/wifinder-tiles`) e tabela das redes.
  `--sem-fundo` para uso sem internet.
- `simulate`: `--ambiente selva` (drone acima da copa, perda por vegetação
  pelo modelo de Weissberger, roteadores em clareira ou sob a mata,
  sombreamento forte), `--esp32-log` (grava o voo no formato do firmware),
  `--alt` e `--lane`.

### Mapa interativo
- Painel com busca por SSID/BSSID, filtros por status, mínimo de amostras,
  RSSI máximo e incerteza máxima; camadas de trajetória, círculos e nomes.
- Lista das redes; clicar voa até a rede e mostra os pontos onde ela foi
  ouvida, coloridos do sinal fraco ao forte.
- Coordenadas em decimal, graus/minutos/segundos ou MGRS: na barra inferior
  conforme o cursor, ao clicar no mapa e no popup de cada rede, com botão de
  copiar e link para o Google Maps.
- Exportação das redes visíveis em CSV (com MGRS) e KML (Google Earth).
- Nome da rede sempre visível ao lado de cada ponto.
- Fundo de satélite (Esri) e ruas (CARTO); o OpenStreetMap foi removido
  porque bloqueia páginas abertas do disco. Zoom nativo limitado a 17.

### Outros
- README com fiação, gravação e fluxo completo.
- Testes novos: importação de log, download com serial simulada, fluxo
  completo ESP32, relatório. 7 passam.

### Conhecido
- O estimador por ajuste de perda de percurso erra ~50 m na simulação de
  cidade e ~70 m na de selva; o centroide ponderado pelo sinal acerta melhor
  na selva (~17 m). `test_simulated_flight` continua falhando por isso.
  Próximo passo sugerido: centroide ou híbrido no `estimate`.
- A parte de GPS do firmware ainda não foi testada com o módulo ligado.
