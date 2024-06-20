---
title: Função ACD – Acesso à dados
type: docs
weight: 1
---


# 1 - Descrição e Conceitos
O SIAD - Sistema Itaú de Acesso a Dados é um subsistema integrado ao GRBE, que tem por função disponibilizar o acesso dos programas aplicativos aos dados
armazenados em arquivos, tanto em ambientes online como em batch. Sua utilização permite a uma aplicação a não dependência de seus programas quanto a organizações
O SIAD, além de centralizar todas as operações de acesso a arquivos aplicativos, proporcionando independência em relação a sua organização, controla e garante a
integridade dos dados acessados concorrentemente em ambientes online. Através de processos de recuperação, o SIAD garante a consistência dos dados em casos de
interrupções imprevistas do processamento, de danos em periféricos ou de solicitação do próprio GRBE ou do aplicativo.

## 1.1 Acesso a Dados Online
Caracteriza-se pelo acesso a dados para leitura e atualização de informações de maneira rápida e direta, durante o processamento online, através de uma chave que
identifica um dado ou um conjunto de dados. O controle de acessos concorrentes a um mesmo dado mantém a integridade das informações, através de eficientes rotinas de
enfileiramento de recursos independentes das do sistema operacional

## 1.2 Acesso a Dados Batch
Caracteriza-se pelo acesso a dados para leitura, atualização e carga de informações, geralmente em grandes volumes, como preparação ao processamento
online. O acesso a dados em batch permite a tomada periódica de informações de controle, que possibilita o eventual processamento a partir de um ponto de sincronismo,
após uma interrupção não prevista, sem perda da integridade dos dados.

## 1.3 Utilização da Ponte Monitor
A PONTE MONITOR através da função de acesso a dados “ACD” faz a interface entre o programa de aplicação e o SIAD. Através de suas diversas funções e parâmetros
permite a execução de todas as operações de I/O disponíveis de maneira uniforme, independente do tipo e organização do arquivo.

## 1.4 Recuperação de Dados
Processo que garante a recuperação automática dos arquivos alterados num ciclo de I/O não completado com sucesso. Pode ser acionado após o término anormal de uma
transação individual, ou após um término anormal do GRBE.
Os dados para recuperação são tomados a cada alteração efetuada nos arquivos de aplicativos e gravados em um arquivo de recuperação, isto é, as imagens antes da alteração são gravadas no arquivo de recuperação. O arquivo de recuperação, em nível 5 de transação online, contém dados que dizem respeito somente às transações sendo processadas em determinado momento.

## 1.5 Alocação e Desalocação Dinâmica de Arquivos
Essa facilidade permite que arquivos de aplicativos sejam alocados ou desalocados durante o processamento online, sem que seja necessário desativar o monitor. Esse
recurso permite, por exemplo, que certas informações ainda não disponíveis para o processamento online não impactem a rede, retardando a sua inicialização, já que é
possível agregá-las mais tarde, com a rede em operação.

## 1.6 Arquivo VSAM-KSDS com Alternate Index
O SIAD permite o uso de AIX somente para leitura. Toda e qualquer alteração
deve ser feita acessando o índice principal. Para que essas alterações sejam refletidas
nos alternate index, é necessário codificar os parâmetros UPGRADE na criação do AIX e
UPDATE na criação do PATH.

## 1.7 Tipos de arquivos
O SIAD permite acesso aos seguintes tipos de arquivos:

* VSAM KSDS(KS)
* VSAM RRDS (RR)
* Acesso Direto (DA)
* Sequencial (PS)
* Sysout (SY)

## 1.6 Uso de tabela de DDNAME alternativo
É possível distribuir o conteúdo de um arquivo em vários arquivos menores, com base em um número (de agência, por exemplo) e em uma tabela associando este
número ao sufixo do ddname do arquivo a ser acessado.
Para isto ao executar a função ACD para acessar o arquivo, aplicação deve acrescentar no final do 2º parâmetro passado 2 campos: o nome da tabela
alternativa MTDAssxx (com 8 caracteres alfanuméricos) e o número a ser utilizado para pesquisa na tabela (com caracteres alfanuméricos ).
Antes de acessar o arquivo o SIAD vai pesquisar a tabela para obter o sufixo a ser acrescentado ao DDNAME.
A tabela deve ser montada com chamadas das macros MTGHTBvv e MTBALTvv

