
# Código Python para gerar o arquivo Markdown para configurar WordPress com MySQL manualmente

markdown_content = """
# Configuração Manual de Containers Docker: WordPress e MySQL

## Índice
1. [Introdução](#introdução)
2. [Pré-requisitos](#pré-requisitos)
3. [Objetivo](#objetivo)
4. [Passo 1: Criação da Rede Docker](#passo-1-criação-da-rede-docker)
5. [Passo 2: Criação do Container MySQL](#passo-2-criação-do-container-mysql)
    - [1. Iniciar o container MySQL](#1-iniciar-o-container-mysql)
6. [Passo 3: Criação do Container WordPress](#passo-3-criação-do-container-wordpress)
    - [1. Iniciar o container WordPress](#1-iniciar-o-container-wordpress)
7. [Passo 4: Testar a Comunicação](#passo-4-testar-a-comunicação)
    - [1. Acessar a aplicação WordPress](#1-acessar-a-aplicação-wordpress)
8. [Conclusão](#conclusão)
9. [Recursos Adicionais](#recursos-adicionais)

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

## Passo 1: Criação da Rede Docker
Para que os containers possam se comunicar, vamos criar uma rede Docker.

```bash
docker network create wordpress-network
```

## Passo 2: Criação do Container MySQL

### 1. Iniciar o container MySQL
```bash
docker run --name mysql-container --network wordpress-network -e MYSQL_ROOT_PASSWORD=root_password -e MYSQL_DATABASE=my_database -e MYSQL_USER=user -e MYSQL_PASSWORD=user_password -v mysql_data:/var/lib/mysql -d mysql:5.7
```
- **--name**: Nome do container (mysql-container).
- **--network**: Rede Docker para o container (wordpress-network).
- **-e**: Variáveis de ambiente para configuração do MySQL.
- **-v**: Monta o volume para persistir os dados do MySQL.
- **-d**: Executar o container em modo desacoplado (em background).

## Passo 3: Criação do Container WordPress

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

## Passo 4: Testar a Comunicação

### 1. Acessar a aplicação WordPress
Abra o navegador web e vá para `http://localhost:8080`. Você deverá ver a página de configuração do WordPress se tudo estiver configurado corretamente.

## Conclusão
Você configurou com sucesso dois containers Docker (WordPress e MySQL) manualmente e configurou a comunicação entre eles usando uma rede Docker. Este exemplo usa WordPress, uma aplicação popular que depende do MySQL para armazenar dados.

## Recursos Adicionais
- [Documentação do Docker](https://docs.docker.com/)
- [Imagens Docker no Docker Hub](https://hub.docker.com/)
- [Documentação do WordPress](https://wordpress.org/support/)
- [Documentação do MySQL](https://dev.mysql.com/doc/)
"""

# Salvar o conteúdo em um arquivo Markdown
file_path = "EX01.md"
with open(file_path, "w") as file:
    file.write(markdown_content)

print(f"O arquivo Markdown foi salvo como {file_path}")
