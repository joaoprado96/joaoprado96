import os
import pypandoc

def convert_markdown_to_pdf(input_file, output_folder):
    # Ensure the output folder exists
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Define the output PDF file path
    base_name = os.path.basename(input_file)
    name_without_ext = os.path.splitext(base_name)[0]
    pdf_file = os.path.join(output_folder, name_without_ext + '.pdf')

    # Convert Markdown to PDF using Pandoc
    pypandoc.convert_file(input_file, 'pdf', outputfile=pdf_file)

    print(f"Conversion complete!\nPDF file is saved in '{output_folder}'.")

if __name__ == '__main__':
    input_markdown_file = 'README.md'  # Change this if your file has a different name
    output_directory = 'output_files'  # Change this to your desired output folder

    convert_markdown_to_pdf(input_markdown_file, output_directory)