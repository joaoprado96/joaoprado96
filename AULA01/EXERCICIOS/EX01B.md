
# Configuração de Containers Docker com Docker Compose: WordPress e MySQL

## Índice
1. [Introdução](#introdução)
2. [Pré-requisitos](#pré-requisitos)
3. [Objetivo](#objetivo)
4. [Passo 1: Instalar Docker e Docker Compose](#passo-1-instalar-docker-e-docker-compose)
5. [Passo 2: Criação do Arquivo docker-compose.yml](#passo-2-criação-do-arquivo-docker-composeyml)
6. [Passo 3: Subir os Containers](#passo-3-subir-os-containers)
7. [Passo 4: Testar a Comunicação](#passo-4-testar-a-comunicação)
    - [1. Acessar a aplicação WordPress](#1-acessar-a-aplicação-wordpress)
8. [Passo 5: Criar uma Página no WordPress](#passo-5-criar-uma-página-no-wordpress)
    - [1. Criar uma nova página](#1-criar-uma-nova-página)
9. [Passo 6: Consultar a Página no MySQL](#passo-6-consultar-a-página-no-mysql)
    - [1. Acessar o container MySQL](#1-acessar-o-container-mysql)
    - [2. Consultar a página salva no banco de dados](#2-consultar-a-página-salva-no-banco-de-dados)
10. [Passo 7: Derrubar e Remover Containers e Rede](#passo-7-derrubar-e-remover-containers-e-rede)
    - [1. Derrubar os containers](#1-derrubar-os-containers)
    - [2. Remover os containers e rede](#2-remover-os-containers-e-rede)
    - [3. Limpar volumes](#3-limpar-volumes)
11. [Conclusão](#conclusão)
12. [Recursos Adicionais](#recursos-adicionais)

## Introdução
### O que é WordPress?
WordPress é um sistema de gerenciamento de conteúdo (CMS) de código aberto que permite criar e gerenciar websites e blogs facilmente. É conhecido por sua flexibilidade, extensibilidade e ampla comunidade de suporte.

### O que é MySQL?
MySQL é um sistema de gerenciamento de banco de dados relacional (RDBMS) de código aberto, baseado em SQL (Structured Query Language). É utilizado para gerenciar e armazenar dados em uma variedade de aplicações, desde pequenos projetos até grandes sistemas de bancos de dados corporativos.

## Pré-requisitos
- Docker e Docker Compose instalados na sua máquina. [Instruções de instalação do Docker](https://docs.docker.com/get-docker/) e [Instruções de instalação do Docker Compose](https://docs.docker.com/compose/install/)
- Conhecimento básico de linha de comando.

## Objetivo
Criar dois containers: um com uma aplicação WordPress e outro com um banco de dados MySQL, e configurar a comunicação entre eles usando Docker Compose.

## Passo 1: Instalar Docker e Docker Compose
Se você ainda não tem o Docker e o Docker Compose instalados na sua máquina, siga as instruções de instalação nos sites oficiais: [Instruções de instalação do Docker](https://docs.docker.com/get-docker/) e [Instruções de instalação do Docker Compose](https://docs.docker.com/compose/install/).

## Passo 2: Criação do Arquivo docker-compose.yml
Crie um arquivo chamado `docker-compose.yml` com o seguinte conteúdo:

```yaml
version: '3.7'

services:
  wordpress:
    image: wordpress:latest
    ports:
      - "8080:80"
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: user
      WORDPRESS_DB_PASSWORD: user_password
      WORDPRESS_DB_NAME: my_database
    volumes:
      - wordpress_data:/var/www/html

  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root_password
      MYSQL_DATABASE: my_database
      MYSQL_USER: user
      MYSQL_PASSWORD: user_password
    volumes:
      - db_data:/var/lib/mysql

volumes:
  wordpress_data:
  db_data:
```

## Passo 3: Subir os Containers
No mesmo diretório onde o arquivo `docker-compose.yml` está localizado, execute o seguinte comando:

```bash
docker-compose up -d
```

## Passo 4: Testar a Comunicação

### 1. Acessar a aplicação WordPress
Abra o navegador web e vá para `http://localhost:8080`. Você deverá ver a página de configuração do WordPress se tudo estiver configurado corretamente.

## Passo 5: Criar uma Página no WordPress

### 1. Criar uma nova página
1. Faça login no painel administrativo do WordPress (`http://localhost:8080/wp-admin`).
2. Vá para **Páginas > Adicionar nova**.
3. Adicione um título e conteúdo à sua página.
4. Clique em **Publicar** para salvar a página.

## Passo 6: Consultar a Página no MySQL

### 1. Acessar o container MySQL
```bash
docker exec -it nome_do_seu_container_db mysql -u user -p
```
Digite a senha `user_password` quando solicitado. Agora você deve estar no prompt do MySQL.

### 2. Consultar a página salva no banco de dados
No prompt do MySQL, execute os seguintes comandos:

```sql
USE my_database;
SELECT * FROM wp_posts WHERE post_type='page';
```

Isso retornará uma lista de páginas salvas no WordPress, incluindo a que você acabou de criar.

## Passo 7: Derrubar e Remover Containers e Rede

### 1. Derrubar os containers
No mesmo diretório onde o arquivo `docker-compose.yml` está localizado, execute o seguinte comando:

```bash
docker-compose down
```

### 2. Remover os containers e rede
Os containers e a rede serão removidos automaticamente pelo comando `docker-compose down`.

### 3. Limpar volumes
```bash
docker volume rm nome_do_seu_projeto_db_data
docker volume rm nome_do_seu_projeto_wordpress_data
```

## Conclusão
Você configurou com sucesso dois containers Docker (WordPress e MySQL) usando Docker Compose e configurou a comunicação entre eles. Além disso, você criou uma nova página no WordPress e consultou a página salva diretamente no banco de dados MySQL. Finalmente, você aprendeu a derrubar, remover os containers e a rede Docker, e limpar os volumes utilizados.

## Recursos Adicionais
- [Documentação do Docker](https://docs.docker.com/)
- [Documentação do Docker Compose](https://docs.docker.com/compose/)
- [Imagens Docker no Docker Hub](https://hub.docker.com/)
- [Documentação do WordPress](https://wordpress.org/support/)
- [Documentação do MySQL](https://dev.mysql.com/doc/)
