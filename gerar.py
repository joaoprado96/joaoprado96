import os
import re
from bs4 import BeautifulSoup
import markdownify
import re
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize

# Download nltk resources if not already available
nltk.download('punkt')

def format_string(input_string):
    # Remover espaços desnecessários
    input_string = input_string.strip()
    
    # Tokenizar o texto em palavras
    words = word_tokenize(input_string)
    
    formatted_sentences = []
    current_sentence = []
    
    for i, word in enumerate(words):
        # Verificar se é um código seguido de uma descrição
        if word.isupper() and (i + 1 < len(words) and not words[i + 1].isupper()):
            # Adicionar a sentença atual à lista se houver
            if current_sentence:
                formatted_sentences.append(' '.join(current_sentence))
            current_sentence = [word]
        else:
            current_sentence.append(word)
    
    # Adicionar a última sentença se houver
    if current_sentence:
        formatted_sentences.append(' '.join(current_sentence))
    
    # Reconstituir o texto formatado com sentenças separadas por vírgula
    formatted_string = ", ".join(formatted_sentences)
    return formatted_string

def format_table(table_html):
    soup = BeautifulSoup(table_html, 'html.parser')
    rows = [[cell.get_text(strip=True) for cell in tr.find_all(['td', 'th'])] for tr in soup.find_all('tr')]

    long_contents = {}  # Dictionary to store long contents and their identifiers

    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if len(cell) > 150:  # If the cell content is too long
                identifier = f'({i}-{j})'  # Create an identifier based on the cell's position
                long_contents[identifier] = format_string(cell)  # Store the long content and its identifier
                rows[i][j] = identifier  # Replace the cell content with the identifier

    if soup.find('tr').find('th'):  # Check if the first row contains 'th' elements
        table_md = markdown_table_with_headers(rows)
    else:
        table_md = markdown_table_without_headers(rows)

    # Add the long contents to the table description
    table_description = '\n'.join(f'> {identifier} {content}\n' for identifier, content in long_contents.items())
    table_md += '---\n' + table_description + '\n'

    return table_md

def markdown_table_with_headers(rows):
    headers = rows[0]
    table = '| ' + ' | '.join(headers) + ' |\n'
    table += '| ' + ' | '.join(['---'] * len(headers)) + ' |\n'
    for row in rows[1:]:
        table += '| ' + ' | '.join(row) + ' |\n'
    table += '\n'
    return table

def markdown_table_without_headers(rows):
    table = ''
    for row in rows:
        table += '| ' + ' | '.join(row) + ' |\n'
    table += '\n'
    return table

def process_html_content(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    main_content = soup.find(id='main-content')

    if main_content:
        # Process tables separately
        for table in main_content.find_all('table'):
            formatted_table = format_table(str(table))
            table.replace_with(BeautifulSoup(formatted_table, 'html.parser'))

        markdown_content = markdownify.markdownify(str(main_content), heading_style="ATX")

        # Remove unnecessary line breaks but keep them before headers, lists, and citations
        lines = markdown_content.split('\n')
        processed_lines = []
        for i in range(len(lines)):
            if (i < len(lines) - 1 and re.match(r'^\s*$', lines[i]) and
                not (lines[i + 1].startswith('#') or lines[i + 1].startswith('*') or lines[i + 1].startswith('>'))):
                continue
            processed_lines.append(lines[i].rstrip())
        markdown_content = '\n'.join(processed_lines)

        # Add line breaks before "Observação:" e "Legenda:"
        markdown_content = markdown_content.replace('**Observação:**', '\n**Observação:**\n')
        markdown_content = markdown_content.replace('**Legenda:**', '\n**Legenda:**\n')

        return markdown_content
    else:
        return None

def convert_html_file_to_markdown(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    markdown_content = process_html_content(html_content)  # Call process_html_content here

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