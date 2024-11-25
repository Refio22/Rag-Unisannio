import requests
import json
import torch
from transformers import AutoTokenizer, AutoModel
from sentence_transformers import SentenceTransformer

# Solr and Ollama configurations
SOLR_URL = "http://localhost:8983/solr/regolamento_unisannio/query"
OLLAMA_COMPLETIONS_URL = "http://localhost:11434/v1/completions"
headers = {"Content-Type": "application/json"}

# Load the nickprock/sentence-bert-base-italian-uncased model and tokenizer
tokenizer = AutoTokenizer.from_pretrained("nickprock/sentence-bert-base-italian-uncased")
model = AutoModel.from_pretrained("nickprock/sentence-bert-base-italian-uncased")


def generate_embedding(text):
    """
    Generate an embedding for the given text using the nickprock/sentence-bert-base-italian-uncased.
    Returns the embedding as a list of floats.
    """
    try:
        inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
        with torch.no_grad():
            outputs = model(**inputs)
            # Use the mean pooling of the last hidden states to get the sentence embedding
            embeddings = outputs.last_hidden_state.mean(dim=1).squeeze()

        # Convert to list for compatibility with JSON
        embedding_list = embeddings.tolist()
        return embedding_list
    except Exception as e:
        print(f"Error generating embedding with nickprock/sentence-bert-base-italian-uncased: {e}")
        return None


def fetch_relevant_documents_embeddings(question, num_results=3):
    """
    Fetch relevant documents from Solr using embedding-based similarity with POST method.
    Always fetches top 3 documents and selects the highest-scoring one.
    """
    # Generate the embedding for the question
    query_embedding = generate_embedding(question)
    if query_embedding is None:
        print("Failed to generate query embedding.")
        return []

    # Constructing the Solr query parameters and JSON body for POST
    params = {
        'q': '{!knn f=embedding_vector topK=' + str(num_results) + '}' + json.dumps(query_embedding),
        'fl': 'id,title,content,score'  # Fields to return
    }

    # Debug: Print the payload to verify structure
    #print("Solr Query Parameters:", json.dumps(params, indent=2))

    try:
        # Make the POST request with the embedding vector in the JSON body
        response = requests.post(SOLR_URL, headers=headers, json={'params': params})
        response.raise_for_status()

        # Debug: Print Solr response
        #print("Solr Response:", response.json())

        data = response.json()

        if data['response']['numFound'] == 0:
            print("No relevant documents found using embeddings.")
            return []

        # Retrieve and process documents
        documents = data['response']['docs']

        # Find the document with the highest score
        top_document = max(documents, key=lambda doc: doc['score'], default=None)
        if top_document:
            print(f"Top Document ID: {top_document['id']}, Top Document Title: {top_document['title']}, Score: {top_document['score']}")
            return [top_document]  # Return a list with only the top document

        return []

    except requests.RequestException as e:
        print(f"Error fetching documents from Solr with embeddings: {e}")
        return []


def generate_answer_with_ollama(question, context):
    """
    Generates an answer using the Ollama model with the provided question and context.
    The answer will be in Italian based on the provided context.
    """
    # Construct the prompt with the question and context
    prompt = f"Domanda: {question}\n\nContesto: {context}\n\nRisposta:"
    try:
        response = requests.post(
            OLLAMA_COMPLETIONS_URL,
            headers=headers,
            json={"prompt": prompt, "model": "llama3"}  # Ensure this model is suitable for completion tasks
        )
        response.raise_for_status()

        # Print full response for debugging
        response_json = response.json()
        #print("Ollama Response JSON:", json.dumps(response_json, indent=2))

        # Check if the expected "choices" key is present in the response
        choices = response_json.get("choices")
        if not choices or not isinstance(choices, list) or not choices[0].get("text"):
            print("No answer text found in Ollama response.")
            return "Errore nella generazione della risposta."  # Friendly error message

        answer = choices[0]["text"]
        return answer
    except requests.RequestException as e:
        print(f"Error generating answer with Ollama: {e}")
        return "Errore nella generazione della risposta."


def retrieve_and_answer(question):
    """
    Retrieve relevant documents based on the question and generate an answer.
    """
    documents = fetch_relevant_documents_embeddings(question)
    if not documents:
        return "No relevant documents found to answer the question."

    context = " ".join(doc['content'] for doc in documents if 'content' in doc)
    answer = generate_answer_with_ollama(question, context)
    return answer


if __name__ == "__main__":
    question = input("Inserisci la tua domanda: ")
    answer = retrieve_and_answer(question)
    print(f"Risposta: {answer}")

