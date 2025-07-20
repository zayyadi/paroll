# Use an official lightweight Python image.
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create a non-root user
RUN addgroup --system app && adduser --system --group app

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Chown all the files to the app user
RUN chown -R app:app /app

# Change to the app user
USER app

# Expose the port
EXPOSE 8000

# Run gunicorn
CMD ["gunicorn", "--bind", ":8000", "--workers", "3", "core.wsgi:application"]