# 2 - Operações de I/O Disponíveis

## 2.1 Funções de Leitura
Um dos requisitos para que as solicitações de leitura sejam atendidas é que o aplicativo forneça uma área cujo tamanho seja compatível com o do registro a ser lido
(maior ou igual ao tamanho máximo do registro).

## 2.1.1 Função de Leitura comum com Chave (“LC “)
Essa função devolve, na área fornecida pelo programa chamador, o registro com a chave fornecida. Se um registro com a chave solicitada não for encontrado é
posicionado o código de retorno apropriado.

## 2.1.2 Função de Leitura prendendo o Registro (com Hold - “LCH“)
Essa função é similar à leitura comum com chave (função “LC “), com a diferença de que ela prende a chave antes da leitura, fazendo com que o registro lido fique preso
para a task até o final do ciclo de I/O. Os registro presos desta forma podem depois serem atualizados ou excluídos com a execução de outras funções. Ocorrendo erro na
leitura, é retornado o código de retorno correspondente, porém a chave do registro permanecerá presa para a task até o final do ciclo de I/O.

## 2.1.3 Função de Leitura comum com Chave Maior ou igual (“LCM“)
Essa função é similar à leitura comum com chave (função “LC “), com a diferença de que ela busca o registro com chave igual ou maior que a fornecida pelo programa
chamador.

## 2.1.4 Função de Leitura por chave Parcial (“LP “)
Essa função devolve, na área fornecida pelo programa chamador, o primeiro registro do arquivo com chave parcial igual à fornecida.
O tamanho da chave parcial deve ser, obrigatoriamente, menor que o tamanho da chave completa. Essa função pode ser seguida da função “LS “ para ler os demais registros sequenciais. Se nenhum registro com a chave solicitada não for encontrado é posicionado o código de retorno apropriado.

## 2.1.5 Função de Leitura de Início de sequência (“LI “)
Esse tipo de leitura tem a função de informar ao método de acesso que essa é a primeira de uma série de leituras sequenciais ao arquivo. Essa função faz com que o
arquivo seja posicionado no registro com a chave fornecida além de ser lido. As leituras sequenciais seguintes devem ser feitas através da função “LS “.

## 2.1.6 Função de Leitura de Início de sequência por chave Anterior (“LIA“)
Essa função é similar à leitura de início de sequência (função “LI “), com a diferença de que as próximas leituras sequenciais serão para trás (pegarão chaves anteriores à
última chave lida). As leituras sequenciais seguintes devem ser feitas através da função “LA “.

## 2.1.7 Função Leitura de Início de sequência com chave Maior ou igual (“LIM“)
Essa função é similar à leitura de início de sequência (função “LI “), com a diferença de que ela faz com que o arquivo seja posicionado no registro com a chave maior ou
igual à fornecida. As leituras sequenciais seguintes devem ser feitas através da função “LS “.

## 2.1.8 Função de Leitura Sequencial (“LS “)
Para arquivos VSAM, essa função devolve, na área fornecida pelo programa chamador, o registro sequencial ao obtido numa chamada anterior de início de
sequência, de leitura por chave parcial ou de leitura sequencial no mesmo arquivo. A sequência deve, obrigatoriamente, ter sido iniciada através de uma leitura de início de
sequência para frente (função “LI “ ou “LIM”) ou de leitura por chave parcial (função “LP“).
Para arquivos PS, essa função devolve, na área fornecida pelo programa chamador, o primeiro registro do arquivo (caso seja a primeira leitura) ou o registro
sequencial ao obtido numa chamada anterior de leitura sequencial no mesmo arquivo.

