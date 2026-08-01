from flask import Flask, render_template, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download-youtube', methods=['POST'])
def download_youtube():
    data = request.get_json()
    youtube_url = data.get('url')
    
    if not youtube_url:
        return jsonify({'success': False, 'error': 'No YouTube URL provided'})
    
    ydl_opts = {
        'format': 'best',
        'cookiefile': 'cookies.txt',
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(youtube_url, download=False)
            
            direct_url = info_dict.get('url')
            video_title = info_dict.get('title', 'video')
            
            if not direct_url:
                formats = info_dict.get('formats', [])
                for f in formats:
                    if f.get('url') and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        direct_url = f.get('url')
                        break
            
            if not direct_url:
                return jsonify({'success': False, 'error': 'Could not extract direct stream link.'})

        return jsonify({'success': True, 'download_url': direct_url, 'title': video_title})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
