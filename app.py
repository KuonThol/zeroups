from flask import Flask, render_template, request, jsonify, send_file
import os
import subprocess
import zipfile
import tempfile

app = Flask(__name__)

# កំណត់ទំហំអតិបរមានៃការ Upload ដល់ 10GB ធំទូលាយ
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024

TEMP_DIR = tempfile.mkdtemp()
UPLOAD_FOLDER = os.path.join(TEMP_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(TEMP_DIR, 'outputs')

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
    output_format = data.get('format', 'mp4').lower()
    
    # ការកំណត់ការសារ៉េ Anti-Copyright ពីសំណាក់អ្នកប្រើប្រាស់
    enable_anti_copyright = data.get('anti_copyright', True)
    mirror_video = data.get('mirror', True)          # បញ្ច្រាសឆ្វេងស្តាំ
    brightness_val = data.get('brightness', 0.03)    # សារ៉េពន្លឺ (ឧទាហរណ៍: -0.1 ដល់ 0.1)
    audio_tempo = data.get('tempo', 1.03)            # សារ៉េល្បឿនសំឡេង (ឧទាហរណ៍: 0.95 ដល់ 1.05)
    
    video_path = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(video_path):
        return jsonify({'success': False, 'error': 'File not found'})

    ext = output_format if output_format in ['mp4', 'webm', 'mkv'] else 'mp4'

    # បង្កើត Filter Strings តាមការសារ៉េ
    video_filters = []
    audio_filters = []

    if enable_anti_copyright:
        if mirror_video:
            video_filters.append("hflip")
        if brightness_val != 0:
            video_filters.append(f"eq=brightness={brightness_val}:saturation=1.05")
        if audio_tempo != 1.0:
            audio_filters.append(f"atempo={audio_tempo}")

    vf_str = ",".join(video_filters) if video_filters else None
    af_str = ",".join(audio_filters) if audio_filters else None

    if mode == 'equal':
        try:
            parts = int(data.get('parts', 3))
            if parts < 1:
                parts = 1
        except:
            parts = 3

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
        output_pattern = os.path.join(OUTPUT_FOLDER, f'part_%03d.{ext}')
        
        command = ['ffmpeg', '-y', '-i', video_path]
        if vf_str:
            command.extend(['-vf', vf_str])
        if af_str:
            command.extend(['-af', af_str])
        
        # ប្រសិនបើគ្មានដាក់ Filter អ្វីសោះ អាចប្រើ -c copy បានដើម្បីឱ្យលឿន
        if not vf_str and not af_str:
            command.extend(['-c', 'copy'])
            
        command.extend([
            '-segment_time', str(segment_duration), 
            '-f', 'segment', '-reset_timestamps', '1', output_pattern
        ])
        subprocess.run(command)

    elif mode == 'duration':
        try:
            seg_duration = str(float(data.get('duration', '60')))
        except:
            seg_duration = '60'
            
        output_pattern = os.path.join(OUTPUT_FOLDER, f'part_%03d.{ext}')
        
        command = ['ffmpeg', '-y', '-i', video_path]
        if vf_str: command.extend(['-vf', vf_str])
        if af_str: command.extend(['-af', af_str])
        if not vf_str and not af_str: command.extend(['-c', 'copy'])
        
        command.extend([
            '-segment_time', seg_duration, 
            '-f', 'segment', '-reset_timestamps', '1', output_pattern
        ])
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
                out_file = os.path.join(OUTPUT_FOLDER, f'custom_part_{i+1:03d}.{ext}')
                cmd = ['ffmpeg', '-y', '-ss', str(start)]
                if p is not None:
                    cmd.extend(['-to', str(p)])
                cmd.extend(['-i', video_path])
                
                if vf_str: cmd.extend(['-vf', vf_str])
                if af_str: cmd.extend(['-af', af_str])
                if not vf_str and not af_str: cmd.extend(['-c', 'copy'])
                
                cmd.append(out_file)
                subprocess.run(cmd)
                if p is not None:
                    start = p

    files_list = sorted([f for f in os.listdir(OUTPUT_FOLDER) if f.startswith('part_') or f.startswith('custom_')])
    
    return jsonify({'success': True, 'segments': files_list})

@app.route('/crop', methods=['POST'])
def crop_video():
    data = request.get_json()
    filename = data.get('filename')
    aspect_ratio = data.get('aspect_ratio', '16:9')
    
    video_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(video_path):
        return jsonify({'success': False, 'error': 'File not found'})
        
    output_filename = f'cropped_{filename}'
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    if aspect_ratio == '9:16':
        crop_filter = 'crop=ih*9/16:ih'
    elif aspect_ratio == '1:1':
        crop_filter = 'crop=min(iw\,ih):min(iw\,ih)'
    elif aspect_ratio == '4:3':
        crop_filter = 'crop=ih*4/3:ih'
    else:
        crop_filter = 'crop=iw:ih'
    
    full_filter = f"{crop_filter},hflip"
    command = ['ffmpeg', '-y', '-i', video_path, '-vf', full_filter, '-af', 'atempo=1.03', output_path]
    subprocess.run(command)
    
    return jsonify({'success': True, 'filename': output_filename})

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
    file_path = os.path.join(OUTPUT_FOLDER, filename)
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