## 2.1.9 Função de Leitura sequencial de chave Anterior (“LA “)
Essa função é similar à leitura sequencial (função “LS “) para arquivos VSAM, com a diferença de que ela devolve o registro sequencial com chave anterior. A sequência
deve, obrigatoriamente, ter sido iniciada através de uma leitura de início de sequência para trás (função “LIA“). Se o último registro lido já era o primeiro registro do arquivo, é
posicionado o código de retorno apropriado.

## 2.1.10 Função de Leitura sKip sequencial (“LK “)
Essa função devolve, na área fornecida pelo programa chamador, o registro de chave igual à fornecida. Esse tipo de leitura posiciona o arquivo na chave requisitada
fazendo com que a busca por uma chave seguinte seja feita a partir dessa posição. Caso o arquivo esteja posicionado após a chave requisitada, será devolvido código de retorno
indicando erro de I/O.

## 2.1.11 Função de Leitura sKip sequencial com chave Maior ou igual (“LKM“)
Essa função é similar à leitura skip sequencial (função “LK “), com a diferença de que ela devolve, na área fornecida pelo programa chamador, o registro de chave maior
ou igual à fornecida.

## 2.2 Função de Atualização com chave, com ou sem recuperação (“A” ou “AF“)
A chamada a essa função deve ter sido precedida por uma chamada de leitura prendendo o registro (função “LCH”). O registro é alterado e permanece preso até o final
do ciclo de I/O.
A chave fornecida deve ser idêntica à chave dentro do registro. A função AF é similar a função A, com a diferença de que ela não grava SYSREC o
que invalida a utilização das funções de finalização do ciclo de I/O (REC e LIB).

## 2.3 Função de Exclusão com chave, com ou sem recuperação (“E” ou “EF”)
A operação de exclusão de um registro pode ou não ser precedida por uma leitura prendendo a chave (função “LCH”). Caso o registro não tenha sido preso anteriormente,
ele é preso durante a chamada dessa função. O registro permanece preso para a task até o final do ciclo de I/O, independentemente da exclusão ser ou não bem sucedida.
A função EF é similar a função E, com a diferença de que ela não grava SYSREC o que invalida a utilização das funções de finalização do ciclo de I/O (REC e LIB).

## 2.4 Funções de Inclusão

## 2.4.1 Função de Inclusão com chave, com ou sem recuperação (“I”ou “IF”)
A operação de inclusão de um registro com chave pode ou não ser precedida por uma leitura prendendo a chave (função “LCH”). Caso o registro não tenha sido preso
anteriormente, ele é preso durante a chamada dessa função. O registro permanece preso para a task até o final do ciclo de I/O, independentemente da inclusão ser ou não
bem sucedida.
A função IF é similar a função I, com a diferença de que ela não grava SYSREC o que invalida a utilização das funções de finalização do ciclo de I/O (REC e LIB).

## 2.4.2 Função de Inclusão sequencial com ou sem recuperação (“IS” ou “ISF”)
O SIAD determina qual a próxima chave disponível no arquivo para fazer a Inclusão, e move a mesma para a posição correta na área do registro fornecida pela
aplicação antes de incluí-lo. A chave permanecerá presa para a task até o final do ciclo de I/O, independentemente da inclusão ter sido ou não bem sucedida.
Para inclusão sequencial de registro em arquivos SYSOUT, o primeiro byte do registro fornecido deve conter um caractere de controle de impressão válido.
A função IS é similar a função ISF, com a diferença de que ela não grava SYSREC o que invalida a utilização das funções de finalização do ciclo de I/O (REC e LIB).

## 2.5 Funções de Finalização
As funções de finalização permitem que a aplicação encerre um ciclo de I/O antes do final de uma transação. Com a finalização de um ciclo, é iniciado um novo ciclo que
permanecerá até o fim da transação ou outra chamada da uma função de finalização. Se a aplicação não chamar nenhuma função de finalização, o ciclo de I/O termina
apenas no final da transação.
Obs.: Quando a aplicação peda a geração de uma nova transação com “K”, o ciclo de I/o não é encerrado.

