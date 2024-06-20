---
title: Função CAM - Consulta Áreas do Monitor
type: docs
weight: 1
---


# 1 - Descrição e Conceitos
Essa função permite que uma aplicação sob GRBE obtenha informações à respeito do monitor, sistema e task em que esta executando.

# 2 - Descrição dos Parâmetros

## 2.1 Primeiro Parâmetro
O aplicativo devera chamar a função "CAM" através da ponte "MONITOR", passando os seguintes parâmetros:
| 1 Byte | Return-Code da Ponte |
| --- | --- |
| 3 Bytes | Código da função da Ponte MONITOR – “CAM”. |
| 8 Bytes | Entidade, deve ser preenchido com “GRBE “ |

## 2.2 Segundo Parâmetro
| 1 Byte | Return-Code da Função |
| --- | --- |
| 3 Bytes | (1-1) |
| 4 Bytes | Fixo: 4 Bytes com brancos |
| 8 Bytes | Tamanho da área para receber o LPARAM4 (apenas para opção “COM”) |
!!! \*\*(1-1)\*\*:
> Opção da chamada:TRA Dados da TransaçãoCOM Dados da Área de Comunicação GRBE-Aplicação (LPARAM4)TER Dados do TerminalGMT Horário GMTBRANCOS Dados do GRBE e task
## 2.3 Terceiro Parâmetro
O terceiro parâmetro depende da opção da chamada (descritos no segundo parâmetro):

**OPÇÃO = BRANCOS**
Essa área deverá conter 30 bytes.
Se não foi solicitado a opção no segundo parâmetro (ficou com “brancos”), serão
devolvidas as seguintes informações sobre o GRBE e a Task:
| 8 Bytes | Applid do monitor onde a aplicação está executando. |
| --- | --- |
| 3 Bytes | Versão do GRBE nesse monitor |
| 4 Bytes | Computador onde esse monitor executa. |
| 2 Bytes | Id da task em hexadecimal |
| 2 Bytes | Id task em decimal nao utilizado mais |
| 8 bytes | Indica nome applid real |
| 3 Bytes | Filler |
| 8 Bytes | Applid do monitor onde a aplicação está executando |
| 3 Bytes | Versão do GRBE nesse monitor |
| 4 Bytes | Computador onde esse monitor executa. |
| 4 Bytes | Id da task em 4 bytes. |
| 8 Bytes | Indica nome applid real |
| 3 Bytes | Filler |

**OPÇÃO = TRA**
Essa área deverá conter 35 bytes.
Essa opção irá devolver as mesmas informações da opção branco, acrescentando o
nome da transação e o nome do programa:
| 8 Bytes | Applid do monitor onde a aplicação está executando. |
| --- | --- |
| 3 Bytes | Versão do GRBE nesse monitor |
| 4 Bytes | Computador onde esse monitor executa. |
| 2 Bytes | Id da task em hexadecimal. |
| 2 Bytes | Id da task em decimal, valido apenas para tasks de processamento. |
| 8 Bytes | Nome da transação |
| 8 Bytes | Nome do programa |

**OPÇÃO = COM**
O 3º parâmetro para a opção "COM" deverá indicar o início de uma área na workingstorage do programa onde será copiada a Área de Comunicação GRBE-Aplicação
(LPARAM4, também conhecida como 4ª área). O tamanho dessa área deverá ser sempre informado no último campo (8 bytes zonados) do 2º parâmetro.
O GRBE moverá a cópia da área para a área destino da aplicação se o tamanho for igual, maior ou menor. Se o tamanho for menor que o esperado a cópia será truncada.
Mudanças feitas nesta cópia da 4ª área não terão reflexo na 4ª área original.
| --- | Início da área na working-storage destinada para a cópia da 4ª área (LPARAM4), com o tamanho fornecido no segundo parâmetro. |
| --- | --- |

**OPÇÃO = TER**
Essa área deverá conter 40 bytes. Essa opção irá devolver várias informações sobre o terminal que solicitou a transação em execução:
| 8 Bytes | Nome lógico do terminal |
| --- | --- |
| 6 Bytes | Número da entrada do terminal |
| 6 Bytes | Tipo de terminal (ttffoo) |
| 5 Bytes | Número de série do terminal |
| 4 Bytes | Número sequencial da mensagem |
| 1 Byte | Tempo da última transação |
| 4 Bytes | Número sequencial da mensagem anterior |
| 1 Byte | Tempo da transação anterior |
| 4 Bytes | Tamanho do buffer |
| 1 Byte | Filler |

**OPÇÃO = GMT**
Essa área deverá conter 8 bytes (double) e trará a data/ hora GMT.
| 8 Bytes | data/hora GMT |
| --- | --- |

