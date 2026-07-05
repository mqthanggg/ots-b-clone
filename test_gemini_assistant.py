import os
import sys
import json
import time
from google import genai

def load_dotenv(dotenv_path=".env"):
    """
    A simple, zero-dependency parser to load variables from a .env file.
    """
    if os.path.exists(dotenv_path):
        print(f"Loading environment variables from {dotenv_path}...")
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        os.environ[key] = val

def run_query(client, resolved_files, question, system_instruction):
    """
    Sends the user query along with the referenced files to the Gemini model
    and prints the response with citations.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=resolved_files + [
                f"{system_instruction}\n\nUser Question: {question}"
            ]
        )
        print("\n================== Gemini Response ==================")
        print(response.text)
        print("=====================================================\n")
    except Exception as e:
        print(f"[ERROR] Generation request failed: {e}")

def main():
    load_dotenv()
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[ERROR] GEMINI_API_KEY is not set.")
        print("Please add GEMINI_API_KEY=your-api-key to your .env file.")
        return
        
    config_path = os.path.join(os.getcwd(), 'gemini_config.json')
    if not os.path.exists(config_path):
        print(f"[ERROR] Gemini config not found at {config_path}.")
        print("Please run main.py first to sync and create the active files list.")
        return
        
    with open(config_path, 'r', encoding='utf-8') as jf:
        config_data = json.load(jf)
        
    uploaded_files = config_data.get("uploaded_files", [])
    if not uploaded_files:
        print("[ERROR] No active uploaded files found in gemini_config.json.")
        return
        
    print("Initializing Gemini Client...")
    client = genai.Client(api_key=api_key)
    
    print(f"Retrieving active files status for {len(uploaded_files)} files...")
    resolved_files = []
    
    for file_name in uploaded_files:
        try:
            uploaded_file = client.files.get(name=file_name)
            
            # Wait if file is still processing
            while uploaded_file.state.name == "PROCESSING":
                print(f"  File {file_name} is processing, waiting 5 seconds...")
                time.sleep(5)
                uploaded_file = client.files.get(name=file_name)
                
            if uploaded_file.state.name == "ACTIVE":
                resolved_files.append(uploaded_file)
            else:
                print(f"  [WARNING] File {file_name} is not active: {uploaded_file.state.name}")
        except Exception as e:
            # Silence specific file get failures if they expired, but alert general issues
            pass
            
    if not resolved_files:
        print("[ERROR] No active files could be resolved on Gemini Storage.")
        print("Your temporary files may have expired. Please re-run main.py to sync them.")
        return
        
    system_instruction = (
        "You are an expert support assistant for OptiSigns digital signage.\n"
        "Your goal is to answer users' technical support and configuration questions "
        "using ONLY the knowledge provided in the attached files.\n\n"
        "Rules:\n"
        "1. Answer queries concisely and clearly, outlining steps as formatted bullet points or ordered lists.\n"
        "2. Always cite your sources by referencing the relevant article title and section heading "
        "exactly as written in the document metadata (e.g. 'According to the article [Title] (Section [Section Name])...').\n"
        "3. If the answer cannot be found in the attached files, state that you do not have that information."
    )
    
    # Check if a question was passed in the CLI arguments
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(f"\nQuerying Gemini (gemini-2.5-flash) with: '{question}'...")
        run_query(client, resolved_files, question, system_instruction)
    else:
        # Start interactive CLI loop
        print("\n" + "=" * 65)
        print("   OptiSigns Support Assistant CLI (Google Gemini In-Context RAG)")
        print("=" * 65)
        print("Type your questions below. Type 'exit' or 'quit' to end the session.\n")
        
        while True:
            try:
                question = input("User Question > ").strip()
                if not question:
                    continue
                if question.lower() in ['exit', 'quit']:
                    print("Goodbye!")
                    break
                
                print("Assistant: [Thinking...]")
                run_query(client, resolved_files, question, system_instruction)
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

if __name__ == "__main__":
    main()
