import fitz  # PyMuPDF
import json
import re
import requests
from io import BytesIO
from sentence_transformers import SentenceTransformer
import torch

# GitHub and Solr configurations
GITHUB_REPO = "Refio22/Rag-Unisannio"
DIRECTORY_PATH = "Documenti"
SOLR_URL = "http://localhost:8983/solr/regolamento_unisannio/update/json/docs"

# GitHub API URL for contents of the directory
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DIRECTORY_PATH}"

# Fetch the list of files in the GitHub directory
response = requests.get(API_URL)

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

# Load the pre-trained model and tokenizer (using nickprock/sentence-bert-base-italian-uncased)
def load_model():
    model = SentenceTransformer('nickprock/sentence-bert-base-italian-uncased')  # Load the Italian BERT model
    return model

# Function to generate embedding using Sentence-Transformers
def generate_embedding(text, model):
    # Generate embeddings from the model
    embeddings = model.encode(text, convert_to_tensor=True)
    return embeddings.cpu().numpy().tolist()

# Function to process and send each PDF file to Solr
def process_and_index_pdf(pdf_url, pdf_name, file_sha, model):
    response = requests.get(pdf_url)
    pdf_data = BytesIO(response.content)

    with fitz.open(stream=pdf_data, filetype="pdf") as pdf:
        content = ""
        for page in pdf:
            content += page.get_text("text")

    # Split content by "ARTICOLO " sections
    sections = content.split("ARTICOLO ")
    if len(sections) == 1:
        sections = content.split("Articolo ")

    structured_data = []

    # Process each section for Solr indexing
    for i, section_text in enumerate(sections[1:], start=1):  # Start from 1 to ignore header
        # Original title and content for indexing in Solr
        title = f"ARTICOLO {i}"
        content_text = section_text.strip()

        # Match patterns for the title using regular expressions
        match = re.match(r'^\s*\d+\s*[-–]\s*(.+?)(?:\n|$)', content_text)
        if match:
            title += f" {match.group(1)}"
            content_text = content_text[len(match.group(0)):].strip()
        else:
            lines = content_text.splitlines()
            if len(lines) > 1 and re.match(r'^\s*\d+\s*$', lines[0].strip()):
                title += f" {lines[1].strip()}"
                content_text = "\n".join(lines[2:]).strip()

        # Format the ID: replace underscores and dashes with spaces, remove "24 25", and append the article number
        base_id = pdf_name.rsplit('.', 1)[0]
        base_id = re.sub(r'[_\-.]', ' ', base_id)  # Replace delimiters with spaces
        base_id = re.sub(r'\b24 25\b', '', base_id).strip()  # Remove "24 25"
        base_id = re.sub(r'\s+', ' ', base_id).strip()  # Normalize spaces
        doc_id = f"{base_id} {i}".strip()  # Append article number

        # Prepare the embedding title (exclude "ARTICOLO {i}")
        embedding_title = re.sub(rf'ARTICOLO\s*{i}\s*', '', title).strip()

        # Remove "Regolamento" from the base_id for embedding calculation
        embedding_id = re.sub(r'^\s*Regolamento\s+', '', base_id).strip()

        # Combine only embedding_id and embedding_title for embedding generation
        combined_text = f"{embedding_id}. {embedding_title}"
        embedding_vector = generate_embedding(combined_text, model)
        if embedding_vector is None:
            print(f"Skipping indexing for {doc_id} due to embedding generation failure.")
            continue

        # Prepare JSON data for Solr with the formatted `id` and `title`
        json_data = {
            "id": doc_id,  # ID with article number for uniqueness
            "title": [title],  # Title array for Solr
            "content": content_text.strip(),
            "embedding_vector": embedding_vector,  # Embedding based on id and title
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


# Load the model (using nickprock/sentence-bert-base-italian-uncased)
model = load_model()

# Loop through each PDF file, download and process if it's new/updated
for pdf_file in pdf_files:
    pdf_name = pdf_file["name"]
    pdf_url = pdf_file["download_url"]
    file_sha = pdf_file["sha"]  # SHA for version checking

    # Check if document is already indexed
    if not is_document_indexed(SOLR_URL, pdf_name):
        process_and_index_pdf(pdf_url, pdf_name, file_sha, model)
    else:
        print(f"{pdf_name} already indexed, skipping.")