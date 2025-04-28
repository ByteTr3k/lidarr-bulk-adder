# Lidarr Bulk Adder

**Version:** 0.1.0 A simple web application, designed to run in Docker, for bulk-adding artists to your [Lidarr](https://lidarr.audio/) instance via its API.

[![Docker Image Size](https://img.shields.io/docker/image-size/bytetrek/lidarr-bulk-adder/latest)](https://hub.docker.com/r/bytetrek/lidarr-bulk-adder) [![GitHub Repo stars](https://img.shields.io/github/stars/ByteTr3k/lidarr-bulk-adder?style=social)](https://github.com/ByteTr3k/lidarr-bulk-adder) ## Features

* **Web Interface:** Easy-to-use UI accessible from your browser.
* **Bulk Add:** Add multiple artists by pasting a list (one artist per line) or uploading a `.txt` file.
* **Configuration UI:** Set your Lidarr URL, API Key, and Root Folder Path via a simple settings page.
* **Persistent Settings:** Configuration *can be made* persistent using Docker volumes or bind mounts (see Configuration Notes).
* **Dockerized:** Runs as a lightweight Docker container, suitable for NAS devices (like Synology) or any Docker host.
* **Dark Mode:** Easy on the eyes!

## Requirements

* [Docker](https://www.docker.com/) installed on your host machine (PC, Server, NAS, etc.).
* A running instance of [Lidarr](https://lidarr.audio/).
* Network access from the machine running this Docker container to your Lidarr instance.

## Running the Application

Choose **one** method below based on how you want to handle configuration persistence.

**Method 1: No Persistent Settings (Easiest, settings lost on recreate)**

```bash
docker run -d \
  --name lidarr-bulk-adder-app \
  -p 5050:5000 \
  bytetrek/lidarr-bulk-adder:latest # Or use specific version e.g., :v0.1.0