## 2.5.1 Finaliza ciclo de I/O LIBerando (“LIB“ )
Esta operação efetiva todos os I/Os de registros alterados, incluídos ou excluidos, emite commit para efetivar leituras e gravações em filas MQ e emite commit no DB2, se
os mesmos foram acessados. A partir desse momento, é iniciado um novo ciclo de I/O que será encerrado ao fim da transação, ou em nova chamada da função LIB ou REC.

## 2.5.2 Finaliza ciclo de I/O RECuperando (“REC“ )
Esta operação desfaz todos os I/Os de registros alterados, incluídos ou excluídos, e emite rollback no DB2 e/ou MQ se eles foram utilizados. A partir desse momento, é
iniciado um novo ciclo de I/O que será encerrado ao fim da transação, ou em nova chamada da função LIB ou REC.

# 3 - Operações de I/O Permitidas
As operações de I/O aceitas e tratadas pelo SIAD dependem da organização e do atributo do arquivo, conforme segue:
| Código Função | PS | SYSOUT | BDAM | VSAM-RRDS | VSAM-KSDS |
| --- | --- | --- | --- | --- | --- |
| A | | | UPD | UPD | UPD |
| AF | | | UPD | UPD | UPD |
| E | | | UPD | UPD | UPD |
| EF | | | UPD | UPD | UPD |
| I | | | UPD | UPD | UPD |
| IF | | | UPD | UPD | UPD |
| IS | UPD | OK | | UPD | |
| ISF | | | | UPD | |
| LA | | | | | OK |
| LC | | | OK | OK | OK |
| LCH | | | UPD | UPD | UPD |
| LCM | | | | | OK |
| LI | | | | OK | OK |
| LIA | | | | | OK |
| LIM | | | | OK | OK |
| LK | | | | | OK |
| LKM | | | | | OK |
| LP | | | | | OK |
| LS | RO | | | OK | OK |
---
RO: Função válida para arquivo com atributo Read-Only (LEITURA).
UPD: Função válida para arquivo com atributo UPDATE (ATUALIZAÇÃO).
OK: Função válida para o arquivo, independentemente do atributo.

# 4 - Descrição dos Parâmetros
Todas as funções de acesso a arquivos devem ter um primeiro parâmetro da Ponte MONITOR especificando a função “ACD”
| 3 Bytes | Código da função da Ponte MONITOR.ACD - Acesso a Dados |
| --- | --- |
| 1 Byte | Código de Retorno da Ponte MONITOR |
| 8 Bytes | Recurso. Deve ser preenchido com “SIAD “. |
---
A seguir descrevemos os demais parâmetro necessários, conforme a função solicitada:

## 4.1 Funções de Leitura

### **Segundo Parâmetro**
| 3 Bytes | (0-1) |
| --- | --- |
| 1 byte | Código de Retorno. |
| 8 bytes | DDname; deve ser preenchido com brancos à direita. |
| 2 Bytes | (3-1) |
| 2 Bytes | Tamanho da Chave Parcial em bytes. É utilizado apenas em Funções de leitura por chave parcial (LP). |
---
> (0-1) Código da função.LA Leitura sequencial de chave AnteriorLC Leitura Comum com chaveLCH Leitura Comum com chave e com HoldLCM Leitura Comum com chave Maior ou igualLI Leitura de Início de sequênciaLIA Leitura de Início de sequência por chave AnteriorLIM Leitura de Início de sequência com chave Maior ou igualLK Leitura sKip-sequencialLKM Leitura sKip-sequencial com chave Maior ou igualLP Leitura por chave Pa

> (3-1) No caso de arquivos VSAM este campo é usado para retornar o tamanho doregistro lido:Se arquivo VSAM Read Only: SIAD retorna o LRECL.Se arquivo VSAM não Read Only: SIAD retorna o LRECL-10.Nos demais casos, o programa de aplicação deve informar o tamanho daárea de dados para conter o registro.

