FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create data directories
RUN mkdir -p /app/data /app/datasets/OMIM /app/datasets/mondo

# Copy dataset files
COPY datasets/OMIM/mimTitles.txt /app/datasets/OMIM/
COPY datasets/OMIM/genemap2.txt /app/datasets/OMIM/
COPY datasets/mondo/mondo.json /app/datasets/mondo/

# Copy genemap2.txt to local data directory (for compatibility)
COPY data/genemap2.txt /app/data/

# Copy application code
COPY . /app/

# Expose port
EXPOSE 8002

# Run the application
CMD ["python", "main.py"]