import re
from bs4 import BeautifulSoup
import markdownify

def format_table(table_html):
    soup = BeautifulSoup(table_html, 'html.parser')
    
    # Extract table headers and rows
    headers = [th.get_text(strip=True) for th in soup.find_all('th')]
    rows = [[td.get_text(strip=True) for td in tr.find_all('td')] for tr in soup.find_all('tr')]

    if not headers and rows:
        headers = rows[0]
        rows = rows[1:]
    
    # Ensure all rows have the same number of columns as headers
    num_columns = len(headers)
    for row in rows:
        while len(row) < num_columns:
            row.append('')

    return markdown_table(headers, rows)

def markdown_table(headers, rows):
    table = '| ' + ' | '.join(headers) + ' |\n'
    table += '| ' + ' | '.join(['---'] * len(headers)) + ' |\n'
    for row in rows:
        table += '| ' + ' | '.join(row) + ' |\n'
    return table

def process_html_content(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    main_content = soup.find(id='main-content')

    if main_content:
        # Extract and remove observations and legends before processing tables
        observations = []
        legends = []
        
        for tag in main_content.find_all():
            if 'Observação:' in tag.text:
                observations.append(tag.text)
                tag.decompose()
            elif 'Legenda:' in tag.text:
                legends.append(tag.text)
                tag.decompose()

        # Process tables separately
        for table in main_content.find_all('table'):
            formatted_table = format_table(str(table))
            table.replace_with(BeautifulSoup(formatted_table, 'html.parser'))

        markdown_content = markdownify.markdownify(str(main_content), heading_style="ATX")

        # Remove unnecessary line breaks but keep them before headers and lists
        lines = markdown_content.split('\n')
        processed_lines = []
        for i in range(len(lines)):
            if (i < len(lines) - 1 and re.match(r'^\s*$', lines[i]) and
                not (lines[i + 1].startswith('#') or lines[i + 1].startswith('*'))):
                continue
            processed_lines.append(lines[i].rstrip())
        markdown_content = '\n'.join(processed_lines)

        # Reinsert observations and legends with line breaks before them
        for obs in observations:
            markdown_content += '\n\n' + obs + '\n'
        for leg in legends:
            markdown_content += '\n\n' + leg + '\n'

        return markdown_content
    else:
        return None

def convert_html_file_to_markdown(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    markdown_content = process_html_content(html_content)

    if markdown_content:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"Arquivo convertido e salvo em {output_file}")
    else:
        print("Elemento com id 'main-content' não encontrado.")

# Usage example
# convert_html_file_to_markdown('input.html', 'output.md')