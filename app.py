from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
from PyPDF2 import PdfMerger
import tempfile
from datetime import datetime

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'Aucun fichier trouvé'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            uploaded_files.append({'name': filename, 'path': unique_filename})

    return jsonify({'files': uploaded_files})


@app.route('/merge', methods=['POST'])
def merge_pdfs():
    data = request.json
    file_paths = data.get('files', [])
    output_name = data.get('outputName', 'merged')

    # Nettoyer le nom de fichier
    output_name = secure_filename(output_name)
    if not output_name:
        output_name = 'merged'

    if not file_paths:
        return jsonify({'error': 'Aucun fichier à fusionner'}), 400

    try:
        merger = PdfMerger()

        for file_path in file_paths:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)
            if os.path.exists(full_path):
                merger.append(full_path)

        # Nom de fichier interne avec timestamp pour éviter les conflits
        internal_filename = f"{output_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], internal_filename)
        merger.write(output_path)
        merger.close()

        # Nom de fichier pour le téléchargement (sans timestamp)
        download_name = f"{output_name}.pdf"

        return jsonify({
            'success': True,
            'filename': internal_filename,
            'downloadName': download_name
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<filename>')
def download_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    return jsonify({'error': 'Fichier non trouvé'}), 404


""" @app.route('/clear', methods=['POST'])
def clear_files():
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500 """


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)