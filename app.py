import os
import requests
import json
import time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- Define Application Version ---
APP_VERSION = "0.1.1"
# ---

CONFIG_FILE = 'config.json'

# --- Configuration Handling ---
def load_config():
    config = {
        'LIDARR_URL': '',
        'API_KEY': '',
        'ROOT_FOLDER_PATH': '/music'
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config.update(json.load(f))
        except json.JSONDecodeError:
            print(f"Warning: Could not decode {CONFIG_FILE}. Using defaults/environment variables.")
        except Exception as e:
             print(f"Warning: Error reading {CONFIG_FILE}: {e}. Using defaults/environment variables.")

    config['LIDARR_URL'] = os.environ.get('LIDARR_URL', config.get('LIDARR_URL', ''))
    config['API_KEY'] = os.environ.get('LIDARR_API_KEY', config.get('API_KEY', ''))
    config['ROOT_FOLDER_PATH'] = os.environ.get('LIDARR_ROOT_FOLDER', config.get('ROOT_FOLDER_PATH', '/music'))

    if config['LIDARR_URL']:
        config['LIDARR_URL'] = config['LIDARR_URL'].rstrip('/')
    return config

def save_config(config_data):
    try:
        save_data = {
            'LIDARR_URL': config_data.get('LIDARR_URL', '').rstrip('/'),
            'API_KEY': config_data.get('API_KEY', ''),
            'ROOT_FOLDER_PATH': config_data.get('ROOT_FOLDER_PATH', '/music')
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(save_data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# --- Lidarr API Logic ---
def search_and_add_artist(artist_name, config):
    if not config.get('LIDARR_URL') or not config.get('API_KEY'):
        return {"status": "error", "message": "Lidarr URL or API Key not configured."}
    if not config.get('ROOT_FOLDER_PATH'):
         return {"status": "error", "message": "Root Folder Path not configured."}

    print(f"🔍 Searching for artist: {artist_name}")
    search_term_encoded = requests.utils.quote(artist_name)
    lookup_url = f"{config['LIDARR_URL']}/api/v1/artist/lookup?term={search_term_encoded}"
    headers = {"X-Api-Key": config['API_KEY']}

    try:
        response = requests.get(lookup_url, headers=headers, timeout=30)
        response.raise_for_status()
        lookup_results = response.json()

        if not lookup_results:
            print(f"❌ Artist not found via API: {artist_name}")
            return {"status": "not_found", "artist": artist_name}

        artist_to_add = lookup_results[0]
        artist_id = artist_to_add.get("foreignArtistId")
        actual_artist_name = artist_to_add.get("artistName")

        if not artist_id or not actual_artist_name:
             print(f"❌ API response missing data for: {artist_name}")
             return {"status": "error", "message": f"API response missing data for: {artist_name}"}

        existing_artist_url = f"{config['LIDARR_URL']}/api/v1/artist"
        existing_response = requests.get(existing_artist_url, headers=headers, timeout=15)
        existing_response.raise_for_status()
        for existing_artist in existing_response.json():
            if existing_artist.get('artistName', '').lower() == actual_artist_name.lower():
                print(f"ℹ️ Artist already exists in Lidarr: {actual_artist_name}")
                return {"status": "already_exists", "artist": actual_artist_name}

        artist_folder_name = actual_artist_name.replace(':', '_').replace('/', '_').replace('\\', '_')

        body = {
            "foreignArtistId": artist_id,
            "metadataProfileId": 1,
            "qualityProfileId": 1,
            "monitored": True,
            "artistName": actual_artist_name,
            "rootFolderPath": config['ROOT_FOLDER_PATH'],
            "path": os.path.join(config['ROOT_FOLDER_PATH'], artist_folder_name),
            "addOptions": { "searchForMissingAlbums": True }
        }

        add_artist_url = f"{config['LIDARR_URL']}/api/v1/artist"
        add_headers = headers.copy()
        add_headers["Content-Type"] = "application/json"
        add_response = requests.post(add_artist_url, headers=add_headers, data=json.dumps(body), timeout=30)
        add_response.raise_for_status()

        print(f"✅ Added: {actual_artist_name}")
        return {"status": "added", "artist": actual_artist_name}

    except requests.exceptions.Timeout:
        print(f"❌ Timeout connecting to Lidarr for artist: {artist_name}")
        return {"status": "error", "message": f"Timeout connecting to Lidarr for artist: {artist_name}"}
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to process {artist_name}. Error: {e}")
        error_message = str(e)
        try:
            error_details = e.response.json()
            if isinstance(error_details, list) and error_details: error_message = error_details[0].get('errorMessage', str(e))
            elif isinstance(error_details, dict): error_message = error_details.get('message', str(e))
        except: pass
        return {"status": "error", "artist": artist_name, "message": f"Lidarr API Error: {error_message}"}
    except Exception as e:
        print(f"❌ Unexpected error processing {artist_name}. Error: {e}")
        return {"status": "error", "artist": artist_name, "message": f"Unexpected error: {str(e)}"}

# --- Flask Routes ---
@app.route('/', methods=['GET'])
def index():
    config = load_config()
    status_message = None
    if not config.get('LIDARR_URL') or not config.get('API_KEY'):
        status_message = 'Lidarr URL or API Key is not configured. Please configure them in Settings.'
    return render_template('index.html', config=config, app_version=APP_VERSION, status_message=status_message)

@app.route('/add', methods=['POST'])
def add_artists_route():
    config = load_config()
    results = []
    artists_input = ""

    if 'artist_list_paste' in request.form and request.form['artist_list_paste'].strip():
        artists_input = request.form['artist_list_paste']
    elif 'artist_list_file' in request.files:
        file = request.files['artist_list_file']
        if file.filename != '':
            try:
                artists_input = file.read().decode('utf-8')
            except Exception as e:
                return jsonify({"status": "error", "message": f"Error reading uploaded file: {e}"}), 400
        elif not artists_input:
             return jsonify({"status": "error", "message": "Please paste a list of artists or upload a file."}), 400
    else:
         return jsonify({"status": "error", "message": "No artist data provided."}), 400

    artists = [artist.strip() for artist in artists_input.splitlines() if artist.strip()]

    if not artists:
        return jsonify({"status": "error", "message": "No valid artist names found in the input."}), 400

    print(f"Processing {len(artists)} artists...")
    total_artists = len(artists)
    processed_count = 0
    errors = []
    messages = []  # Detailed messages for each artist
    for artist in artists:
        result = search_and_add_artist(artist, config)
        results.append(result)
        processed_count += 1
        progress = int((processed_count / total_artists) * 100)
        print(f"Processed {processed_count}/{total_artists} ({progress}%)")
        time.sleep(0.5)
        if result['status'] == 'added':
            messages.append(f"Successfully added: {result['artist']}")
        elif result['status'] == 'already_exists':
            messages.append(f"Already exists on Lidarr: {result['artist']}")
        elif result['status'] == 'not_found':
            messages.append(f"Not found: {result['artist']}")
        elif result['status'] == 'error':
            messages.append(f"Error adding {artist}: {result.get('message', 'Unknown error')}")
            errors.append({"artist": artist, "message": result.get('message', 'Unknown error')})

    summary = {
        "added": sum(1 for r in results if r['status'] == 'added'),
        "already_exists": sum(1 for r in results if r['status'] == 'already_exists'),
        "not_found": sum(1 for r in results if r['status'] == 'not_found'),
        "error": sum(1 for r in results if r['status'] == 'error'),
        "total": len(artists)
    }
    response_data = {
        "status": "complete",
        "progress": 100,
        "summary": summary,
        "errors": errors,
        "messages": messages
    }
    return jsonify(response_data), 200

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    config = load_config()

    if request.method == 'POST':
        new_config = config.copy()
        new_config['LIDARR_URL'] = request.form.get('lidarr_url', '').strip().rstrip('/')
        new_config['API_KEY'] = request.form.get('api_key', '').strip()
        new_config['ROOT_FOLDER_PATH'] = request.form.get('root_folder_path', '').strip()

        if not new_config['LIDARR_URL'] or not new_config['API_KEY'] or not new_config['ROOT_FOLDER_PATH']:
             flash('Lidarr URL, API Key, and Root Folder Path cannot be empty.', 'danger')
             return render_template('settings.html', config=new_config, app_version=APP_VERSION)

        if save_config(new_config):
            flash('Settings saved successfully!', 'success')
        else:
            flash('Error saving settings. Check container logs.', 'danger')
        return redirect(url_for('settings'))

    return render_template('settings.html', config=config, app_version=APP_VERSION)

# --- Main Execution ---
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)