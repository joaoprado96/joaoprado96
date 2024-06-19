
# Kubernetes Hands-on e Demonstrações

## Índice
1. [Introdução](#introdução)
2. [Pré-requisitos](#pré-requisitos)
3. [Objetivo](#objetivo)
4. [Passo a Passo](#passo-a-passo)
   - [Configurando um Cluster Kubernetes](#configurando-um-cluster-kubernetes)
   - [Baixando as Imagens do Docker](#baixando-as-imagens-do-docker)
   - [Configurando MySQL e WordPress](#configurando-mysql-e-wordpress)
5. [Conclusão](#conclusão)

## Introdução
Neste tutorial, vamos configurar um cluster Kubernetes local usando Minikube, baixar as imagens Docker do MySQL e WordPress, e configurar os containers para que se comuniquem entre si. Este é um guia prático que ajudará a entender os conceitos básicos de Kubernetes e como ele pode ser usado para orquestrar aplicações em containers.

## Pré-requisitos
- Sistema operacional: Windows, macOS ou Linux
- Minikube instalado ([Guia de Instalação](https://minikube.sigs.k8s.io/docs/start/))
- Kubectl instalado ([Guia de Instalação](https://kubernetes.io/docs/tasks/tools/install-kubectl/))
- Docker instalado ([Guia de Instalação](https://docs.docker.com/get-docker/))
- Helm instalado ([Guia de Instalação](https://helm.sh/docs/intro/install/))

## Objetivo
Ao final deste tutorial, você terá um cluster Kubernetes rodando localmente com Minikube, dois containers (MySQL e WordPress) configurados e se comunicando entre si, e entenderá como criar e gerenciar Pods, Services e Deployments no Kubernetes.

## Passo a Passo

### Configurando um Cluster Kubernetes
1. **Instalação do Minikube**:
    - Siga as instruções de instalação para seu sistema operacional disponíveis em: [Instalação do Minikube](https://minikube.sigs.k8s.io/docs/start/)
2. **Inicialização do Cluster**:
    ```sh
    minikube start
    ```
3. **Verificando o Status do Cluster**:
    ```sh
    minikube status
    ```

### Baixando as Imagens do Docker
1. **Baixando a Imagem do MySQL**:
    ```sh
    docker pull mysql:8.0
    ```
2. **Baixando a Imagem do WordPress**:
    ```sh
    docker pull wordpress:latest
    ```

### Configurando MySQL e WordPress
1. **Criando um Deployment para MySQL**:
    - Crie um arquivo `mysql-deployment.yaml` com o seguinte conteúdo:
        ```yaml
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: mysql
        spec:
          selector:
            matchLabels:
              app: mysql
          strategy:
            type: Recreate
          template:
            metadata:
              labels:
                app: mysql
            spec:
              containers:
              - image: mysql:8.0
                name: mysql
                env:
                - name: MYSQL_ROOT_PASSWORD
                  value: password
                ports:
                - containerPort: 3306
                  name: mysql
        ```
    - Aplique a configuração:
        ```sh
        kubectl apply -f mysql-deployment.yaml
        ```

2. **Criando um Service para MySQL**:
    - Crie um arquivo `mysql-service.yaml` com o seguinte conteúdo:
        ```yaml
        apiVersion: v1
        kind: Service
        metadata:
          name: mysql
        spec:
          ports:
          - port: 3306
            targetPort: 3306
          selector:
            app: mysql
        ```
    - Aplique a configuração:
        ```sh
        kubectl apply -f mysql-service.yaml
        ```

3. **Criando um Deployment para WordPress**:
    - Crie um arquivo `wordpress-deployment.yaml` com o seguinte conteúdo:
        ```yaml
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: wordpress
        spec:
          selector:
            matchLabels:
              app: wordpress
          strategy:
            type: Recreate
          template:
            metadata:
              labels:
                app: wordpress
            spec:
              containers:
              - image: wordpress:latest
                name: wordpress
                env:
                - name: WORDPRESS_DB_HOST
                  value: mysql
                - name: WORDPRESS_DB_USER
                  value: root
                - name: WORDPRESS_DB_PASSWORD
                  value: password
                - name: WORDPRESS_DB_NAME
                  value: wordpress
                ports:
                - containerPort: 80
                  name: wordpress
        ```
    - Aplique a configuração:
        ```sh
        kubectl apply -f wordpress-deployment.yaml
        ```

4. **Criando um Service para WordPress**:
    - Crie um arquivo `wordpress-service.yaml` com o seguinte conteúdo:
        ```yaml
        apiVersion: v1
        kind: Service
        metadata:
          name: wordpress
        spec:
          ports:
          - port: 80
            targetPort: 80
          selector:
            app: wordpress
          type: LoadBalancer
        ```
    - Aplique a configuração:
        ```sh
        kubectl apply -f wordpress-service.yaml
        ```

5. **Verificando os Deployments e Services**:
    ```sh
    kubectl get deployments
    kubectl get services
    ```

6. **Acessando o WordPress**:
    - Utilize o comando `minikube service wordpress --url` para obter a URL de acesso ao WordPress.

## Conclusão
Neste tutorial, configuramos um cluster Kubernetes local utilizando Minikube, baixamos as imagens Docker do MySQL e WordPress, e configuramos dois containers para que se comuniquem entre si. Esperamos que este guia tenha ajudado a entender os conceitos básicos de Kubernetes e como ele pode ser usado para orquestrar aplicações em containers. Continue explorando e experimentando com diferentes configurações e aplicações para aprofundar seu conhecimento em Kubernetes.
