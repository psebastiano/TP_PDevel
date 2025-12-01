from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import tempfile
from datetime import datetime

app = Flask(__name__)
# Utilisation d'un dossier temporaire système
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# --- ROUTES D'INTERFACE (HTML) ---

@app.route('/')
def home():
    """Page d'accueil avec le choix des outils"""
    return render_template('home.html')


@app.route('/tool/watermark')
def watermark_interface():
    return render_template('watermark.html')


@app.route('/api/watermark', methods=['POST'])
def watermark_action():
    # 1. Vérifier la présence des deux fichiers
    if 'file' not in request.files or 'watermark_file' not in request.files:
        return jsonify({'error': 'Veuillez fournir le document ET le fichier filigrane'}), 400

    source_file = request.files['file']
    watermark_file = request.files['watermark_file']
    output_name_user = request.form.get('outputName', '').strip()

    if source_file and allowed_file(source_file.filename) and watermark_file and allowed_file(watermark_file.filename):
        try:
            # 2. Sauvegarde temporaire
            source_filename = secure_filename(source_file.filename)
            watermark_filename = secure_filename(watermark_file.filename)

            source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"src_{source_filename}")
            watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], f"wm_{watermark_filename}")

            source_file.save(source_path)
            watermark_file.save(watermark_path)

            # 3. Lecture des fichiers
            source_reader = PdfReader(source_path)
            watermark_reader = PdfReader(watermark_path)

            # On prend la première page du PDF filigrane comme modèle
            watermark_page = watermark_reader.pages[0]

            writer = PdfWriter()

            # 4. Application du filigrane sur chaque page
            for page in source_reader.pages:
                # merge_page superpose la page donnée (watermark) sur la page actuelle
                page.merge_page(watermark_page)
                writer.add_page(page)

            # 5. Gestion du nom de sortie
            if not output_name_user:
                output_name_user = f"watermarked_{source_filename}"
            else:
                if not output_name_user.lower().endswith('.pdf'):
                    output_name_user += '.pdf'
                output_name_user = secure_filename(output_name_user)

            output_filename = f"{datetime.now().strftime('%H%M%S')}_{output_name_user}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            with open(output_path, "wb") as f:
                writer.write(f)

            return jsonify({
                'success': True,
                'filename': output_filename,
                'downloadName': output_name_user
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Fichiers invalides'}), 400

@app.route('/tool/merge')
def merge_interface():
    """Interface de fusion"""
    return render_template('merge.html')


@app.route('/tool/split')
def split_interface():
    """Interface de division"""
    return render_template('split.html')


# --- ROUTES API  ---

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'Aucun fichier trouvé'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Timestamp pour éviter les écrasements
            unique_filename = f"{datetime.now().strftime('%H%M%S')}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            # On renvoie le path sécurisé pour le traitement suivant
            uploaded_files.append({
                'name': filename,
                'path': unique_filename
            })

    return jsonify({'files': uploaded_files})


@app.route('/api/merge', methods=['POST'])
def merge_action():
    data = request.json
    file_paths = data.get('files', [])  # L'ordre ici sera celui défini par le front
    output_name = secure_filename(data.get('outputName', 'merged')) or 'merged'

    if len(file_paths) < 2:
        return jsonify({'error': 'Il faut au moins 2 fichiers'}), 400

    try:
        merger = PdfMerger()
        for file_path in file_paths:
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)
            merger.append(full_path)

        output_filename = f"{output_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        merger.write(output_path)
        merger.close()

        return jsonify({
            'success': True,
            'filename': output_filename,
            'downloadName': f"{output_name}.pdf"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ... Imports et config inchangés ...

@app.route('/api/split', methods=['POST'])
def split_action():
    data = request.json
    filename = data.get('filename')
    split_page = int(data.get('splitPage', 1))
    # Nouveau : Récupérer le nom choisi par l'utilisateur
    output_prefix = data.get('outputPrefix', 'split')
    output_prefix = secure_filename(output_prefix) or 'split'

    full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        reader = PdfReader(full_path)
        total_pages = len(reader.pages)

        if split_page < 1 or split_page >= total_pages:
            return jsonify({'error': 'Numéro de page invalide'}), 400

        writer1 = PdfWriter()
        writer2 = PdfWriter()

        for i in range(split_page):
            writer1.add_page(reader.pages[i])

        for i in range(split_page, total_pages):
            writer2.add_page(reader.pages[i])

        timestamp = datetime.now().strftime('%H%M%S')

        # Noms de fichiers internes (pour le stockage unique)
        internal_name1 = f"{output_prefix}_part1_{timestamp}.pdf"
        internal_name2 = f"{output_prefix}_part2_{timestamp}.pdf"

        # Noms de fichiers pour le téléchargement (ce que l'utilisateur verra)
        download_name1 = f"{output_prefix}_part1.pdf"
        download_name2 = f"{output_prefix}_part2.pdf"

        path1 = os.path.join(app.config['UPLOAD_FOLDER'], internal_name1)
        path2 = os.path.join(app.config['UPLOAD_FOLDER'], internal_name2)

        with open(path1, "wb") as f1:
            writer1.write(f1)
        with open(path2, "wb") as f2:
            writer2.write(f2)

        return jsonify({
            'success': True,
            'files': [
                {'filename': internal_name1, 'downloadName': download_name1, 'label': f'Télécharger {download_name1}'},
                {'filename': internal_name2, 'downloadName': download_name2, 'label': f'Télécharger {download_name2}'}
            ]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<filename>')
def download_file(filename):
    download_name = request.args.get('name', filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=download_name)
    return jsonify({'error': 'Fichier introuvable'}), 404


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)