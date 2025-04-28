# lidarr-bulk-adder/app.py
import os
import requests
import json
import time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24) # Needed for flashing messages

CONFIG_FILE = 'config.json'

# --- Configuration Handling ---

def load_config():
    """Loads configuration from config.json or environment variables."""
    config = {
        'LIDARR_URL': '',
        'API_KEY': '',
        'ROOT_FOLDER_PATH': '/music' # Default, can be overridden
    }
    # Load from file first
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config.update(json.load(f))
        except json.JSONDecodeError:
            print(f"Warning: Could not decode {CONFIG_FILE}. Using defaults/environment variables.")
        except Exception as e:
             print(f"Warning: Error reading {CONFIG_FILE}: {e}. Using defaults/environment variables.")


    # Override with environment variables if they exist
    config['LIDARR_URL'] = os.environ.get('LIDARR_URL', config.get('LIDARR_URL', ''))
    config['API_KEY'] = os.environ.get('LIDARR_API_KEY', config.get('API_KEY', ''))
    # Use LIDARR_API_KEY for consistency with common *arr app practices
    config['ROOT_FOLDER_PATH'] = os.environ.get('LIDARR_ROOT_FOLDER', config.get('ROOT_FOLDER_PATH', '/music'))

    # Basic validation (remove trailing slashes)
    if config['LIDARR_URL']:
        config['LIDARR_URL'] = config['LIDARR_URL'].rstrip('/')

    return config

