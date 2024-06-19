import docx
import os

def read_docx(file_path):
    doc = docx.Document(file_path)
    elements = []

    def handle_paragraph(para):
        style = para.style.name
        text = para.text.strip()

        if style.startswith('Heading'):
            level = int(style.split(' ')[1])
            elements.append('#' * level + ' ' + text)
        elif style in ['Normal', 'BodyText', 'Body Text', 'Body Text Indent']:
            elements.append(text)
        elif style in ['List Bullet', 'List Bullet 2', 'List Bullet 3']:
            elements.append(f"* {text}")
        elif style in ['List Number', 'List Number 2', 'List Number 3']:
            elements.append(f"1. {text}")
        elif style == 'TOCHeading':
            elements.append(f"[TOC] {text}")
        else:
            elements.append(text)

    def handle_table(table):
        table_data = []
        for i, row in enumerate(table.rows):
            row_data = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
            table_data.append('| ' + ' | '.join(row_data) + ' |')
            
            # Add header separator after the first row
            if i == 0:
                header_separator = '| ' + ' | '.join(['---'] * len(row.cells)) + ' |'
                table_data.insert(1, header_separator)
        
        elements.extend(table_data)

    def handle_table_of_contents(doc):
        for para in doc.paragraphs:
            if para.style.name.startswith('TOC'):
                elements.append(para.text.strip())

    # Handle the table of contents first
    handle_table_of_contents(doc)

    # Handle the paragraphs and tables
    for para in doc.paragraphs:
        handle_paragraph(para)

    for table in doc.tables:
        handle_table(table)

    # Convert tabs to spaces (4 spaces per tab)
    content = '\n\n'.join(elements).replace('\t', '    ')

    # Ensure proper line breaks
    content = content.replace('\n', '  \n')

    return content

def save_markdown(markdown_content, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

def convert_docx_to_markdown(input_file, output_file):
    docx_content = read_docx(input_file)
    save_markdown(docx_content, output_file)

# Exemplo de uso
input_file = 'documentacao.docx'
output_file = 'documentacao.md'

# Verifique se o arquivo de entrada existe
if not os.path.isfile(input_file):
    print(f"Arquivo de entrada {input_file} não encontrado.")
else:
    convert_docx_to_markdown(input_file, output_file)
    print(f"Arquivo convertido e salvo em {output_file}")