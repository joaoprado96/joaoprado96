import os
import re
from bs4 import BeautifulSoup
import markdownify
from markdown import MarkdownRewriter
from stackspot import ExecucaoComandoRapido
import re

def replace_single_quotes(text):
    # Define o padrão regex para encontrar conteúdos entre " " ( ) [ ] <>
    pattern = r'("[^"]*"|\([^)]*\)|\[[^\]]*\]|<[^>]*>)'
    
    # Substitui os conteúdos encontrados por aspas simples
    result = re.sub(pattern, "'", text)
    
    return result

def process_html_content(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    main_content = soup.find(id='main-content')

    if main_content:
        markdown_content = markdownify.markdownify(str(main_content), 
                                                   heading_style="ATX",
                                                   strip_comments=True,
                                                   escape_underscores=True
                                                   )

        # Remove unnecessary line breaks but keep them before headers, lists, and citations
        lines = markdown_content.split('\n')
        processed_lines = []
        inside_table = False

        for i in range(len(lines)):
            # Trocar o marcador
            if lines[i].startswith('* '):
                processed_lines.append(lines[i].replace('* ', '+ ').rstrip())
                continue
            
            # Ajusta as linhas com titulos para colocar espacamento antes e depois
            if lines[i].lstrip().startswith('#'):
                processed_lines.append("     ")
                processed_lines.append(lines[i])
                processed_lines.append("     ")
                continue
            
            # Remove as linhas de cabecalho de tabela
            if lines[i].lstrip().startswith("| --"):
                continue

            # Verificar se estamos dentro de uma tabela
            if lines[i].lstrip().startswith("|") and not inside_table:
                inside_table = True
                processed_lines.append("\n<!-- Tabela Início -->")
                columns = lines[i].count('|') - 1
                separator = "| " + " | ".join(["---"] * columns) + " |"
                separator_branco = "| " + " | ".join(["   "] * columns) + " |"
                processed_lines.append(separator_branco)
                processed_lines.append(separator)
                processed_lines.append(lines[i].rstrip())
                # Verifica a próxima linha para manter dentro da tabela
                if not (i + 1 < len(lines) and lines[i+1].lstrip().startswith("|")):
                    inside_table = False
                    processed_lines.append("<!-- Tabela Fim -->\n")
                continue

            if inside_table:
                if lines[i].lstrip().startswith("|"):
                    processed_lines.append(lines[i].rstrip())
                else:
                    inside_table = False
                    processed_lines.append("<!-- Tabela Fim -->\n")
                continue

            # Remover as linhas em branco
            if lines[i].strip():
                processed_lines.append(lines[i].rstrip())
                continue

        # Se o arquivo termina dentro de uma tabela
        if inside_table:
            processed_lines.append("<!-- Tabela Fim -->\n")
            inside_table = False

        markdown_content = '\n'.join(processed_lines)

        return markdown_content
    else:
        return None

def quebrar_em_blocos(markdown_content, tamanho_bloco=150):
    linhas = markdown_content.split('\n')
    blocos = [linhas[i:i + tamanho_bloco] for i in range(0, len(linhas), tamanho_bloco)]
    return ["\n".join(bloco) for bloco in blocos]

def executar_comandos_rapidos(executor, slug, blocos):
    respostas = []
    for bloco in blocos:
        sucesso, resultado = executor.executar_comando_rapido(slug=slug, input_data={"doc": bloco})
        if sucesso:
            respostas.append(resultado)
        else:
            respostas.append("ERRO: Consulta falhou na execucao do Comando")
            print("Erro ao executar comando rápido")
    return "\n".join(respostas)


def convert_html_file_to_markdown(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    markdown_content = process_html_content(html_content)

    if markdown_content is not None:
        soup = BeautifulSoup(html_content, 'html.parser')
        # Extract title from meta tag
        title = soup.find('meta', {'name': 'wikilink'})['content'].split(':')[-1].strip()
        
        chars_to_replace = [']', '[', '{', '}', '#', '*', '+', '.', '!', '`', '>', '<', '~', '|', '=']
        for char in chars_to_replace:
            title = title.replace(char, '')

        header = f'---\ntitle: {title}\ntype: docs\nweight: 1\n---\n\n'
        markdown_content = header + markdown_content
        executor = ExecucaoComandoRapido(
            base_url="https://genai-code-buddy-api.stackspot.com",
            client_id="119d6c80-5ad7-4815-8d6a-79523db69158",
            client_secret="BbGRM3a8d255o7W6dw4bp87oGCAIaNuB6eYxgFVW11Kv75h35UOa4Xe4bzsZE0ft",
            intervalo_consultas=8,  # tempo em segundos entre as consultas
            proxies={}
        )

        if len(markdown_content.split('\n')) > 250:
            blocos = quebrar_em_blocos(markdown_content)
            resultado_final = executar_comandos_rapidos(executor, "revisao-doc", blocos)
        else:
            sucesso, resultado_final = executor.executar_comando_rapido(slug="revisao-doc", input_data={"doc": markdown_content})

        with open(f'{output_file[:-3]}stack.md', 'w', encoding='utf-8') as f:
            f.write(resultado_final)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"Arquivo convertido e salvo em {output_file}")
    else:
        print("Elemento com id 'main-content' não encontrado.")

def convert_all_html_in_folder(input_folder, output_folder):
    for filename in os.listdir(input_folder):
        if filename.endswith('.html'):
            input_file = os.path.join(input_folder, filename)
            output_file = os.path.join(output_folder, filename.replace('.html', '.md'))

            convert_html_file_to_markdown(input_file, output_file)

if __name__ == "__main__":
    input_folder = './doc-html-2'
    output_folder = './doc-md'
    convert_all_html_in_folder(input_folder, output_folder)