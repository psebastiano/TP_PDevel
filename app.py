from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename
import os
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import tempfile
from datetime import datetime

# Nouveaux imports pour le dessin du texte
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
import zipfile

app = Flask(__name__)
# Dossier temporaire système
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# --- FONCTION UTILITAIRE : GÉNÉRER LE FILIGRANE ---
def create_text_watermark(text, output_path, width, height):
    """Crée un PDF temporaire de la taille exacte demandée"""
    # On s'assure que width/height sont des floats pour ReportLab
    w = float(width)
    h = float(height)

    c = canvas.Canvas(output_path, pagesize=(w, h))

    # On se place au centre exact de CETTE page
    c.translate(w / 2, h / 2)
    c.rotate(45)

    # On adapte légèrement la taille de police selon la largeur de page
    # (Base 60 pour une largeur d'environ 600 points)
    font_size = 60 * (w / 600.0)
    c.setFont("Helvetica-Bold", font_size)

    c.setFillColor(colors.grey, alpha=0.5)
    c.drawCentredString(0, 0, text)
    c.save()


# --- ROUTES D'INTERFACE (HTML) ---

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/tool/watermark')
def watermark_interface():
    return render_template('watermark.html')


@app.route('/tool/merge')
def merge_interface():
    return render_template('merge.html')


@app.route('/tool/split')
def split_interface():
    return render_template('split.html')


# --- ROUTES API ---

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'Aucun fichier trouvé'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%H%M%S')}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            uploaded_files.append({
                'name': filename,
                'path': unique_filename
            })

    return jsonify({'files': uploaded_files})


@app.route('/api/merge', methods=['POST'])
def merge_action():
    data = request.json
    file_paths = data.get('files', [])
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


@app.route('/api/split', methods=['POST'])
def split_action():
    data = request.json
    filename = data.get('filename')
    split_page = int(data.get('splitPage', 1))
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
        internal_name1 = f"{output_prefix}_part1_{timestamp}.pdf"
        internal_name2 = f"{output_prefix}_part2_{timestamp}.pdf"
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


# --- NOUVELLE ROUTE FILIGRANE (TEXTE) ---
@app.route('/api/watermark', methods=['POST'])
def watermark_action():
    if 'files[]' not in request.files:
        return jsonify({'error': 'Veuillez fournir au moins un fichier PDF'}), 400

    files = request.files.getlist('files[]')
    watermark_text = request.form.get('watermarkText', 'CONFIDENTIEL').strip()
    output_name_user = request.form.get('outputName', '').strip()

    if not files:
        return jsonify({'error': 'Aucun fichier reçu'}), 400

    processed_files = []
    timestamp_global = datetime.now().strftime('%H%M%S')

    try:
        for index, file in enumerate(files):
            if file and allowed_file(file.filename):
                # 1. Sauvegarde du fichier source
                filename = secure_filename(file.filename)
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"src_{index}_{timestamp_global}_{filename}")
                file.save(source_path)

                # 2. Analyse de la taille de la première page du PDF
                source_reader = PdfReader(source_path)
                first_page = source_reader.pages[0]

                # Récupération des dimensions (MediaBox)
                page_width = first_page.mediabox.width
                page_height = first_page.mediabox.height

                # 3. Création d'un filigrane SPÉCIFIQUE à ce fichier (bonne taille)
                watermark_pdf_name = f"wm_temp_{index}_{timestamp_global}.pdf"
                watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], watermark_pdf_name)

                # On passe les dimensions détectées
                create_text_watermark(watermark_text, watermark_path, page_width, page_height)

                # 4. Fusion
                watermark_reader = PdfReader(watermark_path)
                watermark_page = watermark_reader.pages[0]
                writer = PdfWriter()

                for page in source_reader.pages:
                    # PyPDF2 superpose les pages. Si elles font la même taille, le centre s'aligne.
                    page.merge_page(watermark_page)
                    writer.add_page(page)

                # 5. Écriture du résultat
                output_filename = f"WM_{filename}"
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"out_{index}_{timestamp_global}_{filename}")

                with open(output_path, "wb") as f:
                    writer.write(f)

                processed_files.append({
                    'path': output_path,
                    'download_name': output_filename
                })

        # --- Fin de la boucle, gestion du retour ---

        if not processed_files:
            return jsonify({'error': 'Aucun fichier valide traité'}), 400

        # Cas A : Un seul fichier
        if len(processed_files) == 1:
            final_file = processed_files[0]
            dl_name = final_file['download_name']
            if output_name_user:
                dl_name = output_name_user if output_name_user.lower().endswith('.pdf') else output_name_user + '.pdf'

            return jsonify({
                'success': True,
                'filename': os.path.basename(final_file['path']),
                'downloadName': dl_name,
                'type': 'single'
            })

        # Cas B : ZIP
        else:
            zip_name = output_name_user if output_name_user else "documents_filigranes"
            if not zip_name.lower().endswith('.zip'):
                zip_name += '.zip'

            zip_filename_internal = f"batch_{timestamp_global}.zip"
            zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_filename_internal)

            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for p_file in processed_files:
                    zipf.write(p_file['path'], p_file['download_name'])

            return jsonify({
                'success': True,
                'filename': zip_filename_internal,
                'downloadName': zip_name,
                'type': 'zip'
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