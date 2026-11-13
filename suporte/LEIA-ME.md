# Suporte fechado do WiFinder para o DJI Mavic 4 Pro

Duas peças:

- **Base** (`wifinder-mavic4pro-base.stl`): o mesmo aro do suporte de AirTag
  (o encaixe no drone não mudou: o aro abraça o corpo do drone, em pé, como
  um anel) com uma caixa deitada direto em cima do drone, com 1 mm de folga.
  A barra de cima do aro fica embutida na parede da frente da caixa. A caixa
  tem 69,5 × 81 mm (0,75 mm mais larga que o aro de cada lado), começa no plano da frente do aro e vai para trás.
- **Tampa** (`wifinder-mavic4pro-tampa.stl`): encaixa por cima com uma saia de
  6 mm, para a chuva escorrer por fora. Tem janela sobre a tela OLED.

Montada, a caixa sobe 23 mm acima do corpo do drone. Peso das duas peças: 39 a 65 g em PETG, conforme o enchimento.

Outros arquivos: `wifinder-mavic4pro.FCStd` e `.step` (editar no FreeCAD),
`montado-so-para-ver.stl`, `suporte.py` (gera tudo). A `previa-no-drone.png`
está desatualizada: mostra a caixa antiga, de 59 mm, feita para uma placa de
50 × 25,5 mm.

## Dentro da caixa (64,7 × 73 × 17 mm livres)

- **Lado esquerdo:** placa ESP32 em pé nos próprios pinos, tela para cima,
  encostada na parede esquerda, com o USB apontando para trás. O plugue USB
  entra por um furo na parede de trás e encaixa direto na placa.
- **Lado direito:** placa do GPS no fundo (prenda com fita dupla face) e a
  antena cerâmica colada em cima dela, virada para cima.
- Os fios passam pelas aberturas da divisória.
- Cole um pedaço de espuma na tampa, fora da janela, para a placa ESP32 não
  subir com a vibração.

## Vedação

É proteção contra chuva e respingo, não é à prova de imersão:

- Janela: cole por dentro um pedaço de acetato ou acrílico fino de
  21 × 34 mm no rebaixo (cola de silicone ou fita dupla face transparente).
- Furo do USB: depois de ligar o cabo, feche a folga com silicone ou massa
  de calafetar. A saia da tampa cobre o furo por cima.
- Tampa: 4 abraçadeiras, uma em cada par de orelhas. Para vedar melhor, passe
  um filete de silicone ou fita de espuma no topo das paredes.
- Há dois furinhos de dreno no fundo, nos cantos de trás.
- A caixa vai 81 mm para trás do aro, a 1 mm do corpo do drone (`FOLGA_DRONE`
  no `suporte.py`). Só sei que estão livres os 23 mm que a caixinha do AirTag
  ocupava: se o corpo do drone subir atrás disso, aumente a folga.
- O próprio Mavic 4 Pro não é feito para voar na chuva.

## Confira antes de imprimir

As medidas ficam no começo do `suporte.py`. As placas foram medidas à mão
em 12/11/2026 (ESP32 cerca de 7 × 3 cm, GPS 4 × 3 cm, antena 3 × 3 cm) e a caixa tem 1 mm de folga de cada lado
e 2 mm na ponta por causa disso. As outras vieram de anúncios e de um
palpite, não de medição:

| Medida | Valor usado | Como conferir |
|---|---|---|
| `ESP_COMP` × `ESP_LARG` | 70 × 30 mm | Comprimento e largura da placa ESP32, medidos de forma aproximada. Cabe até 72 × 32 mm. |
| `ESP_PINOS` | 8,5 mm | Da ponta dos pinos até a face de baixo da placa. Define a altura do furo do USB. |
| `USB_ACIMA` | 1,3 mm | O conector USB fica na face de cima da placa? Se ficar na de baixo, use −2,9. |
| `JAN_DESLOC` | 0 mm | A janela está centrada na placa. Se a tela ficar mais para uma ponta, desloque. |
| `GPS_LARG` | 30 mm | Largura da placa do GPS e da antena, medida de forma aproximada (o vão tem 31,5 de largura por 73 de comprimento). |

Para gerar de novo:

```sh
~/Downloads/FreeCAD_1.1.4-Linux-x86_64-py311.AppImage freecadcmd suporte.py
```

## Impressão

- Base: o STL já está com o aro deitado na mesa, como o suporte de AirTag, e
  a caixa em pé. Não precisa de suporte; use aba (brim), porque a peça fica
  com 81 mm de altura.
- Tampa: o STL já está de cabeça para baixo, com a face de cima na mesa; não
  precisa de suporte.
- PETG ou ASA; PLA amolece no sol. Camada de 0,2 mm, 4 paredes (ajuda a
  vedar), 20 a 30 % de enchimento.

## G-code pronto (Ender-3 V2, PLA)

Fatiado em 12/11/2026 com o CuraEngine do Cura 5.14 e o perfil "Standard
Quality" da Ender-3, pelo `fatiar.py` (os ajustes usados estão no começo dele):

| Arquivo | Tempo | Filamento | Suportes |
|---|---|---|---|
| `wifinder-mavic4pro-base-PLA.gcode` | 6 h 08 | 14,4 m (~43 g) | em árvore, mais aba de 8 mm |
| `wifinder-mavic4pro-tampa-PLA.gcode` | 2 h 29 | 6,3 m (~19 g) | nenhum (não há nada em balanço) |

PLA a 205 °C, mesa a 60 °C, camada de 0,2 mm, 4 paredes, 25 % de enchimento.
Na base, duas árvores sobem da mesa, do lado aberto da caixa, e seguram a
parede de trás (que é impressa como teto, a 78 mm de altura); há suportes
pequenos sob as divisórias. Se mudar uma medida no `suporte.py`, os STL
mudam e é preciso fatiar de novo.

## Antes de voar

- **Energia:** não confirmei que a USB-C do Mavic 4 Pro alimenta acessórios.
  Teste na bancada: drone ligado, ESP32 no cabo, tela acendendo.
- **GPS e bússola do drone:** o suporte fica em cima do drone. Faça um voo
  pairado baixo e veja se satélites e bússola continuam normais.
- **Peso:** caixa + placas + cabo dão perto de 90 g no topo do drone.
- Prenda o cabo USB para ele não chegar nas hélices.