def save_config(config_data):
    """Saves configuration to config.json."""
    try:
        # Only save fields relevant to the settings form
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
    """Searches for an artist and adds them to Lidarr."""
    if not config.get('LIDARR_URL') or not config.get('API_KEY'):
        return {"status": "error", "message": "Lidarr URL or API Key not configured."}
    if not config.get('ROOT_FOLDER_PATH'):
         return {"status": "error", "message": "Root Folder Path not configured."}

    print(f"🔍 Searching for artist: {artist_name}")
    search_term_encoded = requests.utils.quote(artist_name)
    lookup_url = f"{config['LIDARR_URL']}/api/v1/artist/lookup?term={search_term_encoded}"
    headers = {"X-Api-Key": config['API_KEY']}

    try:
        response = requests.get(lookup_url, headers=headers, timeout=30) # Added timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        lookup_results = response.json()

        if not lookup_results:
            print(f"❌ Artist not found via API: {artist_name}")
            return {"status": "not_found", "artist": artist_name}

        # Usually, the first result is the most relevant
        artist_to_add = lookup_results[0]
        artist_id = artist_to_add.get("foreignArtistId")
        actual_artist_name = artist_to_add.get("artistName")

        if not artist_id or not actual_artist_name:
             print(f"❌ API response missing data for: {artist_name}")
             return {"status": "error", "message": f"API response missing data for: {artist_name}"}

        # Check if artist already exists (avoids errors)
        existing_artist_url = f"{config['LIDARR_URL']}/api/v1/artist"
        existing_response = requests.get(existing_artist_url, headers=headers, timeout=15)
        existing_response.raise_for_status()
        for existing_artist in existing_response.json():
            # Lidarr API sometimes uses 'id' and sometimes 'foreignArtistId'. Checking the name is safer.
            # A more robust check might involve the foreignArtistId if available consistently.
            if existing_artist.get('artistName', '').lower() == actual_artist_name.lower():
                print(f"ℹ️ Artist already exists in Lidarr: {actual_artist_name}")
                return {"status": "already_exists", "artist": actual_artist_name}


        # Prepare data to add the artist
        # Ensure path is constructed correctly for Lidarr
        # Lidarr typically expects a *folder name* within the root path
        artist_folder_name = actual_artist_name.replace(':', '_').replace('/', '_').replace('\\', '_') # Basic sanitization

        body = {
            "foreignArtistId": artist_id,
            "metadataProfileId": 1,  # Default, consider making configurable if needed
            "qualityProfileId": 1,   # Default, consider making configurable if needed
            "monitored": True,
            "artistName": actual_artist_name, # Use name from lookup result
             # Combine root path with the sanitized artist name
            "rootFolderPath": config['ROOT_FOLDER_PATH'], # Send the root path configured
            "path": os.path.join(config['ROOT_FOLDER_PATH'], artist_folder_name), # Full path Lidarr expects
            "addOptions": {
                "searchForMissingAlbums": True
            }
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
            # Attempt to get more specific error from Lidarr response
            error_details = e.response.json()
            if isinstance(error_details, list) and error_details:
                 error_message = error_details[0].get('errorMessage', str(e))
            elif isinstance(error_details, dict):
                 error_message = error_details.get('message', str(e))
        except:
             pass # Keep original error if parsing fails
        return {"status": "error", "artist": artist_name, "message": f"Lidarr API Error: {error_message}"}
    except Exception as e: # Catch other potential errors
        print(f"❌ Unexpected error processing {artist_name}. Error: {e}")
        return {"status": "error", "artist": artist_name, "message": f"Unexpected error: {str(e)}"}


# --- Flask Routes ---

@app.route('/', methods=['GET'])
def index():
    """Displays the main page."""
    config = load_config()
    if not config.get('LIDARR_URL') or not config.get('API_KEY'):
        flash('Lidarr URL or API Key is not configured. Please configure them in Settings.', 'warning')
    return render_template('index.html', config=config)

@app.route('/add', methods=['POST'])
def add_artists_route():
    """Handles adding artists from text input or file upload."""
    config = load_config()
    results = []
    artists_input = ""

    if 'artist_list_paste' in request.form and request.form['artist_list_paste'].strip():
        artists_input = request.form['artist_list_paste']
    elif 'artist_list_file' in request.files:
        file = request.files['artist_list_file']
        if file.filename != '':
            try:
                # Read file content securely
                artists_input = file.read().decode('utf-8')
            except Exception as e:
                flash(f"Error reading uploaded file: {e}", 'danger')
                return redirect(url_for('index'))
        elif not artists_input: # No paste data either
             flash('Please paste a list of artists or upload a file.', 'warning')
             return redirect(url_for('index'))
    else:
         flash('No artist data provided.', 'warning')
         return redirect(url_for('index'))


    artists = [artist.strip() for artist in artists_input.splitlines() if artist.strip()]

    if not artists:
        flash('No valid artist names found in the input.', 'warning')
        return redirect(url_for('index'))

    print(f"Processing {len(artists)} artists...")
    processed_count = 0
    for artist in artists:
        result = search_and_add_artist(artist, config)
        results.append(result)
        processed_count += 1
        print(f"Processed {processed_count}/{len(artists)}")
        time.sleep(0.5)  # Be nice to the Lidarr API

    # Provide feedback to the user
    # You could render a results page or flash messages,
    # here we just flash a summary and redirect back.
    summary = {
        "added": sum(1 for r in results if r['status'] == 'added'),
        "already_exists": sum(1 for r in results if r['status'] == 'already_exists'),
        "not_found": sum(1 for r in results if r['status'] == 'not_found'),
        "error": sum(1 for r in results if r['status'] == 'error'),
        "total": len(artists)
    }
    flash(f"Processing complete: Added: {summary['added']}, Already Existed: {summary['already_exists']}, Not Found: {summary['not_found']}, Errors: {summary['error']} (Total: {summary['total']})", 'info')

    # Log detailed errors if any occurred
    error_details = [f"{r['artist']}: {r.get('message', 'Unknown error')}" for r in results if r['status'] == 'error']
    if error_details:
         print("--- Detailed Errors ---")
         for error in error_details:
             print(error)
         flash("Some artists could not be added. Check the container logs for details.", 'danger')


    return redirect(url_for('index'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Displays and handles saving settings."""
    config = load_config()

    if request.method == 'POST':
        new_config = config.copy() # Start with existing config
        new_config['LIDARR_URL'] = request.form.get('lidarr_url', '').strip().rstrip('/')
        new_config['API_KEY'] = request.form.get('api_key', '').strip()
        new_config['ROOT_FOLDER_PATH'] = request.form.get('root_folder_path', '').strip()

        if not new_config['LIDARR_URL'] or not new_config['API_KEY'] or not new_config['ROOT_FOLDER_PATH']:
             flash('Lidarr URL, API Key, and Root Folder Path cannot be empty.', 'danger')
             # Return the settings page with entered values, but don't save
             return render_template('settings.html', config=new_config)


        if save_config(new_config):
            flash('Settings saved successfully!', 'success')
            # Update environment variables for the current process (optional)
            # os.environ['LIDARR_URL'] = new_config['LIDARR_URL']
            # os.environ['LIDARR_API_KEY'] = new_config['API_KEY']
            # os.environ['LIDARR_ROOT_FOLDER'] = new_config['ROOT_FOLDER_PATH']
        else:
            flash('Error saving settings. Check container logs.', 'danger')
        return redirect(url_for('settings')) # Redirect to GET after POST

    # For GET request, just display the settings page with current config
    return render_template('settings.html', config=config)

# --- Main Execution ---

if __name__ == "__main__":
    # Make sure the config file can be written inside the container
    # Adjust permissions if needed during Docker build or entrypoint
    app.run(host='0.0.0.0', port=5000) # Listen on all interfaces, required for Docker