### Terceiro Parâmetro
| "n" Bytes | (0-1) |
| --- | --- |
---
> (0-1) Chave para de pesquisa do registro em questão, ou a chave parcial (completadacom zeros binários) para leitura por chave parcial (LP). N é o tamanho da chaveem bytes, que pode ter até 255 bytes.Para arquivos DA ou VSAM RRDS, a chave deve estar em formato compactado,com tamanho de até 8 bytes.Nas funções LS e LA este parâmetro é desprezado.

### Quarto Parâmetro
| Área de Dados |
| --- |
| Tamanho | Tipo de arquivo |
| N>=LRECL | Para arquivos VSAM Read Only. |
| N>=LRECL-10 | Para arquivos VSAM não Read Only. |
| N=BLKSIZE-10 | Para arquivos de organização direta (DA). |
| N=LRECL | Para arquivos sequenciasi (PS). |
---

## 4.2 Funções de Inclusão

### Segundo Parâmetro
| 3 Bytes | Código da função.I Inclusão com chaveIF Inclusão com chave (SEM SYSREC)IS Inclusão SequencialISF Inclusão Sequencial (SEM SYSREC) |
| --- | --- |
| 1 Byte | Código de Retorno. |
| 8 bytes | DDname; deve ser preenchido com brancos à direita. |
| 2 Bytes | (3-1) |
| 2 Bytes | Tamanho da chave parcial. Este campo não é utilizado nesta função |
---
> (3-1) Tamanho da área que contem o registro a ser incluído.Para arquivos PS: N = LRECLPara arquivos DA: N = BLKSIZE-10Para arquivos VSAM: (RKP+KEYLEN-10) <= N <= LRECL-10

### Terceiro Parâmetro
| "n" Bytes | (0-1) |
| --- | --- |
---
> (0-1) Chave do registro a ser incluido. N é o tamanho da chave em bytes, que pode ter até 255 bytes.Para arquivos DA ou VSAM RRDS, a chave deve estar em formato compactado, com tamanho de até 8 bytes.Na função IS, o SIAD retorna, nesse campo, a chave que ele atribuiu aoregistro (se arquivo DA ou RRDS, retorna no formato compactado).
Observação
 1) Na Inclusão Seqüencial o SIAD devolve neste campo a chave que ele forneceu ao registro.
2) Para Inclusão Seqüencial o campo chave do arquivo deve sempre estar no formato compactado e ter 4 bytes de tamanho.

### Quarto Parâmetro
| Área de Dados |
| --- |
| Tamanho | Tipo de arquivo |
| (RKP+KEYLEN-10) <= N <= LRECL-10 | Para arquivos VSAM. |
| N=BLKSIZE-10 | Para arquivos de organização direta (DA). |
| N=LRECL | Para arquivos sequenciasi (PS). |
---
Observação
 1)) Quando o arquivo for SYSOUT (DSORG=SY), o primeiro byte deve ser o controle de carro para a impressão: Pode ser:
" " = grava o registro na sysout
"0" = pula 1 linha e grava o registro na sysout
"1" = pula 1 página e grava o registro na sysout

## 4.3 Função de Exclusão

### Segundo Parâmetro
| 3 Bytes | Código da função.E ExclusãoEF Exclusão (SEM SYSREC) |
| --- | --- |
| 1 Byte | Código de Retorno. |
| 8 bytes | DDname; deve ser preenchido com brancos à direita. |
| 2 Bytes | Este campo não é utilizado nesta função. |
| 2 Bytes | Este campo não é utilizado nesta função. |
---

### Terceiro Parâmetro
| "n" Bytes | (0-1) |
| --- | --- |
---
> (0-1) Chave do registro a ser incluido. N é o tamanho da chave em bytes, que pode ter até 255 bytes.Para arquivos DA ou VSAM RRDS, a chave deve estar em formato compactado, com tamanho de até 8 bytes.

## 4.4 Função de Alteração

### Segundo Parâmetro
| 3 Bytes | Código da função.A AlteraçãoAF Alteração (SEM SYSREC) |
| --- | --- |
| 1 Byte | Código de Retorno. |
| 8 bytes | DDname; deve ser preenchido com brancos à direita. |
| 2 Bytes | Tamanho da área que contem o registro a ser alterado.Para arquivos DA: N = BLKSIZE-10Para arquivos VSAM: (RKP+KEYLEN-10) <= N <= LRECL-10 |
| 2 Bytes | Este campo não é utilizado nesta função. |
---

