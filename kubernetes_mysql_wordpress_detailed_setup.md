
# Kubernetes Hands-on e Demonstrações

## Índice
1. [Introdução](#introdução)
2. [Pré-requisitos](#pré-requisitos)
3. [Objetivo](#objetivo)
4. [Passo a Passo](#passo-a-passo)
   - [Configurando um Cluster Kubernetes](#configurando-um-cluster-kubernetes)
   - [Criando e Gerenciando Pods](#criando-e-gerenciando-pods)
   - [Configurando MySQL e WordPress](#configurando-mysql-e-wordpress)
5. [Conclusão](#conclusão)

## Introdução
Neste tutorial, vamos configurar um cluster Kubernetes local usando Minikube, criar e gerenciar Pods, e configurar dois containers, MySQL e WordPress, para que se comuniquem entre si. Este é um guia prático que ajudará a entender os conceitos básicos de Kubernetes e como ele pode ser usado para orquestrar aplicações em containers.

## Pré-requisitos
- Sistema operacional: Windows, macOS ou Linux
- Minikube instalado ([Guia de Instalação](https://minikube.sigs.k8s.io/docs/start/))
- Kubectl instalado ([Guia de Instalação](https://kubernetes.io/docs/tasks/tools/install-kubectl/))
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

### Criando e Gerenciando Pods
1. **Criando um Pod**:
    ```sh
    kubectl run nginx --image=nginx
    ```
2. **Listando Pods**:
    ```sh
    kubectl get pods
    ```
3. **Criando um Deployment**:
    ```sh
    kubectl create deployment nginx --image=nginx
    ```
4. **Escalando o Deployment**:
    ```sh
    kubectl scale deployment nginx --replicas=3
    ```
5. **Atualizando o Deployment**:
    ```sh
    kubectl set image deployment/nginx nginx=nginx:1.16.1
    ```
6. **Listando Deployments e ReplicaSets**:
    ```sh
    kubectl get deployments
    kubectl get rs
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
              - image: mysql:5.6
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
              - image: wordpress:4.8-apache
                name: wordpress
                env:
                - name: WORDPRESS_DB_HOST
                  value: mysql:3306
                - name: WORDPRESS_DB_PASSWORD
                  value: password
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
Neste tutorial, configuramos um cluster Kubernetes local utilizando Minikube, criamos e gerenciamos Pods, e configuramos dois containers, MySQL e WordPress, para que se comuniquem entre si. Esperamos que este guia tenha ajudado a entender os conceitos básicos de Kubernetes e como ele pode ser usado para orquestrar aplicações em containers. Continue explorando e experimentando com diferentes configurações e aplicações para aprofundar seu conhecimento em Kubernetes.
