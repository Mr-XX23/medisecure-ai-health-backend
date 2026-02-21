# 1) Create and activate virtualenv
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 2) Install FastAPI + Uvicorn
pip install fastapi uvicorn

# 3) install AI libs
pip install langgraph langchain-openai googlemaps

uvicorn main:app --port 8005 --reload

token = os.environ["GITHUB_TOKEN"]
endpoint = "https://models.github.ai/inference"
model = "openai/gpt-5-mini"