### Terceiro Parâmetro
| "n" Bytes | (0-1) |
| --- | --- |
---
> (0-1) Chave do registro a ser incluido. N é o tamanho da chave em bytes, que pode ter até 255 bytes.Para arquivos DA ou VSAM RRDS, a chave deve estar em formato compactado, com tamanho de até 8 bytes.

### Quarto Parâmetro
| Área de Dados |
| --- |
| Tamanho | Tipo de arquivo |
| (RKP+KEYLEN-10) <= N <= LRECL-10 | Para arquivos VSAM. |
| N=BLKSIZE-10 | Para arquivos de organização direta (DA). |
---

## 4.5 Funções de Finalização

### Segundo Parâmetro
| 3 Bytes | Código da função.LIB Final LiberarREC Final Recuparação ( ou Desfazer) |
| --- | --- |
| 1 Byte | Código de Retorno. |
---

## 5 Códigos de Retorno
O código de retorno da função vem no quarto byte do segundo parâmetro. Este pode conter os seguintes valores:
| Cód. retorno | Descrição |
| --- | --- |
| A | Término normal |
| B | Função inválida |
| C | Arquivo não foi aberto ou incosistente |
| D | Id-registro (DDNAME) incorreto |
| E | Arquivo está fechado |
| F | Não existe registro com a chave fornecida |
| G | Já existe registro com a chave fornecida |
| H | Tamanho da área fornecida incompatível com LRECL do arquivo |
| I | Erro irrecuperável de I/O |
| J | Erro no processamento da tabela de DDNAMEs alternativos |
| K | Controle de carro inválido (SYSOUT) |
| L | Arquivos do sistema de aplicação não foram gravados, transação não completada e arquivos recuperados |
| N | Chave passada não está no formato decimal compactado |
| O | Chave fornecida diferente da chave na área de dados |
| P | Registro fora do arquivo |
| Q | SIAD em inicialização. Arquivos ainda fechados |
| R | Possível deadlock envolvendo o registro com a chave fornecida |
| S | Falta de espaço correspondente à task no arquivo de recuperação para efetuar a gravação solicitada |
| T | Falta de memória virtual para processar esta chamada |
| U | Tamanho da chave parcial incorreto (menor que 1 ou maior ou igual a keylen) |
| V | Falta de espaço no arquivo de recuperação para processar o número de tasks concorrentes especificado |
| W | Fim de arquivo durante uma leitura (arquivo VSAM) |
| X | Transação deverá sofrer abend |
| Y | Registro tem chave múltipla |
| 1 | Fim de arquivo durante uma leitura (arquivo PS) |
| 3 | Chamada não autorizada, arquivo protegido por RACF e acesso feito por programa ou subprograma não autorizado |
| 4 | Memória indisponível para arquivo BDAM em memória |
| 5 | Tabela de arquivos (MTDD) em "reset" |
| 6 | Atingido limite de leituras com hold por recovery unit para arquivos TVS |
| 7 | Atingido limite de atualizações por recovery unit para arquivos TVS |
| 8 | Erro grave no notepad |
---
 (1) Alguns arquivos críticos cadastrados na Classe $DSNCRIT do RACF só podem ser acessados por subprogramas autorizados.
