```python
import os
import uuid
import subprocess
import time
from flask import Flask, request, jsonify, send_from_directory, render_template_string
import yt_dlp
import imageio_ffmpeg

app = Flask(__name__)

IS_VERCEL = os.environ.get("VERCEL") == "1"
CLIPS_DIR = "/tmp/clips" if IS_VERCEL else os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

def cleanup_old_files():
    """Membersihkan file lama di folder tmp agar memori tidak pernah penuh"""
    try:
        now = time.time()
        for f in os.listdir(CLIPS_DIR):
            fp = os.path.join(CLIPS_DIR, f)
            if os.path.isfile(fp):
                # Hapus file jika usianya lebih dari 10 menit
                if now - os.path.getmtime(fp) > 600:
                    os.remove(fp)
    except Exception:
        pass

HTML_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ClipForge AI - Auto YouTube Clipper</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col items-center p-4 md:p-8">
    <div class="w-full max-w-3xl">
        <header class="text-center my-6">
            <h1 class="text-4xl font-extrabold text-cyan-400 tracking-tight">ClipForge AI</h1>
            <p class="text-slate-400 mt-2">Potong video YouTube atau file lokal otomatis jadi klip vertikal siap upload (Hemat Memori)</p>
        </header>

        <div class="bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
            <div class="flex gap-2 mb-5 bg-slate-950 p-1 rounded-xl border border-slate-800">
                <button onclick="switchTab('youtube')" id="tab-yt" class="flex-1 py-2 rounded-lg text-sm font-bold bg-cyan-500 text-slate-950 transition-all">Link YouTube</button>
                <button onclick="switchTab('upload')" id="tab-up" class="flex-1 py-2 rounded-lg text-sm font-bold text-slate-400 hover:text-white transition-all">Upload Video (Anti-Blokir)</button>
            </div>

            <div id="input-yt-group">
                <label class="block text-sm font-medium text-slate-300 mb-2">Link Video YouTube</label>
                <input type="url" id="yt-link" placeholder="https://www.youtube.com/watch?v=..." 
                    class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-slate-100 focus:outline-none focus:border-cyan-500 mb-4">
            </div>

            <div id="input-up-group" class="hidden">
                <label class="block text-sm font-medium text-slate-300 mb-2">Pilih File Video (MP4 / MOV)</label>
                <input type="file" id="video-file" accept="video/*" 
                    class="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-300 mb-4 file:mr-4 file:py-1.5 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-cyan-500 file:text-slate-950">
            </div>

            <div class="grid grid-cols-2 gap-4 mb-4">
                <div>
                    <label class="block text-xs text-slate-400 mb-1">Durasi Per Klip (Detik)</label>
                    <select id="clip-duration" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-slate-200">
                        <option value="15">15 Detik</option>
                        <option value="30" selected>30 Detik</option>
                        <option value="45">45 Detik</option>
                        <option value="60">60 Detik</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs text-slate-400 mb-1">Jumlah Klip</label>
                    <select id="clip-count" class="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-slate-200">
                        <option value="2" selected>2 Klip</option>
                        <option value="3">3 Klip</option>
                        <option value="5">5 Klip</option>
                    </select>
                </div>
            </div>

            <div class="flex items-center gap-4 mb-5 text-sm text-slate-300">
                <label class="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" id="crop-vertical" checked class="accent-cyan-500 w-4 h-4"> Crop 9:16 (TikTok / Shorts)
                </label>
            </div>

            <button onclick="processVideo()" id="submit-btn" 
                class="w-full bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold py-3.5 rounded-xl transition-all shadow-lg">
                Mulai Nge-Klip Sekarang
            </button>
        </div>

        <div id="status-box" class="hidden text-center my-8 p-6 bg-slate-900/50 border border-slate-800 rounded-2xl">
            <div class="inline-block animate-spin rounded-full h-10 w-10 border-4 border-cyan-500 border-t-transparent"></div>
            <p id="status-text" class="text-cyan-400 mt-4 font-medium animate-pulse">Memproses & merender video...</p>
            <p class="text-xs text-slate-500 mt-1">File langsung dibersihkan otomatis setelah selesai agar memori aman</p>
        </div>

        <div id="error-box" class="hidden my-6 p-4 bg-red-950/60 border border-red-800 text-red-300 rounded-xl text-sm"></div>

        <div id="results-box" class="hidden mt-8">
            <h2 class="text-xl font-bold text-slate-200 mb-4">Hasil Potongan Klip</h2>
            <div id="clips-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
        </div>
    </div>

    <script>
        let currentMode = 'youtube';

        function switchTab(mode) {
            currentMode = mode;
            const tabYt = document.getElementById('tab-yt');
            const tabUp = document.getElementById('tab-up');
            const groupYt = document.getElementById('input-yt-group');
            const groupUp = document.getElementById('input-up-group');

            if (mode === 'youtube') {
                tabYt.className = 'flex-1 py-2 rounded-lg text-sm font-bold bg-cyan-500 text-slate-950 transition-all';
                tabUp.className = 'flex-1 py-2 rounded-lg text-sm font-bold text-slate-400 hover:text-white transition-all';
                groupYt.classList.remove('hidden');
                groupUp.classList.add('hidden');
            } else {
                tabUp.className = 'flex-1 py-2 rounded-lg text-sm font-bold bg-cyan-500 text-slate-950 transition-all';
                tabYt.className = 'flex-1 py-2 rounded-lg text-sm font-bold text-slate-400 hover:text-white transition-all';
                groupUp.classList.remove('hidden');
                groupYt.classList.add('hidden');
            }
        }

        async function processVideo() {
            const duration = document.getElementById('clip-duration').value;
            const count = document.getElementById('clip-count').value;
            const vertical = document.getElementById('crop-vertical').checked;

            const btn = document.getElementById('submit-btn');
            const statusBox = document.getElementById('status-box');
            const errorBox = document.getElementById('error-box');
            const resultsBox = document.getElementById('results-box');
            const clipsGrid = document.getElementById('clips-grid');

            const formData = new FormData();
            formData.append('mode', currentMode);
            formData.append('duration', duration);
            formData.append('count', count);
            formData.append('vertical', vertical);

            if (currentMode === 'youtube') {
                const url = document.getElementById('yt-link').value.trim();
                if (!url) {
                    alert('Masukkan link YouTube dulu, Bro!');
                    return;
                }
                formData.append('url', url);
            } else {
                const fileInput = document.getElementById('video-file');
                if (!fileInput.files.length) {
                    alert('Pilih file video dulu, Bro!');
                    return;
                }
                formData.append('file', fileInput.files[0]);
            }

            btn.disabled = true;
            btn.classList.add('opacity-50');
            statusBox.classList.remove('hidden');
            errorBox.classList.add('hidden');
            resultsBox.classList.add('hidden');
            clipsGrid.innerHTML = '';

            try {
                const response = await fetch('/api/clip', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (!response.ok || data.error) {
                    throw new Error(data.error || 'Gagal memproses video.');
                }

                data.clips.forEach((clip, index) => {
                    const card = document.createElement('div');
                    card.className = 'bg-slate-900 border border-slate-800 p-4 rounded-xl flex flex-col justify-between';
                    card.innerHTML = `
                        <div>
                            <video src="${clip.url}" controls class="w-full rounded-lg bg-black mb-3 max-h-80 object-contain"></video>
                            <h3 class="font-semibold text-slate-200">Klip #${index + 1} (${clip.start}s - ${clip.end}s)</h3>
                            <p class="text-xs text-slate-400 mt-1">${data.title}</p>
                        </div>
                        <a href="${clip.url}" download="${clip.filename}" 
                            class="mt-4 block text-center bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-sm font-bold py-2.5 rounded-lg transition-all">
                            Download MP4
                        </a>
                    `;
                    clipsGrid.appendChild(card);
                });

                resultsBox.classList.remove('hidden');
            } catch (err) {
                errorBox.innerHTML = '<strong>Error:</strong> ' + err.message + '<br><span class="text-xs text-slate-400 mt-1 block">Tips: Jika YouTube memblokir IP server Vercel, gunakan tab <b>Upload Video (Anti-Blokir)</b> di atas!</span>';
                errorBox.classList.remove('hidden');
            } finally {
                btn.disabled = false;
                btn.classList.remove('opacity-50');
                statusBox.classList.add('hidden');
            }
        }
    </script>
</body>
</html>"""

def get_video_duration(ffmpeg_exe, filepath):
    cmd = [ffmpeg_exe, "-i", filepath]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            time_str = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = time_str.split(":")
            return int(float(h) * 3600 + float(m) * 60 + float(s))
    return 60

@app.route('/')
def index():
    cleanup_old_files()
    return render_template_string(HTML_PAGE)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/clips/<path:filename>')
def serve_clip(filename):
    return send_from_directory(CLIPS_DIR, filename)

@app.route('/api/clip', methods=['POST'])
def create_clips():
    cleanup_old_files()
    mode = request.form.get('mode', 'youtube')
    clip_duration = int(request.form.get('duration', 30))
    clip_count = int(request.form.get('count', 2))
    vertical = request.form.get('vertical', 'true').lower() == 'true'

    job_id = str(uuid.uuid4())[:8]
    raw_video_path = os.path.join(CLIPS_DIR, f"{job_id}_raw.mp4")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    try:
        if mode == 'upload':
            if 'file' not in request.files:
                return jsonify({'error': 'File video tidak ditemukan.'}), 400
            file = request.files['file']
            title = file.filename or "Uploaded Video"
            file.save(raw_video_path)
            total_duration = get_video_duration(ffmpeg_exe, raw_video_path)
        else:
            url = request.form.get('url')
            if not url:
                return jsonify({'error': 'URL YouTube tidak boleh kosong'}), 400

            ydl_opts = {
                'format': 'best[height<=480][ext=mp4]/best[ext=mp4]/best',  # Pilih resolusi kecil (480p) agar hemat memori & cepat
                'outtmpl': raw_video_path,
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'tv_embedded'],
                        'player_skip': ['webpage', 'configs']
                    }
                }
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'YouTube Video')
                total_duration = info.get('duration', 60)

        if not os.path.exists(raw_video_path):
            return jsonify({'error': 'Gagal menyiapkan file video.'}), 500

        clips_output = []
        start_offset = 10 if total_duration > (clip_duration * clip_count + 15) else 0
        available_span = max(total_duration - start_offset - clip_duration, 1)
        step = max(available_span // max(clip_count, 1), clip_duration)

        for i in range(clip_count):
            start_time = start_offset + (i * step)
            if start_time + 5 >= total_duration:
                break
            end_time = min(start_time + clip_duration, total_duration)
            actual_dur = end_time - start_time

            out_filename = f"clip_{job_id}_{i+1}.mp4"
            out_filepath = os.path.join(CLIPS_DIR, out_filename)

            cmd = [
                ffmpeg_exe, "-y",
                "-ss", str(start_time),
                "-i", raw_video_path,
                "-t", str(actual_dur),
            ]

            if vertical:
                cmd.extend(["-vf", "scale=480:-2,crop=ih*(9/16):ih"])

            cmd.extend([
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-c:a", "aac", "-b:a", "96k",
                out_filepath
            ])

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            if os.path.exists(out_filepath):
                clips_output.append({
                    'filename': out_filename,
                    'url': f"/clips/{out_filename}",
                    'start': int(start_time),
                    'end': int(end_time)
                })

        # HAPUS FILE MENTAH UTAMA SEGERA AGAR MEMORI SERVER AMAN & TIDAK PENUH
        if os.path.exists(raw_video_path):
            os.remove(raw_video_path)

        if not clips_output:
            return jsonify({'error': 'Video terlalu pendek untuk dipotong.'}), 400

        return jsonify({
            'title': title,
            'clips': clips_output
        })

    except Exception as e:
        if os.path.exists(raw_video_path):
            os.remove(raw_video_path)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
```
