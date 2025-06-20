import markdown
from weasyprint import HTML

def convert_markdown_to_modern_pdf(input_md_path, output_pdf_path):
    # Lê o conteúdo do Markdown
    with open(input_md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Converte o Markdown para HTML
    html_body = markdown.markdown(md_content, extensions=['extra', 'tables', 'sane_lists', 'toc'])

    # HTML + CSS com design clean e profissional
    html_template = f"""
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 2cm;
            }}
            body {{
                font-family: 'Helvetica Neue', Arial, sans-serif;
                color: #222;
                font-size: 11pt;
                line-height: 1.6;
                margin: 0;
            }}
            h1, h2, h3 {{
                color: #0B3D91;
                margin-bottom: 5px;
            }}
            h1 {{
                font-size: 20pt;
                border-bottom: 2px solid #0B3D91;
                padding-bottom: 5px;
            }}
            h2 {{
                font-size: 16pt;
                border-bottom: 1px solid #ccc;
                padding-bottom: 3px;
                margin-top: 25px;
            }}
            h3 {{
                font-size: 13pt;
                margin-top: 20px;
            }}
            ul {{
                margin-left: 20px;
            }}
            a {{
                color: #1a0dab;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            p {{
                margin: 5px 0 10px 0;
            }}
            .section {{
                margin-bottom: 25px;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin-top: 10px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 6px 8px;
            }}
            th {{
                background-color: #f2f2f2;
                text-align: left;
            }}
            blockquote {{
                border-left: 3px solid #ccc;
                padding-left: 10px;
                color: #555;
                font-style: italic;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 4px;
                border-radius: 4px;
                font-family: monospace;
            }}
        </style>
    </head>
    <body>
        {html_body}
    </body>
    </html>
    """

    # Gera o PDF
    HTML(string=html_template).write_pdf(output_pdf_path)
    print(f"✅ PDF generated at: {output_pdf_path}")

# Exemplo de uso:
convert_markdown_to_modern_pdf('PTBR.md', 'Joao Prado - PTBR.pdf')