# lidarr-bulk-adder/Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir: Reduces image size by not storing cache
# --upgrade pip: Ensures pip is up-to-date
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variables (optional defaults, can be overridden at runtime)
# These are useful if config.json doesn't exist yet
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
# ENV LIDARR_URL="" # No default, better to set at runtime or via config file
# ENV LIDARR_API_KEY="" # No default
# ENV LIDARR_ROOT_FOLDER="/music" # Default root folder if not set

# Create a directory for configuration data inside the container
# This is where we will mount the volume from the host
RUN mkdir /config

# Command to run the application using Flask's built-in server (suitable for development/small loads)
# For production, consider using a more robust WSGI server like Gunicorn:
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
CMD ["flask", "run"]