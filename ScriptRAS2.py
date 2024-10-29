import fitz  # PyMuPDF
import json
import os
import requests
from io import BytesIO

# GitHub and Solr configurations from environment
SOLR_URL = os.getenv('SOLR_URL', 'http://localhost:8983/solr/#/regolamento_1/update/json/docs')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'Refio22/Rag-Unisannio')
DIRECTORY_PATH = os.getenv('DIRECTORY_PATH', 'Documenti')

# GitHub API URL for contents of the directory
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DIRECTORY_PATH}"

# Optional headers for private repo access (include token if needed)
# headers = {"Authorization": "token YOUR_GITHUB_TOKEN"}

# Fetch the list of files in the GitHub directory
response = requests.get(API_URL)  # , headers=headers

# Check if the response is valid JSON
try:
    files = response.json()
except json.JSONDecodeError:
    print("Failed to decode JSON response from GitHub API")
    files = []

# Ensure files is a list
if not isinstance(files, list):
    print("Unexpected response format from GitHub API")
    files = []

# Filter for PDF files
pdf_files = [file for file in files if file.get("name", "").endswith(".pdf")]

# Function to check if a document is already indexed in Solr
def is_document_indexed(solr_url, doc_id):
    query_url = f"{solr_url}/select?q=id:{doc_id}&wt=json"
    response = requests.get(query_url)
    try:
        response_json = response.json()
    except json.JSONDecodeError:
        print(f"Failed to decode JSON response from Solr for document ID: {doc_id}")
        return False
    return response_json.get('response', {}).get('numFound', 0) > 0

# Function to process and send each PDF file to Solr
def process_and_index_pdf(pdf_url, pdf_name, file_sha):
    response = requests.get(pdf_url)
    pdf_data = BytesIO(response.content)

    with fitz.open(stream=pdf_data, filetype="pdf") as pdf:
        content = ""
        for page in pdf:
            content += page.get_text("text")

    # Split content by "ARTICOLO" sections
    sections = content.split("ARTICOLO ")
    structured_data = []

    # Process each section for Solr indexing
    for i, section_text in enumerate(sections[1:], start=1):  # Start from 1 to ignore header
        doc_id = f"{pdf_name}-articolo-{i}"
        if not is_document_indexed(SOLR_URL, doc_id):
            title = f"{pdf_name} - ARTICOLO {i}"
            json_data = {
                "id": doc_id,
                "title": title,
                "content": f"ARTICOLO {section_text.strip()}",
                "file_sha": file_sha  # Use SHA to track file version
            }
            structured_data.append(json_data)

    # Post structured data to Solr
    for data in structured_data:
        response = requests.post(SOLR_URL, json=data)
        if response.status_code == 200:
            print(f"Indexed {data['id']} to Solr.")
        else:
            print(f"Failed to index {data['id']} to Solr. Status: {response.status_code}, Error: {response.text}")

# Loop through each PDF file, download and process if it's new/updated
for pdf_file in pdf_files:
    pdf_name = pdf_file["name"]
    pdf_url = pdf_file["download_url"]
    file_sha = pdf_file["sha"]  # SHA for version checking

    # Check if document is already indexed
    if not is_document_indexed(SOLR_URL, pdf_name):
        process_and_index_pdf(pdf_url, pdf_name, file_sha)
    else:
        print(f"{pdf_name} already indexed, skipping.")