Para o cadastro de novos profiles (arquivos ou subprogramas) favor entrar em contato com o grupo de suporte aos monitores Banco Eletrônico.
Relação dos códigos de retorno possíveis para cada Função:
| Cód.Função | A | B | C | D | E | F | G | H | I | J | K | L | M | N | O | P | Q | R | S | T | U | V | W | X | Y | Z | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LA | A | B | | D | E | F | | H | I | J | | | | | | | Q | | | T | | | W | X | Y | | | | 3 | | 5 | | | |
| LC | A | B | | D | E | F | | H | I | J | | | | N | | P | Q | | | T | | | | X | | | | | 3 | 4 | 5 | | | |
| LCH | A | B | | D | E | F | | H | I | J | | | | N | | P | Q | R | | T | | | | X | | | | | 3 | 4 | 5 | 6 | | |
| LCM | A | B | | D | E | F | | H | I | J | | | | | | | Q | | | T | | | | X | | | | | 3 | | 5 | | | |
| LI | A | B | | D | E | F | | H | I | J | | | | N | | | Q | | | T | | | | X | Y | | | | 3 | | 5 | | | |
| LIA | A | B | | D | E | F | | H | I | J | | | | | | | Q | | | T | | | | X | Y | | | | 3 | | 5 | | | |
| LIM | A | B | | D | E | | | H | I | J | | | | N | | | Q | | | T | | | W | X | Y | | | | 3 | | 5 | | | |
| LK | A | B | | D | E | F | | H | I | J | | | | | | | Q | | | T | | | | X | Y | | | | 3 | | 5 | | | |
| LKM | A | B | | D | E | | | H | I | J | | | | | | | Q | | | T | | | W | X | Y | | | | 3 | | 5 | | | |
| LP | A | B | | D | E | F | | H | I | J | | | | | | | Q | | | T | U | | | X | Y | | | | 3 | | 5 | | | |
| LS | A | B | | D | E | F | | H | I | J | | | | | | | Q | | | T | | | W | X | Y | | 1 | | 3 | | 5 | | | |
| I | A | B | | D | E | | G | H | I | J | | | | N | O | P | Q | R | S | T | | | | X | | | | | 3 | 4 | 5 | 6 | | |
| IS | A | B | | D | E | | | H | I | J | K | | | N | | | Q | R | S | T | | | | X | | | | | 3 | | 5 | 6 | | 8 |
| E | A | B | | D | E | F | | | I | J | | | | N | | P | Q | R | S | T | | | | X | | | | | 3 | 4 | 5 | 6 | | |
| A | A | B | | D | E | F | | H | I | J | | | | N | O | P | Q | R | S | T | | | | X | | | | | 3 | 4 | 5 | 6 | | |
| LIB | A | | C | | | | | | | | | L | | | | | Q | | | | | | | X | | | | | | | | | | |
| REC | A | | C | | | | | | | | | | | | | | Q | | | | | | | X | | | | | | | | | | |
---
Exemplo de utilização da função XXX
 ## 6 Exemplos
Seguem 2 exemplos de utilização da ponte MONITOR para acesso a arquivos. O primeiro na linguagem COBOL e o segundo em ASSEMBLER /370.

