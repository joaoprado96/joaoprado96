# Aula sobre Kubernetes

## 1. Introdução ao Kubernetes

### 1.1. O que é Kubernetes?
Kubernetes, também conhecido como K8s, é uma plataforma open-source para orquestração de containers, permitindo automação na implantação, escalonamento e operações de aplicações em containers. Foi originalmente desenvolvido pelo Google, inspirado no seu sistema interno chamado Borg, e agora é mantido pela Cloud Native Computing Foundation (CNCF).

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
- **Cluster Autoscaler**: Ajusta o número de Nodes no cluster com base na demanda.

### 3.3. Deployments e atualizações contínuas
- **Rolling updates**: Atualiza gradualmente os Pods de uma aplicação para garantir zero downtime.
- **Rollbacks**: Reverte para uma versão anterior em caso de falha na atualização.

### 3.4. Monitoramento e logging
- **Prometheus e Grafana**: Ferramentas populares para monitoramento e visualização de métricas.
- **ELK Stack (Elasticsearch, Logstash, Kibana)**: Solução para coleta, análise e visualização de logs.
- **Fluentd**: Ferramenta de coleta de logs para agregação e roteamento.

### 3.5. Segurança
- **RBAC (Role-Based Access Control)**: Controle de acesso baseado em funções para gerenciar permissões no cluster.
- **Secrets e ConfigMaps**: Armazenamento de informações sensíveis e configurações de forma segura.
- **Network Policies**: Definição de regras de rede para controlar a comunicação entre Pods.

## 4. Principais Ferramentas de Mercado

### 4.1. Ferramentas de Gerenciamento
- **Kubernetes Dashboard**: Interface web para gerenciamento e visualização de recursos no cluster.
- **Lens**: IDE para Kubernetes que facilita a visualização e gerenciamento de clusters.
- **Kubectl (CLI)**: Ferramenta de linha de comando para interagir com o cluster Kubernetes.

### 4.2. Ferramentas de CI/CD
- **Jenkins X**: Extensão do Jenkins para Kubernetes, facilitando a entrega contínua.
- **Argo CD**: Ferramenta declarativa de CD para Kubernetes.
- **Tekton**: Framework de pipelines CI/CD nativo para Kubernetes.

### 4.3. Observabilidade
- **Prometheus & Grafana**: Monitoramento de métricas e visualização.
- **ELK Stack (Elasticsearch, Logstash, Kibana)**: Solução completa de logging.
- **Jaeger**: Ferramenta para rastreamento distribuído (tracing).

### 4.4. Ferramentas de Segurança
- **Istio (Service Mesh)**: Gerenciamento de tráfego de rede, segurança e observabilidade para serviços.
- **Linkerd**: Service mesh leve para Kubernetes.
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

## 6. Hands-on e Demonstrações

### 6.1. Configurando um Cluster Kubernetes
- **Minikube**: Ferramenta para rodar um cluster Kubernetes localmente.
- **Google Kubernetes Engine (GKE)**: Serviço gerenciado de Kubernetes na Google Cloud Platform.

### 6.2. Criando e Gerenciando Pods
- Comandos básicos do Kubectl para criar e gerenciar Pods, ReplicaSets e Deployments.

### 6.3. Configurando Serviços e Ingress
- Exposição de aplicações com Services e configuração de um Ingress Controller para gerenciamento de tráfego.

## 7. Conclusão e Perguntas

### 7.1. Resumo dos pontos principais
- Revisão dos conceitos e funcionalidades abordadas, reforçando a importância do Kubernetes na orquestração de containers.

### 7.2. Perguntas e Respostas
- Espaço aberto para dúvidas e discussões, permitindo uma interação enriquecedora com o público.

## Materiais de Referência
- [Documentação oficial do Kubernetes](https://kubernetes.io/docs/)
- "Kubernetes Up & Running" (livro)
- Tutoriais e vídeos no YouTube (canal do Kubernetes)