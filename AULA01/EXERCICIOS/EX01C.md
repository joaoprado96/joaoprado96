# Kubernetes Hands-on e Demonstrações

## Índice
1. [Introdução](#introdução)
2. [Pré-requisitos](#pré-requisitos)
3. [Objetivo](#objetivo)
4. [Passo a Passo](#passo-a-passo)
   - [Configurando um Cluster Kubernetes](#configurando-um-cluster-kubernetes)
   - [Baixando as Imagens do Docker](#baixando-as-imagens-do-docker)
   - [Configurando MySQL e WordPress](#configurando-mysql-e-wordpress)
   - [Verificando Conectividade](#verificando-conectividade)
   - [Criando Banco de Dados e Concedendo Permissões](#criando-banco-de-dados-e-concedendo-permissões)
   - [Verificando e Ajustando Configurações](#verificando-e-ajustando-configurações)
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
                  value: mysql.default.svc.cluster.local
                - name: WORDPRESS_DB_USER
                  value: root
                - name: WORDPRESS_DB_PASSWORD
                  value: password
                - name: WORDPRESS_DB_NAME
                  value: wordpress
                ports:
                - containerPort: 80
                  name: wordpress
                readinessProbe:
                  httpGet:
                    path: /
                    port: 80
                  initialDelaySeconds: 10
                  periodSeconds: 5
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

### Verificando Conectividade
Para verificar se o WordPress pode se conectar ao MySQL, você pode usar um Pod temporário para testar a conectividade:

1. **Criar um Pod Temporário para Teste**:

    Se você encontrar o erro "pods 'debug' already exists", você tem duas opções:

    - **Opção 1: Excluir o Pod Existente e Criar um Novo**:
        ```sh
        kubectl delete pod debug
        kubectl run -i --tty --rm debug --image=busybox --restart=Never -- sh
        ```

    - **Opção 2: Criar um Novo Pod com um Nome Diferente**:
        ```sh
        kubectl run -i --tty --rm debug2 --image=busybox --restart=Never -- sh
        ```

2. **Testar Resolução de Nome e Conectividade**:
    Dentro do Pod, tente os seguintes comandos:
    ```sh
    nslookup mysql.default.svc.cluster.local
    nc -zv mysql.default.svc.cluster.local 3306
    ```

    - `nslookup mysql.default.svc.cluster.local`: Verifica se o nome do serviço MySQL está sendo resolvido corretamente.
    - `nc -zv mysql.default.svc.cluster.local 3306`: Verifica se a porta 3306 do serviço MySQL está aberta e acessível.

### Criando Banco de Dados e Concedendo Permissões
Para criar o banco de dados `wordpress` e conceder as permissões necessárias ao usuário:

1. **Acessar o MySQL**:
    ```sh
    kubectl exec -it $(kubectl get pods -l app=mysql -o jsonpath='{.items[0].metadata.name}') -- mysql -u root -p
    ```

2. **Criar o Banco de Dados `wordpress`**:
    ```sql
    CREATE DATABASE wordpress;
    ```

3. **Conceder Permissões ao Usuário**:
    ```sql
    GRANT ALL PRIVILEGES ON wordpress.* TO 'root'@'%';
    FLUSH PRIVILEGES;
    ```

4. **Verificar se o Banco de Dados foi Criado**:
    ```sql
    SHOW DATABASES;
    ```

### Verificando e Ajustando Configurações
Para garantir que as configurações estejam corretas e o WordPress funcione corretamente:

1. **Acessar o Pod do WordPress**:
    ```sh
    kubectl exec -it $(kubectl get pods -l app=wordpress -o jsonpath='{.items[0].metadata.name}') -- /bin/bash
    ```

2. **Reiniciar Apache**:
    ```sh
    service apache2 restart
    ```

4. **Verificar Logs de Erro do WordPress**:
    ```sh
    tail -f /var/www/html/wp-content/debug.log
    ```

## Conclusão
Neste tutorial, configuramos um cluster Kubernetes local usando Minikube, baixamos e configuramos containers MySQL e WordPress, criamos o banco de dados `wordpress` e garantimos que as configurações estavam corretas. Com isso, conseguimos acessar e utilizar o WordPress com sucesso dentro do nosso cluster Kubernetes.