## 6.1 Cobol
O exemplo faz chamadas à ponte MONITOR para efetuar operações de I/O num arquivo de aplicação, conforme dados passados por outro programa.
```
DATA DIVISION
WORKING-STORAGE SECTION.
77 WA PIC XXX VALUE 'A '.
77 WI PIC XXX VALUE 'I '.
77 WE PIC XXX VALUE 'E '.
77 WLCH PIC XXX VALUE 'LCH'.
01 WDADOS.
03 WCONTA PIC 9(10).
03 WVALOR PIC 9(08).
03 WRESTO PIC 9(10).
01 WXCONTA PIC 9(08).
01 WPONTE.
03 P_FUNCAO PIC X(03) VALUE 'ACD'.
03 P_CODIGO-RETORNO PIC X.
03 P_ENTIDADE PIC X(08) VALUE 'SIAD '.
01 WCONTROLE.
03 FUNCAO PIC X(03).
03 CODIGO-RETORNO PIC X.
03 IDENT-ARQUIVO PIC X(08) VALUE 'SYS001 '.
03 TAMANHO-DADOS PIC S99 COMP VALUE 28.
03 TAM-CHAVE-PARC PIC S99 COMP VALUE 0.
LINKAGE SECTION.
01 LINK-COD-RETORNO PIC X.
01 DADOS.
03 CONTA PIC 9(10).
03 VALOR PIC 9(08).
03 RESTO PIC 9(10).
PROCEDURE DIVISION USING DADOS.
LER.
 MOVE WLCH TO FUNCAO.
 CALL 'MONITOR' USING WPONTE WCONTROLE CONTA WDADOS.
 IF CODIGO-RETORNO = 'F'
 THEN GO TO INCLUIR.
 IF CODIGO-RETORNO NOT = 'A'
 THEN DISPLAY '+PROG.001I ERRO DE LEITURA CHAVE' CONTA
 MOVE 1 TO LINK-COD-RETORNO
 GOBACK.
ATUALIZAR.
 IF VALOR = 0 THEN GO TO EXCLUIR.
 ADD VALOR TO WVALOR.
 MOVE WA TO FUNCAO.
 CALL 'MONITOR' USING WPONTE WCONTROLE WCONTA WDADOS.
 IF CODIGO-RETORNO NOT = 'A'
 THEN DISPLAY '+PROG.001I ERRO DE ATUALIZACAO CHAVE' CONTA
 MOVE 2 TO LINK-COD-RETORNO
 GOBACK.
 GO TO FIM.
INCLUIR.
 MOVE CONTA TO WXCONTA.
 MOVE WI TO FUNCAO.
 CALL 'MONITOR' USING WPONTE WCONTROLE WXCONTA DADOS.
 IF CODIGO-RETORNO NOT = 'A'
 THEN DISPLAY '=PROG.001I ERRO DE INCLUSAO CHAVE' CONTA
 MOVE 3 TO LINK-COD-RETORNO
 GOBACK.
 GO TO FIM.
EXCLUIR.
 MOVE WE TO FUNCAO.
 CALL 'MONITOR' USING WPONTE WCONTROLE CONTA.
 IF CODIGO-RETORNO NOT = 'A'
 THEN DISPLAY '=PROG.001I ERRO DE EXCLUSAO CHAVE' CONTA
 MOVE 4 TO LINK-COD-RETORNO
 GOBACK.
FIM.
 MOVE 0 TO LINK-COD-RETORNO.
 DISPLAY '=PROG.001I FIM NORMAL DE PROGRAMA'.
```

## 6.2 Assembler
O exemplo faz chamadas à ponte MONITOR para efetuar operações de I/O num arquivo de aplicação, conforme dados contidos num outro arquivo.
```
EXEMPLO START 0
 XENTRY
 OPEN (ENTRADA,,SAIDA,(OUTPUT))
* LEITURA DE DADOS DE ENTRADA
LEDADOS EQU *
 GET ENTRADA,AREAENT
 MVC FUNCAO,AREAENT
 MVC ARQUIVO,AREAENT+3
 MVC CHAVE,AREAENT+11
 PACK TAMAUX,AREAENT+17(02)
 CVB R2,TAMAUX
 STH R2,TAMAREA
 BCTR R2,0
 EX R2,MVCDADOS
*
 PACK TAMAUX,AREAENT=19(02)
 CVB R2,TAMAUX
 STH R2,TAMCHAVP
*
 CALL MONITOR,(PONTE,CONTROLE,CHAVE,AREA)
 SNAP DCB=SAIDA,STORAGE=(AREAENT,MVCDADOS)
 B LEDADOS
FIM EQU *
 CLOSE (ENTRADA,,SAIDA)
 XRETURN
* AREAS UTILIZADAS PELO PROGRAMA EXEMPLO
 DS OF
AREAENT DS CL80
AREA DS CL100
CHAVE DS CL6
PONTE DS OF
PFUNCAO DC CL3’ACD’
PCODRET DC CL1
PENTIDD DC CL8’SIAD’
CONTROLE DS OF
FUNCAO DS CL3
CODRETRN DS CL1
ARQUIVO DS CL8
TAMAREA DS H
TAMCHAVP DS H
TAMAUX DS CL8
MVCDADOS MVC AREA(0),AREAENT+21
* DEFINICAO DE ARQUIVOS
ENTRADA DCB ...
SAIDA DCB EODAD=FIM...
 END EXEMPLO
```
