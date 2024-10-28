import fitz  # PyMuPDF
import json
import os
import requests
from io import BytesIO

# GitHub and Solr configurations from environment
SOLR_URL = os.getenv('SOLR_URL')

# GitHub and Solr configurations
GITHUB_REPO = "Refio22/Rag-Unisannio"
DIRECTORY_PATH = "Documenti"
SOLR_URL = "http://localhost:8983/solr/regolamento_1/update/json/docs"

# GitHub API URL for contents of the directory
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DIRECTORY_PATH}"

# Optional headers for private repo access (include token if needed)
# headers = {"Authorization": "token YOUR_GITHUB_TOKEN"}

# Fetch the list of files in the GitHub directory
response = requests.get(API_URL)
files = response.json()

# Ensure files is a list
if not isinstance(files, list):
    print("Unexpected response format from GitHub API")
    files = []

# Filter for PDF files
pdf_files = [file for file in files if file.get("name", "").endswith(".pdf")]
indexed_docs = set()

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
        indexed_docs.add(doc_id)
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

# Function to delete removed documents from Solr
def delete_removed_docs(solr_url, indexed_docs):
    query_url = f"{solr_url}/select?q=*:*&wt=json&rows=1000"
    response = requests.get(query_url)
    response_json = response.json()
    solr_docs = response_json.get('response', {}).get('docs', [])
    for doc in solr_docs:
        if doc['id'] not in indexed_docs:
            delete_url = f"{solr_url}?commit=true"
            delete_data = {"delete": {"id": doc['id']}}
            delete_response = requests.post(delete_url, json=delete_data)
            if delete_response.status_code == 200:
                print(f"Deleted {doc['id']} from Solr.")
            else:
                print(f"Failed to delete {doc['id']} from Solr. Status: {delete_response.status_code}, Error: {delete_response.text}")

# Loop through each PDF file, download and process if it's new/updated
for pdf_file in pdf_files:
    pdf_name = pdf_file["name"]
    pdf_url = pdf_file["download_url"]
    file_sha = pdf_file["sha"]  # SHA for version checking

    process_and_index_pdf(pdf_url, pdf_name, file_sha)

# Delete documents that no longer exist in the repository
delete_removed_docs(SOLR_URL, indexed_docs)
