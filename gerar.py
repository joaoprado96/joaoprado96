import os
import re
from bs4 import BeautifulSoup
import markdownify

def markdown_table(rows):
    if not rows:
        return ""
    num_columns = len(rows[0])
    headers = [f'' for i in range(num_columns)]
    table = '| ' + ' | '.join(headers) + ' |\n'
    table += '| ' + ' | '.join(['---'] * num_columns) + ' |\n'
    for row in rows:
        table += f'| ' + ' | '.join(row) + ' |\n'
    return table

def format_table(table_html):
    soup = BeautifulSoup(table_html, 'html.parser')
    rows = [[cell.get_text(strip=True) for cell in tr.find_all(['td', 'th'])] for tr in soup.find_all('tr')]
    table_md = markdown_table(rows)
    return table_md

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
        for i in range(len(lines)):
            # Trocar o marcador
            if lines[i].startswith('* '):
                processed_lines.append(lines[i].replace('* ','+ ').rstrip())
                continue
            # Remover as linhas em branco
            if lines[i].strip():
                processed_lines.append(lines[i].rstrip())
                continue
        
        markdown_content = '\n'.join(processed_lines)

        return markdown_content
    else:
        return None

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

        # Add header to the markdown content
        header = f'---\ntitle: {title}\ntype: docs\nweight: 1\n---\n\n'
        markdown_content = header + markdown_content

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
    input_folder = './doc-html'
    output_folder = './'
    convert_all_html_in_folder(input_folder, output_folder)