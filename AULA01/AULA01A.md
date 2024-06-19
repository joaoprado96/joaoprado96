# Virtualização, Containers, Docker

## Índice

1. [Introdução](#introdução)
2. [Virtualização](#virtualização)
    - [Definição](#definição)
    - [Tipos de Virtualização](#tipos-de-virtualização)
    - [Benefícios](#benefícios)
3. [Containers](#containers)
    - [Definição](#definição-1)
    - [Comparação com Máquinas Virtuais](#comparação-com-máquinas-virtuais)
    - [Benefícios](#benefícios-1)
4. [Docker](#docker)
    - [Definição](#definição-2)
    - [Componentes Principais do Docker](#componentes-principais-do-docker)
    - [Como o Docker Funciona](#como-o-docker-funciona)
    - [Benefícios do Docker](#benefícios-do-docker)
5. [Casos de Uso](#casos-de-uso)
7. [Conclusão](#conclusão)
8. [Recursos Adicionais](#recursos-adicionais)

## Introdução

- **Objetivo da Apresentação**
  - Compreender os conceitos de virtualização e containers
  - Explorar a tecnologia Docker

## Virtualização

### Definição
- Virtualização é o processo de criar uma versão virtual (em vez de real) de algo, como um sistema operacional, um servidor, um dispositivo de armazenamento ou recursos de rede. Isso permite que vários sistemas ou aplicativos sejam executados de forma independente em um único hardware físico.

### Tipos de Virtualização

#### Virtualização de Servidores
- **Definição**: Permite que múltiplos sistemas operacionais sejam executados em uma única máquina física, criando várias máquinas virtuais (VMs) que compartilham os recursos do hardware físico.
- **Como Fazer**:
  - Utilizar um hipervisor, que é um software de virtualização que permite a criação e gerenciamento de VMs.
  - Dois tipos de hipervisores: Tipo 1 (bare-metal) e Tipo 2 (hospedado).
    - **Tipo 1**: Executa diretamente no hardware (ex.: VMware ESXi, Microsoft Hyper-V, XenServer).
    - **Tipo 2**: Executa sobre um sistema operacional (ex.: VMware Workstation, Oracle VirtualBox).
- **Principais Produtos de Mercado**:
  - VMware vSphere/ESXi
  - Microsoft Hyper-V
  - Citrix XenServer
  - Oracle VM VirtualBox

#### Virtualização de Rede
- **Definição**: Abstrai os recursos de rede para que vários dispositivos e serviços de rede possam ser gerenciados como uma única unidade, independentemente da localização física.
- **Como Fazer**:
  - Utilizar tecnologias como VLANs (Virtual Local Area Networks), VXLANs (Virtual Extensible LAN), e SDN (Software-Defined Networking).
  - Ferramentas de virtualização de rede como switches virtuais e roteadores virtuais.
- **Principais Produtos de Mercado**:
  - VMware NSX
  - Cisco ACI (Application Centric Infrastructure)
  - Juniper Contrail
  - OpenStack Neutron

#### Virtualização de Armazenamento
- **Definição**: Combina vários dispositivos de armazenamento físico em um único dispositivo de armazenamento virtual que é gerenciado a partir de um console centralizado.
- **Como Fazer**:
  - Utilizar software de virtualização de armazenamento que agrupa os dispositivos de armazenamento físicos.
  - Ferramentas como SAN (Storage Area Network) e NAS (Network Attached Storage).
- **Principais Produtos de Mercado**:
  - VMware vSAN
  - Dell EMC VPLEX
  - NetApp ONTAP
  - IBM Spectrum Virtualize

#### Virtualização de Desktop
- **Definição**: Permite que os desktops sejam executados em servidores centralizados, permitindo que os usuários acessem seus desktops virtuais de qualquer dispositivo.
- **Como Fazer**:
  - Utilizar VDI (Virtual Desktop Infrastructure) ou DaaS (Desktop as a Service).
  - Ferramentas que permitem a criação e gestão de desktops virtuais.
- **Principais Produtos de Mercado**:
  - VMware Horizon
  - Citrix Virtual Apps and Desktops
  - Microsoft Azure Virtual Desktop
  - Amazon WorkSpaces

### Benefícios

#### Melhor Utilização de Recursos
- **Explicação**: A virtualização permite que os recursos do hardware físico sejam utilizados de forma mais eficiente, já que várias VMs podem compartilhar os mesmos recursos físicos, como CPU, memória e armazenamento.

#### Redução de Custos Operacionais
- **Explicação**: Reduz a necessidade de adquirir hardware físico adicional, diminui os custos de manutenção e energia, e facilita o gerenciamento centralizado de recursos.

#### Isolamento de Aplicações
- **Explicação**: Cada VM opera de forma independente, o que significa que problemas em uma VM não afetam outras VMs. Isso melhora a segurança e a estabilidade das aplicações.

#### Facilidade de Gerenciamento
- **Explicação**: Ferramentas de gerenciamento de virtualização permitem a criação, configuração, monitoramento e manutenção de VMs a partir de uma interface centralizada, simplificando a administração dos recursos.

## Problemas da Virtualização

### 1. Sobrecarga de Recursos

- **Descrição**: Embora a virtualização permita a execução de várias VMs em um único hardware físico, cada VM ainda consome uma quantidade significativa de recursos (CPU, memória, armazenamento). Se não houver um planejamento adequado, isso pode levar à sobrecarga do host físico.
- **Impacto**: Desempenho degradado, tempos de resposta mais lentos e possíveis falhas do sistema.

### 2. Complexidade de Gerenciamento

- **Descrição**: Gerenciar um grande número de VMs pode ser complexo e desafiador. A administração de recursos, patches de segurança, backups e atualizações se torna mais complicada com a expansão do ambiente virtualizado.
- **Impacto**: Aumento do tempo e esforço necessários para gerenciamento, potencial para erros humanos e dificuldades na manutenção de consistência e segurança.

### 3. Problemas de Segurança

- **Descrição**: VMs compartilham o mesmo hardware físico, o que pode levar a preocupações de segurança, como a possibilidade de ataques de escape de VM, onde uma aplicação maliciosa pode escapar de uma VM e afetar outras VMs ou o próprio host.
- **Impacto**: Potenciais brechas de segurança, comprometimento de dados sensíveis e maior superfície de ataque.

### 4. Dependência de Software de Virtualização

- **Descrição**: A virtualização depende de hipervisores e outros softwares de virtualização. Qualquer vulnerabilidade ou falha nesses softwares pode afetar todas as VMs que eles gerenciam.
- **Impacto**: Potenciais interrupções no serviço, necessidade de atualizações e patches frequentes e risco de falhas generalizadas.

### 5. Problemas de Licenciamento e Custo

- **Descrição**: Muitas soluções de virtualização, especialmente as de nível empresarial, vêm com custos de licenciamento significativos. Além disso, pode haver custos adicionais associados ao suporte e à manutenção.
- **Impacto**: Aumento dos custos operacionais e a necessidade de orçamentos maiores para TI.

### 6. Desempenho I/O

- **Descrição**: Em ambientes virtualizados, o desempenho de entrada/saída (I/O) pode ser afetado devido à sobrecarga adicional do hipervisor e ao compartilhamento de recursos de armazenamento e rede entre várias VMs.
- **Impacto**: Desempenho mais lento para aplicações intensivas em I/O e possíveis gargalos de desempenho.

### 7. Backup e Recuperação de Desastres

- **Descrição**: A virtualização complica os processos de backup e recuperação, uma vez que agora há necessidade de estratégias que considerem tanto as VMs quanto os dados nelas contidos.
- **Impacto**: Necessidade de soluções de backup mais avançadas e potencial para recuperação mais lenta em caso de desastres.

### 8. Problemas de Compatibilidade

- **Descrição**: Algumas aplicações e sistemas operacionais podem não ser totalmente compatíveis com certos hipervisores ou ambientes virtualizados, resultando em problemas de desempenho ou funcionalidade.
- **Impacto**: Limitações na escolha de software e possíveis problemas de desempenho ou estabilidade.

### Conclusão

Embora a virtualização ofereça muitos benefícios, como melhor utilização de recursos e flexibilidade, também apresenta desafios significativos que precisam ser cuidadosamente gerenciados. Conhecer esses problemas é essencial para implementar e manter um ambiente virtualizado eficiente e seguro.

## Containers

### Definição
- Containers são um método de virtualização no nível do sistema operacional, onde o kernel permite a existência de múltiplas instâncias isoladas do espaço do usuário, em vez de apenas uma. Cada container encapsula uma aplicação e todas as suas dependências, garantindo que funcione de forma consistente em qualquer ambiente.

### Comparação com Máquinas Virtuais
- **Menor sobrecarga**: Containers compartilham o kernel do sistema operacional host, enquanto máquinas virtuais (VMs) precisam de um sistema operacional completo para cada instância.
- **Início mais rápido**: Containers podem ser iniciados em segundos, enquanto VMs demoram minutos para iniciar devido ao carregamento do sistema operacional.
- **Melhor uso dos recursos**: Containers utilizam recursos de forma mais eficiente, compartilhando o kernel do host e eliminando a necessidade de emular hardware.
- **Compartilhamento do kernel do host**: Ao contrário das VMs, que têm seus próprios kernels, os containers compartilham o kernel do sistema operacional host, permitindo maior densidade de execução.

### Benefícios
- **Portabilidade**: Containers podem ser executados de forma consistente em qualquer ambiente, desde o laptop do desenvolvedor até servidores de produção.
- **Consistência no ambiente de desenvolvimento e produção**: Elimina o problema de "funciona na minha máquina" ao garantir que o ambiente de execução seja o mesmo em todos os estágios.
- **Isolamento e segurança**: Cada container é isolado dos outros, garantindo que aplicações não interfiram umas com as outras.
- **Escalabilidade**: Facilita a escalabilidade horizontal, permitindo que novos containers sejam instanciados rapidamente para lidar com aumentos de carga.

### Como Utilizar Containers
- **Criação de Containers**: Utilizar ferramentas como Docker para criar e gerenciar containers. Escrever um Dockerfile para definir a imagem do container.
- **Orquestração de Containers**: Utilizar ferramentas de orquestração como Kubernetes para gerenciar clusters de containers, balancear carga e escalar aplicações.
- **Registries de Imagens**: Utilizar repositórios como Docker Hub, Google Container Registry, e Amazon ECR para armazenar e distribuir imagens de containers.

### Principais Produtos de Mercado
- **Docker**: Plataforma de código aberto que facilita a criação, implantação e execução de containers.
- **Kubernetes**: Sistema de orquestração de containers que automatiza a implantação, o dimensionamento e o gerenciamento de aplicações em containers.
- **OpenShift**: Plataforma de contêineres da Red Hat baseada no Kubernetes, com recursos adicionais de desenvolvedor e ferramentas de CI/CD.
- **Rancher**: Plataforma de gerenciamento de contêineres que fornece uma interface para orquestrar Kubernetes e Docker Swarm.
- **Amazon ECS/Fargate**: Serviços de contêineres da AWS que permitem executar e gerenciar contêineres em um ambiente gerenciado.

### Problemas Comuns dos Containers
- **Segurança**: Embora os containers ofereçam um certo grau de isolamento, ainda compartilham o kernel do host, o que pode levar a preocupações de segurança.
- **Persistência de Dados**: Containers são efêmeros por natureza, o que pode complicar a persistência de dados. Soluções como volumes Docker e sistemas de arquivos distribuídos são necessárias.
- **Gerenciamento de Imagens**: A proliferação de imagens pode levar a desafios de gerenciamento e atualização.
- **Rede e Comunicação**: Configurar redes entre containers pode ser complexo, especialmente em ambientes de orquestração como Kubernetes.
- **Monitoramento e Logging**: Monitorar e registrar a atividade dos containers pode ser mais desafiador devido à sua natureza efêmera e distribuída.

### Conclusão
Containers oferecem uma maneira eficiente e flexível de implantar e gerenciar aplicações, proporcionando portabilidade, consistência e escalabilidade. No entanto, é importante estar ciente dos desafios e limitações associados à segurança, persistência de dados e gerenciamento para aproveitar ao máximo essa tecnologia.

## Docker

### Definição
- Docker é uma plataforma de código aberto que facilita a criação, implantação e execução de aplicações em containers. Ele fornece uma camada de abstração e automação para virtualização de containers, permitindo que os desenvolvedores empacotem aplicações e suas dependências em um container portátil.

### Componentes Principais do Docker

#### Docker Engine
- **Definição**: O runtime que permite a construção e execução dos containers. Ele inclui:
  - **Daemon do Docker**: Responsável pela criação, execução e gerenciamento dos containers.
  - **API REST**: Interface que permite aos programas interagirem com o daemon do Docker.
  - **CLI do Docker**: Ferramenta de linha de comando usada para interagir com o Docker.

#### Docker Hub
- **Definição**: Repositório de imagens onde os desenvolvedores podem compartilhar imagens Docker. Ele permite que você armazene e distribua imagens criadas por você ou por outros usuários.
  - **Registro Público**: Onde qualquer um pode puxar imagens publicamente disponíveis.
  - **Registro Privado**: Onde você pode armazenar imagens privadas para seu uso pessoal ou organizacional.

#### Docker Compose
- **Definição**: Ferramenta para definir e executar aplicações Docker multi-containers. Ele usa um arquivo YAML para configurar os serviços da aplicação.
  - **docker-compose.yml**: Arquivo de configuração onde você define os serviços, redes e volumes necessários para a aplicação.

### Como o Docker Funciona

#### Imagens Docker
- **Definição**: Modelos read-only utilizados para criar containers. Cada imagem é composta por camadas que representam diferentes estados do sistema de arquivos.
- **Criação**: As imagens são criadas a partir de um Dockerfile e podem ser compartilhadas através do Docker Hub.

#### Containers Docker
- **Definição**: Instâncias de imagens que estão sendo executadas. Containers são isolados e têm seus próprios sistemas de arquivos, recursos de rede e espaço de processo.
- **Execução**: Containers são iniciados a partir de imagens e podem ser gerenciados usando comandos do Docker CLI.

#### Dockerfile
- **Definição**: Script de configuração utilizado para criar imagens Docker. Contém uma série de instruções que o Docker Engine executa para construir a imagem.
  - **Exemplo de Dockerfile**:
    ```dockerfile
    # Use uma imagem base oficial do Node.js
    FROM node:14

    # Crie um diretório de trabalho
    WORKDIR /app

    # Copie o package.json e o package-lock.json
    COPY package*.json ./

    # Instale as dependências
    RUN npm install

    # Copie o restante do código da aplicação
    COPY . .

    # Exponha a porta que a aplicação irá rodar
    EXPOSE 3000

    # Comando para iniciar a aplicação
    CMD ["node", "app.js"]
    ```

### Benefícios do Docker

- **Facilidade na configuração e gerenciamento de ambientes**: Docker permite que os desenvolvedores configurem e compartilhem ambientes de desenvolvimento consistentes e replicáveis.
- **Redução de incompatibilidades entre sistemas**: Ao empacotar todas as dependências e configurações necessárias em um container, Docker garante que a aplicação funcione da mesma maneira em qualquer ambiente.
- **Agilidade no desenvolvimento e deployment**: Docker acelera o ciclo de desenvolvimento e implantação, permitindo que as equipes entreguem software de forma mais rápida e confiável.

### Casos de Uso

#### DevOps e CI/CD
- **Automação de pipelines de desenvolvimento**: Docker pode ser integrado em pipelines de CI/CD para automação de testes, builds e deployments.
- **Ambientes consistentes para desenvolvimento, teste e produção**: Containers garantem que o código funcione de forma idêntica em todos os ambientes, desde o desenvolvimento até a produção.

#### Microservices
- **Implementação e escalabilidade de arquiteturas de microservices**: Docker facilita a criação e gerenciamento de microservices, permitindo que cada serviço seja desenvolvido, testado e implantado de forma independente.

#### Data Science
- **Criação de ambientes isolados para execução de notebooks e scripts de análise**: Docker permite que os cientistas de dados criem ambientes isolados e reproduzíveis para execução de análises e experimentos, garantindo que as dependências e bibliotecas corretas estejam sempre disponíveis.

### Conclusão
Docker é uma ferramenta poderosa que simplifica a criação, implantação e execução de aplicações em containers, oferecendo benefícios significativos em termos de consistência, portabilidade e escalabilidade. Seja para desenvolvimento de software, arquiteturas de microservices ou análise de dados, Docker é uma escolha excelente para modernizar e otimizar o fluxo de trabalho de TI.

## Demonstração Prática
- Vamos agora colocar esses conhecimentos em pratica
### Subindo 2 containers com Docker - EX01A
### Subindo 2 containers com Docker Compose - EX01B
### Subindo 2 containers com Kubernetes - EX01C


## Recursos Adicionais

- **Documentação Oficial do Docker:** [docs.docker.com](https://docs.docker.com)
- **Curso Docker para Desenvolvedores:** [Docker Academy](https://www.docker.com/academy)
- **Livro:** "Docker: Up & Running" por Karl Matthias e Sean P. Kane