# Dockerfile (in C:\Users\SULEKHA\OneDrive\Desktop\credit_approval_system)

# Use an official Python runtime as a parent image
FROM python:3.9-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install system dependencies needed for psycopg2
# These are required for Python to interact with PostgreSQL
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gcc \
    libpq-dev \
    # Clean up APT when done
    && rm -rf /var/lib/apt/lists/*

# Copy the backend project requirements file into the container
# Assuming requirements.txt is in backend/
COPY backend/requirements.txt /app/backend/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy the entire project into the container
# This copies your backend/ folder, customer_data.xlsx, loan_data.xlsx etc.
COPY . /app

# Set the backend directory as the current working directory for manage.py
WORKDIR /app/backend

# Expose port 8000 for Django
EXPOSE 8000

# Command to run the Django development server
# This will be overridden by docker-compose, but good for direct testing
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]