# 3 - Códigos de Retorno
| Código de Retorno | Descrição |
| --- | --- |
| A | Processamento Normal. Foi completado o processamento solicitado com sucesso.Tamanho passado pela aplicação e tamanho da 4ª área são iguais. |
| B | (2-1) |
| C | (3-1) |
| D | Ocorreu erro no processamento. Foi solicitado opção "COM" e o tamanhoinformado é igual a ZEROS. |
| E | Ocorreu erro no processamento. Foi solicitado opção "COM" e o tamanhoinformado é inválido. |
!!! \*\*(2-1)\*\*:
> Processamento Normal. Foi solicitado opção "COM" e o tamanho passadopela aplicação é MENOR do que o tamanho da 4ª área, que é copiada etruncada de acordo com o tamanho especificado pela aplicação.
!!! \*\*(3-1)\*\*:
> Processamento Normal. Foi solicitado opção "COM" e o tamanho passadopela aplicação é MAIOR do que o tamanho da 4ª área, que é copiada como seu tamanho correto
Observação
 1. No primeiro parâmetro está o código de retorno da ponte "MONITOR" informando o status de processamento da ponte.
2. O código acima retorna no segundo parâmetro

# 4 - Exemplos

## 4.1 Exemplo 1
Exemplo de uma aplicação que esta' executando no monitor SP01 e na task de processamento de ID "0A".
```
DATA DIVISION
 *** AREA PARA A PONTE MONITOR ***
 01 WMONIT.
 03 WMONIT-FUN PIC X(03).
 03 WMONIT-RC PIC X(01).
 03 WMONIT-NOME PIC X(08).
 *** AREA PARA CAM - PARAM 2 ***
 01 WPARAM2.
 03 WPARAM2-OPCAO PIC X(03).
 03 WPARAM2-RC PIC X(01).
 03 WPARAM2-REC PIC X(04).
 *** AREA PARA CAM - PARAM 3 ***
 01 WPARAM3.
 03 WPARAM3-APPLID PIC X(08).
 03 WPARAM3-VERSAO PIC X(03).
 03 WPARAM3-SIST PIC X(04).
 03 WPARAM3-IDTK PIC X(02).
 03 WPARAM3-IDTKD PIC X(02).
 03 WPARAM3-FILLER PIC X(11).
 PROCEDURE
 *** OBTER INFORMACOES DO MONITOR ***
 MOVE 'CAM' TO WMONIT-FUN.
 MOVE 'GRBE ' TO WMONIT-NOME.
 MOVE ' ' TO WMONIT-RC.
 MOVE ' ' TO WPARAM2-OPCAO.
 MOVE ' ' TO WPARAM2-RC.
 MOVE ' ' TO WPARAM2-REC.
 CALL 'MONITOR' USING WMONIT WPARAM2 WPARAM3
 IF WMONIT-RC NOT EQUAL 'A'
 OR WPARAM2-RC NOT EQUAL 'A'
 PERFORM ROTERRMO.
 * VALORES QUE ESTARIAM NO WPARAM3 APOS A CHAMADA DA PONTE *
 * DE ACORDO COM O EXEMPLO CITADO ACIMA. *
 WPARAM3-APPLID ---> AGENSP01 (applid do monitor)
 WPARAM3-VERSAO ---> 52B (versao do grbe)
 WPARAM3-SIST ---> SECC (computador em que esse GRBE executa)
 WPARAM3-IDTK ---> 0A (id da task - hexadecimal)
 WPARAM3-IDTKD ---> 10 (id da task em decimal)
```

## 4.2 Exemplo 2
Exemplo de uma aplicação que necessita de uma cópia da 4ª área
```
DATA DIVISION
 *** AREA PARA A PONTE MONITOR ***
 01 WMONIT.
 03 WMONIT-FUN PIC X(03).
 03 WMONIT-RC PIC X(01).
 03 WMONIT-NOME PIC X(08).
 03 WMONIT-ENDTAB PIC X(04).
 *** AREA PARA CAM - PARAM 2 ***
 01 WPARAM2.
 03 WPARAM2-OPCAO PIC X(03).
 03 WPARAM2-RC PIC X(01).
 03 WPARAM2-REC PIC X(08).
 03 WPARAM2-TAM REDEFINES WPARAM2-REC.
 05 WPARAM2-TAMAREA PIC 9(08).
 *** INÍCIO DA AREA PARA CÓPIA DA LPARAM4 - PARAM 3 ***
 01 W77-PARAM4. ---> Início da área p/ cópia do LPARAM4
 PROCEDURE
 *** OBTER INFORMACOES DO MONITOR ***
 MOVE 'CAM' TO WMONIT-FUN.
 MOVE 'GRBE ' TO WMONIT-NOME.
 MOVE ' ' TO WMONIT-RC.
 MOVE 'COM' TO WPARAM2-OPCAO.
 MOVE ' ' TO WPARAM2-RC.
 MOVE 150 TO WPARAM2-TAMAREA.
 CALL 'MONITOR' USING WMONIT WPARAM2 WPARAM3
 IF WMONIT-RC NOT EQUAL 'A'
 OR WPARAM2-RC NOT EQUAL 'A'
 PERFORM ROTERRMO.
 * VALORES QUE ESTARIAM NO WPARAM3 APOS A CHAMADA DA PONTE *
 * DE ACORDO COM O EXEMPLO CITADO ACIMA .
*
 WPARAM2-TAMAREA ---> 150 (tamanho da área p/ LPARAM4)
 W77-LPARAM4 ---> Estará a cópia da 4ª área (LPARAM4)
```
