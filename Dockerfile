FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Copy dependency definitions
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and files
COPY main.py ingest_articles.py test_gemini_assistant.py /app/
COPY README.md /app/

# Create folders for scratch/temp space
RUN mkdir -p /app/articles /app/chunks

# Run daily sync scraper-uploader by default
CMD ["python", "main.py"]
