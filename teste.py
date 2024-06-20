import re
from bs4 import BeautifulSoup
import markdownify
import markdown_table

def convert_html_file_to_markdown(input_file, output_file):
    def format_table(table_html):
        soup = BeautifulSoup(table_html, 'html.parser')
        headers = [th.get_text(strip=True) for th in soup.find_all('th')]
        rows = [[td.get_text(strip=True) for td in tr.find_all('td')] for tr in soup.find_all('tr')]
        return markdown_table.create(headers, rows)

    with open(input_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    main_content = soup.find(id='main-content')

    if main_content:
        # Process tables separately
        for table in main_content.find_all('table'):
            table.replace_with(BeautifulSoup(format_table(str(table)), 'html.parser'))
        
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

        # Add line breaks before "Observação:" and "Legenda:"
        markdown_content = markdown_content.replace('**Observação:**', '\n**Observação:**\n')
        markdown_content = markdown_content.replace('**Legenda:**', '\n**Legenda:**\n')

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"Arquivo convertido e salvo em {output_file}")
    else:
        print("Elemento com id 'main-content' não encontrado.")