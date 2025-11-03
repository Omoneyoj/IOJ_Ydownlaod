import subprocess
import os
import shutil
import sys
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename

# Initialize Flask application
app = Flask(__name__)

# --- NEW: Route to serve the HTML file ---
@app.route('/')
def serve_index():
    """Serves the index.html file when the user visits the root URL."""
    # To use render_template, the index.html file MUST be placed inside a 
    # folder named 'templates' in the same directory as app.py.
    return render_template('index.html')
# --- END NEW ---

@app.route('/api/download', methods=['POST'])
def download_video():
    """
    Handles POST requests to download a YouTube video or playlist.
    It executes the yt-dlp command and returns the resulting file or zip.
    """
    data = request.json
    url = data.get('url')
    download_type = data.get('type', 'single')
    # NEW: Get the selected format type (defaults to 'video')
    format_type = data.get('format', 'video') 

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # 1. Define temporary directories for safe operation
    temp_dir = 'temp_downloads'
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    # 2. Define yt-dlp format based on user choice
    if format_type == 'audio':
        # Best audio format, merged into m4a (requires FFmpeg if merging streams, but often downloads as one stream)
        yt_dlp_format = 'bestaudio[ext=m4a]/bestaudio'
        file_ext = '.m4a'
        mime_type_file = 'audio/m4a'
    else: # Default to video
        # Video/Audio combo that doesn't rely on FFmpeg for merging (up to 720p)
        yt_dlp_format = 'best[ext=mp4]/best'
        file_ext = '.mp4'
        mime_type_file = 'video/mp4'

    try:
        # 3. Define the base yt-dlp command and options
        base_command = [
            sys.executable,
            '-m', 'yt_dlp',
            '--format', yt_dlp_format, # Use determined format
            '--ignore-errors',
            '--output', os.path.join(temp_dir, f'%(title)s{file_ext}'), # Use determined extension
        ]
        
        # 4. Handle playlist vs. single video logic
        if download_type == 'playlist':
            # For playlists, we modify the output template to include index and create a subfolder
            base_command[-1] = os.path.join(temp_dir, '%(playlist)s', f'%(playlist_index)s - %(title)s{file_ext}')
            base_command.append('--yes-playlist')
            
            # Execute command to download playlist contents
            result = subprocess.run(base_command + [url], check=True, capture_output=True, text=True)
            print("yt-dlp output:", result.stdout)

            # 5. Zip the contents of the playlist folder
            playlist_folders = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
            if not playlist_folders:
                if len(os.listdir(temp_dir)) == 0:
                     return jsonify({"error": "Playlist download succeeded but no files were found (possibly restricted content)."}), 500
                playlist_folder_name = "Playlist_Content"
                zip_path = os.path.join(temp_dir, playlist_folder_name)
                shutil.make_archive(zip_path, 'zip', temp_dir)
            else:
                playlist_folder_name = playlist_folders[0]
                zip_path = os.path.join(temp_dir, secure_filename(playlist_folder_name)) # Base name for zip
                shutil.make_archive(zip_path, 'zip', os.path.join(temp_dir, playlist_folder_name))
            
            final_file_path = f"{zip_path}.zip"
            download_filename = f"{playlist_folder_name}.zip"
            mime_type = 'application/zip'

        else: # Single video download
            # Execute command to download single video
            result = subprocess.run(base_command + [url], check=True, capture_output=True, text=True)
            print("yt-dlp output:", result.stdout)
            
            # Find the downloaded file using the expected extension
            downloaded_files = [f for f in os.listdir(temp_dir) if f.endswith(file_ext)]
            if not downloaded_files:
                 return jsonify({"error": "Video download succeeded but file not found (possibly restricted content or download failure)."}), 500

            final_file_path = os.path.join(temp_dir, downloaded_files[0])
            download_filename = downloaded_files[0]
            mime_type = mime_type_file # Use determined mime type

        # 6. Send the file back to the browser
        return send_file(
            final_file_path, 
            as_attachment=True, 
            download_name=download_filename, 
            mimetype=mime_type
        )

    except subprocess.CalledProcessError as e:
        error_output = e.stderr
        print(f"yt-dlp Error: {error_output}")
        return jsonify({"error": "Download failed. Check the server console for yt-dlp errors."}), 500
    
    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({"error": "Internal server error."}), 500
    
    finally:
        # 7. Cleanup the temporary directory immediately
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    # Flask will run on port 5000 by default
    app.run(debug=True)
