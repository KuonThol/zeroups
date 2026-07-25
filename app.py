from flask import Flask, render_template, request, jsonify, send_file
import os
import subprocess
import zipfile

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'No video file provided'})
    
    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'})

    if video_file:
        video_path = os.path.join(UPLOAD_FOLDER, video_file.filename)
        video_file.save(video_path)
        return jsonify({'success': True, 'filename': video_file.filename})

@app.route('/split', methods=['POST'])
def split_video():
    data = request.get_json()
    filename = data.get('filename')
    mode = data.get('mode', 'equal')
    
    video_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(video_path):
        return jsonify({'success': False, 'error': 'File not found'})

    # លុបឯកសារចាស់ចោលជាមុនសិន
    for f in os.listdir(OUTPUT_FOLDER):
        if f.startswith('part_') or f.startswith('custom_'):
            try:
                os.remove(os.path.join(OUTPUT_FOLDER, f))
            except:
                pass

    if mode == 'equal':
        parts = int(data.get('parts', 4))
        probe_command = [
            'ffprobe', '-v', 'error', '-show_entries',
            'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        try:
            result = subprocess.run(probe_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            duration = float(result.stdout.strip())
        except Exception:
            duration = 60.0
        segment_duration = duration / parts
        output_pattern = os.path.join(OUTPUT_FOLDER, 'part_%03d.mp4')
        
        command = [
            'ffmpeg', '-y', '-i', video_path, '-c', 'copy', 
            '-map', '0', '-segment_time', str(segment_duration), 
            '-f', 'segment', '-reset_timestamps', '1', output_pattern
        ]
        subprocess.run(command)

    elif mode == 'duration':
        seg_duration = str(data.get('duration', '60'))
        output_pattern = os.path.join(OUTPUT_FOLDER, 'part_%03d.mp4')
        
        command = [
            'ffmpeg', '-y', '-i', video_path, '-c', 'copy', 
            '-map', '0', '-segment_time', seg_duration, 
            '-f', 'segment', '-reset_timestamps', '1', output_pattern
        ]
        subprocess.run(command)

    elif mode == 'custom':
        points_str = data.get('custom_points', '')
        try:
            points = [float(p.strip()) for p in points_str.split(',') if p.strip()]
            points = sorted(list(set(points)))
        except:
            points = []

        if points:
            start = 0.0
            points.append(None)
            for i, p in enumerate(points):
                out_file = os.path.join(OUTPUT_FOLDER, f'custom_part_{i+1:03d}.mp4')
                if p is not None:
                    cmd = ['ffmpeg', '-y', '-ss', str(start), '-to', str(p), '-i', video_path, '-c', 'copy', out_file]
                    start = p
                else:
                    cmd = ['ffmpeg', '-y', '-ss', str(start), '-i', video_path, '-c', 'copy', out_file]
                subprocess.run(cmd)

    files_list = sorted([f for f in os.listdir(OUTPUT_FOLDER) if f.startswith('part_') or f.startswith('custom_')])
    
    return jsonify({'success': True, 'segments': files_list})

@app.route('/download-zip/<filename>')
def download_single(filename):
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    return send_file(file_path, as_attachment=True)

@app.route('/download-all-zip', methods=['POST'])
def download_all_zip():
    data = request.get_json()
    segments = data.get('segments', [])
    
    zip_filename = 'all_split_videos.zip'
    zip_path = os.path.join(OUTPUT_FOLDER, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for seg in segments:
            file_path = os.path.join(OUTPUT_FOLDER, seg)
            if os.path.exists(file_path):
                zipf.write(file_path, arcname=seg)
                
    return jsonify({'success': True, 'zip_filename': zip_filename})

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
