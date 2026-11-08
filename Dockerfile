FROM python:3.11-slim

# Set working directory
WORKDIR /code

# Install system dependencies for building packages if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/lists/*

# Copy lean deployment requirements and install them
COPY requirements-deploy.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Run the application as a non-root user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy the rest of the application code with proper permissions
COPY --chown=user . $HOME/app

EXPOSE 8000

# Start the FastAPI server via Uvicorn
CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]