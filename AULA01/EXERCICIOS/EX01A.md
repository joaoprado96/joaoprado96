
# Configuração Manual de Containers Docker: WordPress e MySQL

## Índice
1. [Introdução](#introdução)
2. [Pré-requisitos](#pré-requisitos)
3. [Objetivo](#objetivo)
4. [Passo 1: Instalar Docker](#passo-1-instalar-docker)
5. [Passo 2: Criação da Rede Docker](#passo-2-criação-da-rede-docker)
6. [Passo 3: Baixar as Imagens Docker](#passo-3-baixar-as-imagens-docker)
    - [1. Baixar a imagem do MySQL](#1-baixar-a-imagem-do-mysql)
    - [2. Baixar a imagem do WordPress](#2-baixar-a-imagem-do-wordpress)
7. [Passo 4: Criação do Container MySQL](#passo-4-criação-do-container-mysql)
    - [1. Iniciar o container MySQL](#1-iniciar-o-container-mysql)
8. [Passo 5: Criação do Container WordPress](#passo-5-criação-do-container-wordpress)
    - [1. Iniciar o container WordPress](#1-iniciar-o-container-wordpress)
9. [Passo 6: Testar a Comunicação](#passo-6-testar-a-comunicação)
    - [1. Acessar a aplicação WordPress](#1-acessar-a-aplicação-wordpress)
10. [Passo 7: Criar uma Página no WordPress](#passo-7-criar-uma-página-no-wordpress)
    - [1. Criar uma nova página](#1-criar-uma-nova-página)
11. [Passo 8: Consultar a Página no MySQL](#passo-8-consultar-a-página-no-mysql)
    - [1. Acessar o container MySQL](#1-acessar-o-container-mysql)
    - [2. Consultar a página salva no banco de dados](#2-consultar-a-página-salva-no-banco-de-dados)
12. [Passo 9: Derrubar e Remover Containers e Rede](#passo-9-derrubar-e-remover-containers-e-rede)
    - [1. Derrubar os containers](#1-derrubar-os-containers)
    - [2. Remover os containers](#2-remover-os-containers)
    - [3. Remover a rede Docker](#3-remover-a-rede-docker)
    - [4. Limpar volumes](#4-limpar-volumes)
13. [Conclusão](#conclusão)
14. [Recursos Adicionais](#recursos-adicionais)

## Introdução
### O que é WordPress?
WordPress é um sistema de gerenciamento de conteúdo (CMS) de código aberto que permite criar e gerenciar websites e blogs facilmente. É conhecido por sua flexibilidade, extensibilidade e ampla comunidade de suporte.

### O que é MySQL?
MySQL é um sistema de gerenciamento de banco de dados relacional (RDBMS) de código aberto, baseado em SQL (Structured Query Language). É utilizado para gerenciar e armazenar dados em uma variedade de aplicações, desde pequenos projetos até grandes sistemas de bancos de dados corporativos.

## Pré-requisitos
- Docker instalado na sua máquina. [Instruções de instalação](https://docs.docker.com/get-docker/)
- Conhecimento básico de linha de comando.

## Objetivo
Criar dois containers: um com uma aplicação WordPress e outro com um banco de dados MySQL, e configurar a comunicação entre eles manualmente.

## Passo 1: Instalar Docker
Se você ainda não tem o Docker instalado na sua máquina, siga as instruções de instalação no site oficial do Docker: [Instruções de instalação](https://docs.docker.com/get-docker/).

## Passo 2: Criação da Rede Docker
Para que os containers possam se comunicar, vamos criar uma rede Docker.

```bash
docker network create wordpress-network
```

## Passo 3: Baixar as Imagens Docker

### 1. Baixar a imagem do MySQL
```bash
docker pull mysql:8.0
```

### 2. Baixar a imagem do WordPress
```bash
docker pull wordpress:latest
```

## Passo 4: Criação do Container MySQL

### 1. Iniciar o container MySQL
```bash
docker run --name mysql-container --network wordpress-network -e MYSQL_ROOT_PASSWORD=root_password -e MYSQL_DATABASE=my_database -e MYSQL_USER=user -e MYSQL_PASSWORD=user_password -v mysql_data:/var/lib/mysql -d mysql:8.0
```
- **--name**: Nome do container (mysql-container).
- **--network**: Rede Docker para o container (wordpress-network).
- **-e**: Variáveis de ambiente para configuração do MySQL.
- **-v**: Monta o volume para persistir os dados do MySQL.
- **-d**: Executar o container em modo desacoplado (em background).

## Passo 5: Criação do Container WordPress

### 1. Iniciar o container WordPress
```bash
docker run --name wordpress-container --network wordpress-network -e WORDPRESS_DB_HOST=mysql-container -e WORDPRESS_DB_USER=user -e WORDPRESS_DB_PASSWORD=user_password -e WORDPRESS_DB_NAME=my_database -p 8080:80 -v wordpress_data:/var/www/html -d wordpress:latest
```
- **--name**: Nome do container (wordpress-container).
- **--network**: Rede Docker para o container (wordpress-network).
- **-e**: Variáveis de ambiente para configuração do WordPress.
- **-p**: Mapeia a porta 80 do container para a porta 8080 do host.
- **-v**: Monta o volume para persistir os dados do WordPress.
- **-d**: Executar o container em modo desacoplado (em background).

## Passo 6: Testar a Comunicação

### 1. Acessar a aplicação WordPress
Abra o navegador web e vá para `http://localhost:8080`. Você deverá ver a página de configuração do WordPress se tudo estiver configurado corretamente.

## Passo 7: Criar uma Página no WordPress

### 1. Criar uma nova página
1. Faça login no painel administrativo do WordPress (`http://localhost:8080/wp-admin`).
2. Vá para **Páginas > Adicionar nova**.
3. Adicione um título e conteúdo à sua página.
4. Clique em **Publicar** para salvar a página.

## Passo 8: Consultar a Página no MySQL

### 1. Acessar o container MySQL
```bash
docker exec -it mysql-container mysql -u user -p
```
Digite a senha `user_password` quando solicitado. Agora você deve estar no prompt do MySQL.

### 2. Consultar a página salva no banco de dados
No prompt do MySQL, execute os seguintes comandos:

```sql
USE my_database;
SELECT * FROM wp_posts WHERE post_type='page';
```

Isso retornará uma lista de páginas salvas no WordPress, incluindo a que você acabou de criar.

## Passo 9: Derrubar e Remover Containers e Rede

### 1. Derrubar os containers
```bash
docker stop wordpress-container
docker stop mysql-container
```

### 2. Remover os containers
```bash
docker rm wordpress-container
docker rm mysql-container
```

### 3. Remover a rede Docker
```bash
docker network rm wordpress-network
```

### 4. Limpar volumes
```bash
docker volume rm mysql_data
docker volume rm wordpress_data
```

## Conclusão
Você configurou com sucesso dois containers Docker (WordPress e MySQL) manualmente e configurou a comunicação entre eles usando uma rede Docker. Além disso, você criou uma nova página no WordPress e consultou a página salva diretamente no banco de dados MySQL. Finalmente, você aprendeu a derrubar, remover os containers e a rede Docker, e limpar os volumes utilizados.

## Recursos Adicionais
- [Documentação do Docker](https://docs.docker.com/)
- [Imagens Docker no Docker Hub](https://hub.docker.com/)
- [Documentação do WordPress](https://wordpress.org/support/)
- [Documentação do MySQL](https://dev.mysql.com/doc/)
