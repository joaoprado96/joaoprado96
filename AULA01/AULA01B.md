# Kubernetes

## Índice
1. [Introdução](#introdução)
   - [O que é Kubernetes?](#o-que-é-kubernetes)
   - [Principais conceitos](#principais-conceitos)
2. [Arquitetura do Kubernetes](#arquitetura-do-kubernetes)
   - [Componentes do Plano de Controle (Control Plane)](#componentes-do-plano-de-controle-control-plane)
   - [Componentes dos Nós (Nodes)](#componentes-dos-nós-nodes)
3. [Funcionalidades do Kubernetes](#funcionalidades-do-kubernetes)
   - [Orquestração de containers](#orquestração-de-containers)
   - [Autoescalonamento (Auto-scaling)](#autoescalonamento-auto-scaling)
   - [Deployments e atualizações contínuas](#deployments-e-atualizações-contínuas)
   - [Monitoramento e logging](#monitoramento-e-logging)
   - [Segurança](#segurança)
4. [Principais Ferramentas de Mercado](#principais-ferramentas-de-mercado)
   - [Ferramentas de Gerenciamento](#ferramentas-de-gerenciamento)
   - [Ferramentas de CI/CD](#ferramentas-de-cicd)
   - [Observabilidade](#observabilidade)
   - [Ferramentas de Segurança](#ferramentas-de-segurança)
5. [Casos de Uso](#casos-de-uso)
   - [Deploy de Aplicações Web](#deploy-de-aplicações-web)
   - [Processamento em Lote (Batch Processing)](#processamento-em-lote-batch-processing)
   - [Microservices](#microservices)
   - [Desenvolvimento e Testes](#desenvolvimento-e-testes)
6. [Kubernetes no IBM ZCX](#kubernetes-no-ibm-zcx)
   - [O que é IBM ZCX?](#o-que-é-ibm-zcx)
   - [Benefícios do IBM ZCX](#benefícios-do-ibm-zcx)
   - [Provisionamento de uma Instância ZCX](#provisionamento-de-uma-instância-zcx)
   - [Como Kubernetes se integra com IBM ZCX](#como-kubernetes-se-integra-com-ibm-zcx)
8. [Conclusao](#conclusao)

## 1. Introdução

### 1.1. O que é Kubernetes?
[Kubernetes](https://kubernetes.io/docs/concepts/overview/what-is-kubernetes/), também conhecido como K8s, é uma plataforma open-source para orquestração de containers, permitindo automação na implantação, escalonamento e operações de aplicações em containers. Foi originalmente desenvolvido pelo Google, inspirado no seu sistema interno chamado Borg, e agora é mantido pela Cloud Native Computing Foundation (CNCF).

### 1.2. Principais conceitos
- **Containers e Docker**: Containers são unidades leves e portáveis de software que empacotam código e todas as suas dependências. Docker é a plataforma mais comum para criação de containers.
- **Cluster**: Conjunto de máquinas (físicas ou virtuais) que executam os containers gerenciados pelo Kubernetes.
- **Nodes (Master e Worker)**: Máquinas dentro do cluster. O Master Node gerencia o cluster e os Worker Nodes executam os containers.
- **Pods**: A menor unidade de execução no Kubernetes, um Pod pode conter um ou mais containers.
- **ReplicaSets**: Garante que um número especificado de réplicas de um Pod esteja rodando em qualquer momento.
- **Deployments**: Controla a criação e atualização de ReplicaSets.
- **Services**: Abstração que define um conjunto lógico de Pods e uma política para acessar esses Pods.

## 2. Arquitetura do Kubernetes

### 2.1. Componentes do Plano de Controle (Control Plane)
- **API Server**: Exponha a API do Kubernetes. Ele é o ponto de entrada para todas as chamadas REST e processa o estado desejado do cluster.
- **etcd**: Armazena todos os dados do cluster. É um banco de dados chave-valor distribuído e confiável.
- **Scheduler**: Atribui Pods aos Nodes com base em recursos disponíveis e outras restrições.
- **Controller Manager**: Executa processos de fundo que gerenciam o estado do cluster, como a criação de Pods em ReplicaSets.
- **Cloud Controller Manager**: Gerencia componentes específicos de nuvem, permitindo a integração com provedores de nuvem.

### 2.2. Componentes dos Nós (Nodes)
- **Kubelet**: Agente que roda em cada Node, garantindo que os containers estejam rodando em Pods.
- **Kube-proxy**: Mantém regras de rede no Node e permite a comunicação de rede para os Pods.
- **Container Runtime**: O software responsável por rodar containers (Docker, containerd, etc.).

## 3. Funcionalidades do Kubernetes

### 3.1. Orquestração de containers
Kubernetes gerencia automaticamente a criação, destruição e replicação de containers, garantindo alta disponibilidade e balanceamento de carga.

### 3.2. Autoescalonamento (Auto-scaling)
- **Horizontal Pod Autoscaler (HPA)**: Ajusta o número de réplicas de Pods com base na utilização de recursos, como CPU e memória.
- **Vertical Pod Autoscaler (VPA)**: Recomenda e ajusta automaticamente os valores de CPU e memória para os Pods.
- **Cluster Autoscaler**: Ajusta o número de Nodes no cluster com base na demanda, expandindo ou encolhendo o pool de Nodes conforme necessário.

### 3.3. Deployments e atualizações contínuas
- **Rolling updates**: Atualiza gradualmente os Pods de uma aplicação para garantir zero downtime.
- **Rollbacks**: Reverte para uma versão anterior em caso de falha na atualização.

### 3.4. Monitoramento e logging
- **Prometheus e Grafana**: Ferramentas populares para monitoramento e visualização de métricas.
- **ELK Stack (Elasticsearch, Logstash, Kibana)**: Solução para coleta, análise e visualização de logs.
- **Fluentd**: Ferramenta de coleta de logs para agregação e roteamento.

### 3.5. Segurança
- **RBAC (Role-Based Access Control)**: Controle de acesso baseado em funções para gerenciar permissões no cluster. Atribua roles e bindings seguindo o princípio do menor privilégio.
- **Secrets e ConfigMaps**: Armazenamento de informações sensíveis e configurações de forma segura.
- **Network Policies**: Definição de regras de rede para controlar a comunicação entre Pods. Inclua plugins de rede como Calico, Flannel e Weave Net.

## 4. Principais Ferramentas de Mercado

### 4.1. Ferramentas de Gerenciamento
- **Kubernetes Dashboard**: Interface web para gerenciamento e visualização de recursos no cluster.
- **Kubectl (CLI)**: Ferramenta de linha de comando para interagir com o cluster Kubernetes.

### 4.2. Ferramentas de CI/CD
- **Jenkins X**: Extensão do Jenkins para Kubernetes, facilitando a entrega contínua.
- **Argo CD**: Ferramenta declarativa de CD para Kubernetes.
- **Tekton**: Framework de pipelines CI/CD nativo para Kubernetes.

### 4.3. Observabilidade
- **Prometheus & Grafana**: Monitoramento de métricas e visualização.
- **ELK Stack (Elasticsearch, Logstash, Kibana)**: Solução completa de logging.

### 4.4. Ferramentas de Segurança
- **OPA (Open Policy Agent)**: Ferramenta para políticas de segurança e controle de acesso.

## 5. Casos de Uso

### 5.1. Deploy de Aplicações Web
- Deploy de uma aplicação web em múltiplos Pods com balanceamento de carga usando Services.
- Gerenciamento de versões e atualizações contínuas com Deployments.

### 5.2. Processamento em Lote (Batch Processing)
- Configuração e execução de Jobs e CronJobs para tarefas em lote.

### 5.3. Microservices
- Orquestração de múltiplos serviços e comunicação segura entre eles usando Service Mesh.

### 5.4. Desenvolvimento e Testes
- Criação de ambientes de desenvolvimento replicáveis e testes automatizados com pipelines CI/CD.

## 6. Kubernetes no IBM ZCX

### 6.1. O que é IBM ZCX?
IBM z/OS Container Extensions (ZCX) é uma solução que permite a execução de containers Linux no z/OS. Isso possibilita a execução de workloads modernos em containers diretamente no mainframe, integrando o ambiente tradicional do z/OS com aplicações baseadas em containers.

### 6.2. Benefícios do IBM ZCX
- **Integração**: Permite a execução de aplicações em containers junto com workloads tradicionais no z/OS.
- **Segurança**: Aproveita os recursos de segurança robustos do z/OS.
- **Performance**: Tira proveito da alta performance do hardware IBM Z.
- **Eficiência Operacional**: Reduz a necessidade de transferências de dados entre ambientes diferentes.

### 6.3. Provisionamento de uma Instância ZCX
#### Passos para Provisionamento
**Pré-requisitos:**
- Certifique-se de que o ambiente z/OS está configurado corretamente.
- Verifique se os recursos necessários (CPU, memória, armazenamento) estão disponíveis.

**Configuração do Ambiente:**
- Configure o ambiente z/OS para suportar ZCX, incluindo a configuração de redes e armazenamento.

**Criação da Instância ZCX:**
- Utilize comandos específicos do z/OS para criar e configurar uma instância ZCX.
- Exemplo de comando:
  ```sh
  CREATE ZCX INSTANCE <instance_name> ...
  ```

**Configuracao da instancia**
- Configure a instância ZCX para atender aos requisitos específicos da aplicação.
- Isso pode incluir a configuração de volumes, redes e outras dependências.

**Deploy de Containers:**
- Utilize ferramentas de orquestração de containers, como Kubernetes, para gerenciar os containers dentro da instância ZCX.
- Exemplo de comando Kubernetes:
```sh
apiVersion: v1
kind: Pod
metadata:
  name: my-pod
spec:
  containers:
   - name: my-container
    image: my-image
```

**Deploy de Containers:**
- Gestão de Containers: Kubernetes pode ser utilizado para gerenciar os containers executados no IBM ZCX, proporcionando uma interface unificada para orquestração.
- Resiliência: A combinação do Kubernetes com o IBM ZCX aumenta a resiliência e disponibilidade das aplicações.
- DevOps: Facilita a adoção de práticas DevOps, integrando aplicações mainframe com pipelines de CI/CD modernos.

## 7. Conclusão

Nesta aula, exploramos os fundamentos do Kubernetes, uma plataforma poderosa e amplamente utilizada para orquestração de containers. Discutimos a arquitetura do Kubernetes, incluindo os componentes do plano de controle e dos nós, e examinamos suas principais funcionalidades, como orquestração de containers, autoescalonamento, e segurança.

Também abordamos as principais ferramentas de mercado que complementam o Kubernetes, como ferramentas de gerenciamento, CI/CD, observabilidade e segurança. Além disso, exploramos casos de uso práticos, desde o deploy de aplicações web até o desenvolvimento e testes de microservices.

Por fim, discutimos a integração do Kubernetes com o IBM z/OS Container Extensions (ZCX), destacando os benefícios e os passos para provisionar uma instância ZCX.

Esperamos que esta aula tenha fornecido uma compreensão sólida do Kubernetes e suas capacidades, capacitando você a aplicar esses conhecimentos em seus projetos e ambientes de trabalho.

## 8. Materiais de Referência

- [Documentação oficial do Kubernetes](https://kubernetes.io/docs/home/)
- [Documentação do IBM ZCX](https://www.ibm.com/docs/en/zos-container-extensions)
- "Kubernetes Up & Running" (livro)
- Tutoriais e vídeos no YouTube (canal do Kubernetes)