import mammoth
from xhtml2pdf import pisa
from flask import Flask, render_template, request, send_file, jsonify
from pdf2docx import Converter
from reportlab.lib.utils import ImageReader
from werkzeug.utils import secure_filename
import os
from PyPDF2 import PdfMerger, PdfReader, PdfWriter, Transformation
import tempfile
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import zipfile
from pdf2image import convert_from_path
import io
import math
from flask import request, jsonify, send_file, render_template
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import tempfile
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['ALLOWED_DOCX_EXTENSIONS'] = {'docx', 'doc'}



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_IMAGE_EXTENSIONS']

def allowed_docx(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_DOCX_EXTENSIONS']

def create_text_watermark(text, output_path, width, height):
    """Crée un PDF temporaire de la taille exacte demandée avec un filigrane"""
    w = float(width)
    h = float(height)
    c = canvas.Canvas(output_path, pagesize=(w, h))
    c.translate(w / 2, h / 2)
    c.rotate(45)
    font_size = 60 * (w / 600.0)
    c.setFont("Helvetica-Bold", font_size)
    c.setFillColor(colors.grey, alpha=0.5)
    c.drawCentredString(0, 0, text)
    c.save()


# --- ROUTES D'INTERFACE (HTML) ---

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/tool/pdf-to-docx')
def pdf_to_docx_interface():
    return render_template('pdf_to_docx.html')

@app.route('/tool/docx_to_pdf')
def docx_to_pdf_interface():
    return render_template('docx_to_pdf.html')

@app.route('/tool/organize')
def organize_interface():
    return render_template('organize.html')

@app.route('/tool/watermark')
def watermark_interface():
    return render_template('watermark.html')

@app.route('/tool/sign')
def sign_interface():
    return render_template('sign.html')


@app.route('/tool/merge')
def merge_interface():
    return render_template('merge.html')


@app.route('/tool/merge_advanced')
def merge_advanced_interface():
    return render_template('merge_advanced.html')


@app.route('/tool/split')
def split_interface():
    return render_template('split.html')


@app.route('/tool/rotate')
def rotate_interface():
    return render_template('rotate.html')


@app.route('/tool/signature')
def signature_interface():
    return render_template('sign.html')


@app.route('/tool/view')
def view_interface():
    return render_template('view.html')
@app.route('/tool/pdf_to_jpeg')
def pdf_to_jpeg_interface():
    return render_template('pdf_to_jpeg.html')

@app.route('/tool/page_number')
def page_number_interface():
    return render_template('page_number.html')

@app.route('/screenshot')
def screenshot_pdf():
    return render_template('pdf_screenshot.html')


# --- ROUTES API ---

@app.route('/upload', methods=['POST'])
def upload_files():
    """Upload one or multiple files.

    Args:
        files[] (form-data): List of files to upload.

    Returns:
        JSON: List of uploaded files with original name and server path.

    Raises:
        400: If no file is provided in the request.
    """
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


@app.route('/api/docx_to_pdf', methods=['POST'])
def docx_to_pdf_action():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    if not file or not allowed_docx(file.filename):
        return jsonify({'error': 'Fichier Word (.docx ou .doc) requis'}), 400

    try:
        timestamp = datetime.now().strftime('%H%M%S')
        clean_name = secure_filename(file.filename)

        # Chemins des fichiers
        input_filename = f"src_docx_{timestamp}_{clean_name}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)

        # Sauvegarde du fichier DOCX
        file.save(input_path)

        # --- ÉTAPE 1 : Conversion DOCX -> HTML avec Mammoth ---
        with open(input_path, "rb") as docx_file:
            # Convertit le docx en HTML brut
            result = mammoth.convert_to_html(docx_file)
            html_content = result.value
            messages = result.messages  # Warnings éventuels

        # --- ÉTAPE 2 : Ajout de style CSS pour le PDF ---
        # On ajoute une structure HTML de base et du CSS pour que le PDF soit joli
        full_html = f"""
        <html>
        <head>
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{
                    font-family: Helvetica, Arial, sans-serif;
                    font-size: 12pt;
                    line-height: 1.5;
                    color: #333;
                }}
                h1, h2, h3 {{ color: #2c3e50; margin-top: 20px; }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-bottom: 20px;
                }}
                td, th {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                img {{
                    max-width: 100%;
                    height: auto;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

        # --- ÉTAPE 3 : Conversion HTML -> PDF avec xhtml2pdf ---
        output_filename = f"converted_{timestamp}_{os.path.splitext(clean_name)[0]}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        with open(output_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(
                src=full_html,  # Le contenu HTML
                dest=pdf_file  # Le fichier de destination
            )

        # Vérification des erreurs
        if pisa_status.err:
            return jsonify({'error': 'Erreur lors de la génération du PDF'}), 500

        # Nom pour le téléchargement
        download_name = os.path.splitext(clean_name)[0] + ".pdf"

        return jsonify({
            'success': True,
            'filename': output_filename,
            'downloadName': download_name
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/merge', methods=['POST'])
def merge_action():
    """Merge multiple PDF files into a single PDF.

    Args:
        files (list of str): List of file paths to merge (must be at least 2).
        outputName (str, optional): Base name for the merged PDF.

    Returns:
        JSON:
            - success (bool): True if merge succeeded.
            - filename (str): Server filename of merged PDF.
            - downloadName (str): Suggested download name.

    Raises:
        400: If fewer than 2 files are provided.
        500: On any error during merging.
    """
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


@app.route('/api/sign', methods=['POST'])
def sign_pdf_action():
    """Sign a PDF with a PNG image on the last page.

    Args:
        pdf (file): PDF file to sign.
        signature (file): PNG image of the signature.
        position (str, optional): Position of the signature ('bottom-right' by default).

    Returns:
        JSON:
            - success (bool): True if signing succeeded.
            - filename (str): Server filename of signed PDF.
            - downloadName (str): Suggested download name.

    Raises:
        400: If required files are missing or invalid.
        500: On any error during PDF signing.
    """
    # Vérification des fichiers
    if 'pdf' not in request.files or 'signature' not in request.files:
        return jsonify({'error': 'PDF et image de signature requis'}), 400

    pdf_file = request.files['pdf']
    sig_file = request.files['signature']
    position = request.form.get('position', 'bottom-right')

    # Validation basique des extensions
    if not pdf_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Le fichier PDF est invalide'}), 400
    if not sig_file.filename.lower().endswith('.png'):
        return jsonify({'error': 'La signature doit être un PNG'}), 400

    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_name = secure_filename(pdf_file.filename)
        sig_name = secure_filename(sig_file.filename)

        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"sign_src_{ts}_{pdf_name}")
        sig_path = os.path.join(app.config['UPLOAD_FOLDER'], f"sign_img_{ts}_{sig_name}")

        pdf_file.save(pdf_path)
        sig_file.save(sig_path)

        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        # Préparer l'image de signature
        img = ImageReader(sig_path)

        total_pages = len(reader.pages)

        # Parcourir les pages et n'appliquer la signature que sur la dernière
        for i, page in enumerate(reader.pages):
            if i == total_pages - 1:
                w = float(page.mediabox.width)
                h = float(page.mediabox.height)

                # Overlay temporaire pour la dernière page uniquement
                overlay_path = os.path.join(app.config['UPLOAD_FOLDER'], f"overlay_{ts}_{os.urandom(4).hex()}.pdf")
                c = canvas.Canvas(overlay_path, pagesize=(w, h))

                # Taille de la signature: ~25% de la largeur de page
                target_width = w * 0.25
                iw, ih = img.getSize()
                aspect = ih / iw
                target_height = target_width * aspect

                margin = 36.0  # 0.5 inch
                if position == 'bottom-left':
                    x = margin
                    y = margin
                elif position == 'bottom-right':
                    x = w - margin - target_width
                    y = margin
                elif position == 'bottom-center':
                    x = (w - target_width) / 2.0
                    y = margin
                else:
                    x = w - margin - target_width
                    y = margin

                c.drawImage(img, x, y, width=target_width, height=target_height, mask='auto')
                c.save()

                # Fusion overlay avec la dernière page
                overlay_reader = PdfReader(overlay_path)
                overlay_page = overlay_reader.pages[0]
                page.merge_page(overlay_page)

                # Nettoyage du fichier overlay temporaire
                try:
                    os.remove(overlay_path)
                except Exception:
                    pass

            # Ajouter la page (signée si c'est la dernière)
            writer.add_page(page)

        # Enregistrer le PDF signé
        out_download = f"signe_{os.path.splitext(pdf_name)[0]}.pdf"
        out_internal = f"signed_{ts}_{secure_filename(out_download)}"
        out_path = os.path.join(app.config['UPLOAD_FOLDER'], out_internal)

        with open(out_path, "wb") as f:
            writer.write(f)

        return jsonify({
            'success': True,
            'filename': out_internal,
            'downloadName': out_download
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/organize', methods=['POST'])
def reorder_action():
    """Reorder pages of a PDF based on a provided index list."""
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    # L'ordre est envoyé sous forme de chaîne "0,2,1,3..."
    order_string = request.form.get('order', '')

    if not file or not allowed_file(file.filename):
        return jsonify({'error': 'Fichier PDF invalide'}), 400

    if not order_string:
        return jsonify({'error': 'Ordre des pages manquant'}), 400

    try:
        # Convertir la chaîne "0,2,1" en liste d'entiers [0, 2, 1]
        page_order = [int(x) for x in order_string.split(',') if x.strip().isdigit()]

        timestamp = datetime.now().strftime('%H%M%S')
        clean_name = secure_filename(file.filename)

        # Sauvegarde temporaire pour lecture
        temp_input = f"reorder_src_{timestamp}_{clean_name}"
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_input)
        file.save(input_path)

        reader = PdfReader(input_path)
        writer = PdfWriter()

        total_pages = len(reader.pages)

        # Reconstruction du PDF dans le nouvel ordre
        for index in page_order:
            if 0 <= index < total_pages:
                writer.add_page(reader.pages[index])
            else:
                print(f"Index de page invalide ignoré : {index}")

        output_filename = f"reordered_{timestamp}_{clean_name}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        with open(output_path, "wb") as f:
            writer.write(f)

        download_name = f"reorganise_{clean_name}"

        return jsonify({
            'success': True,
            'filename': output_filename,
            'downloadName': download_name
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/api/merge_advanced', methods=['POST'])
def merge_advanced_action():
    """Merge multiple PDF groups into separate PDFs.

    Args:
        groups (list of dict): Each dict contains:
            - name (str, optional): Base name for the group.
            - files (list of str): File paths to merge for the group.

    Returns:
        JSON:
            - success (bool): True if at least one group was merged.
            - files (list of dict): Each dict contains:
                - filename (str): Server filename of merged PDF.
                - downloadName (str): Suggested download name.
                - displayName (str): Name to display in UI.

    Raises:
        400: If no groups provided or no files generated.
        500: On any error during merging.
    """
    data = request.json
    groups = data.get('groups', [])

    if not groups:
        return jsonify({'error': 'Aucun groupe fourni'}), 400

    try:
        result_files = []
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for idx, group in enumerate(groups):
            group_name = secure_filename(group.get('name', f'groupe_{idx + 1}')) or f'groupe_{idx + 1}'
            file_paths = group.get('files', [])

            if len(file_paths) < 1:
                continue

            merger = PdfMerger()
            for file_path in file_paths:
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)
                if os.path.exists(full_path):
                    merger.append(full_path)

            output_filename = f"{group_name}_{timestamp}.pdf"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            merger.write(output_path)
            merger.close()

            result_files.append({
                'filename': output_filename,
                'downloadName': f"{group_name}.pdf",
                'displayName': f"{group_name}.pdf"
            })

        if not result_files:
            return jsonify({'error': 'Aucun fichier généré'}), 400

        return jsonify({
            'success': True,
            'files': result_files
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/split', methods=['POST'])
def split_action():
    """Split a PDF into two parts at a specified page.

    Args:
        filename (str): Name of the PDF file to split.
        splitPage (int, optional): Page number at which to split (default 1).
        outputPrefix (str, optional): Prefix for the output files (default 'split').

    Returns:
        JSON:
            - success (bool): True if split succeeded.
            - files (list of dict): Each dict contains:
                - filename (str): Server filename of split PDF.
                - downloadName (str): Suggested download name.
                - label (str): Display label for download.

    Raises:
        400: If split page is invalid.
        500: On any error during PDF splitting.
    """
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


def create_text_watermark(text, output_path, width, height):
    """Crée un PDF temporaire couvrant toute la page avec un texte répété en diagonale."""
    w = float(width)
    h = float(height)
    c = canvas.Canvas(output_path, pagesize=(w, h))

    # Style du motif
    angle = 45
    font_name = "Helvetica-Bold"
    # Taille de police proportionnelle à la page (~6% du côté le plus court)
    font_size = max(14, int(min(w, h) * 0.06))
    c.setFont(font_name, font_size)
    # Couleur avec transparence légère
    c.setFillColor(colors.Color(0, 0, 0, alpha=0.12))

    # Rotation au centre pour un motif diagonal
    c.saveState()
    c.translate(w / 2.0, h / 2.0)
    c.rotate(angle)

    # Espacements en fonction de la taille du texte
    text_w = c.stringWidth(text, font_name, font_size)
    x_step = max(120.0, text_w * 1.2)
    y_step = max(80.0, font_size * 2.5)

    # Couvrir une zone plus grande que la page
    cols = int((w * 2) / x_step) + 3
    rows = int((h * 2) / y_step) + 3

    start_col = -cols // 2
    end_col = cols // 2
    start_row = -rows // 2
    end_row = rows // 2

    for r in range(start_row, end_row + 1):
        y = r * y_step
        # Décalage en quinconce pour mieux remplir
        offset = (r % 2) * (x_step / 2.0)
        for cidx in range(start_col, end_col + 1):
            x = cidx * x_step + offset
            c.drawCentredString(x, y, text)

    c.restoreState()
    c.save()

@app.route('/api/watermark', methods=['POST'])
def watermark_action():
    """Apply a text watermark to one or multiple PDF files.

    Args:
        files[] (form-data): List of PDF files to watermark.
        watermarkText (str, optional): Text to use as watermark (default 'CONFIDENTIEL').
        outputName (str, optional): Base name for output file(s).

    Returns:
        JSON:
            - success (bool): True if processing succeeded.
            - filename (str): Server filename of resulting PDF or ZIP.
            - downloadName (str): Suggested download name for user.
            - type (str): 'single' for one file, 'zip' for multiple files.

    Raises:
        400: If no files are provided or no valid files processed.
        500: On any error during watermarking.
    """
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
            if not file or not allowed_file(file.filename):
                continue

            filename = secure_filename(file.filename)
            source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"src_{index}_{timestamp_global}_{filename}")
            file.save(source_path)

            source_reader = PdfReader(source_path)
            writer = PdfWriter()

            # Générer un filigrane adapté à CHAQUE page (dimensions exactes)
            for page_i, page in enumerate(source_reader.pages):
                page_width = float(page.mediabox.width)
                page_height = float(page.mediabox.height)

                wm_pdf_name = f"wm_temp_{index}_{page_i}_{timestamp_global}.pdf"
                wm_path = os.path.join(app.config['UPLOAD_FOLDER'], wm_pdf_name)
                create_text_watermark(watermark_text, wm_path, page_width, page_height)

                wm_reader = PdfReader(wm_path)
                wm_page = wm_reader.pages[0]

                page.merge_page(wm_page)
                writer.add_page(page)

            output_filename = f"WM_{filename}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"out_{index}_{timestamp_global}_{filename}")

            with open(output_path, "wb") as f:
                writer.write(f)

            processed_files.append({
                'path': output_path,
                'download_name': output_filename
            })

        if not processed_files:
            return jsonify({'error': 'Aucun fichier valide traité'}), 400

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


@app.route('/api/rotate', methods=['POST'])
def rotate_action():
    """    Rotate a PDF file with optional tight bounding box adjustment.

    Args:
        file (file): PDF file to rotate.
        angle (int, optional): Rotation angle in degrees (default 90).
        direction (str, optional): 'clockwise' or 'counterclockwise' (default 'clockwise').
        outputName (str, optional): Base name for output PDF (default 'rotated').

    Returns:
        JSON:
            - success (bool): True if rotation succeeded.
            - filename (str): Server filename of rotated PDF.
            - downloadName (str): Suggested download name.

    Raises:
        400: If no file provided or file format is invalid.
        500: On any error during rotation.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    angle_input = int(request.form.get('angle', 90))
    direction = request.form.get('direction', 'clockwise')
    output_name = request.form.get('outputName', 'rotated')
    output_name = secure_filename(output_name) or 'rotated'

    if not allowed_file(file.filename):
        return jsonify({'error': 'Format de fichier invalide'}), 400

    try:
        # 1. Calcul de l'angle
        if direction == 'clockwise':
            rotation_angle = -angle_input
        else:
            rotation_angle = angle_input

        # Sauvegarder temporairement
        timestamp = datetime.now().strftime('%H%M%S')
        temp_filename = f"temp_{timestamp}_{secure_filename(file.filename)}"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(temp_path)

        reader = PdfReader(temp_path)
        writer = PdfWriter()

        for page in reader.pages:
            # Si rotation simple (90, 180...), on utilise la méthode standard
            if rotation_angle % 90 == 0:
                page.rotate(rotation_angle)
                writer.add_page(page)
            else:
                # --- CALCUL GÉOMÉTRIQUE PRÉCIS (45°) ---

                # 1. On récupère la taille VISIBLE (CropBox) et non la taille totale
                # Cela évite de tourner des marges vides inutiles
                w = float(page.cropbox.width)
                h = float(page.cropbox.height)

                # 2. Conversion en radians pour les calculs
                angle_rad = math.radians(rotation_angle)
                cos_a = abs(math.cos(angle_rad))
                sin_a = abs(math.sin(angle_rad))

                # 3. Calcul de la nouvelle taille EXACTE (Bounding Box)
                # C'est la taille minimale pour contenir le rectangle incliné
                new_w = (w * cos_a) + (h * sin_a)
                new_h = (w * sin_a) + (h * cos_a)

                # 4. On crée une page vierge de la nouvelle taille exacte
                # Note: PyPDF2 modifie la page en place, donc on ajuste ses dimensions

                # IMPORTANT : On normalise la page à (0,0) pour simplifier la rotation
                page.mediabox.lower_left = (0, 0)
                page.mediabox.upper_right = (w, h)

                # Matrice de transformation :
                # - Centrer l'ancienne page au point (0,0)
                # - Pivoter
                # - Déplacer vers le centre de la NOUVELLE taille
                op = Transformation().translate(-w / 2, -h / 2).rotate(rotation_angle).translate(new_w / 2, new_h / 2)

                page.add_transformation(op)

                # 5. On applique les nouvelles dimensions au conteneur PDF
                page.mediabox.upper_right = (new_w, new_h)
                # On s'assure que la zone affichée (CropBox) correspond à la zone totale
                page.cropbox.upper_right = (new_w, new_h)

                writer.add_page(page)

        output_filename = f"{output_name}_{timestamp}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

        return jsonify({
            'success': True,
            'filename': output_filename,
            'downloadName': f"{output_name}.pdf"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/signature', methods=['POST'])
def signature_action():
    """Add a signature image to a PDF.

    Args:
        pdf (file): PDF file to sign.
        signature (file): Image file (PNG/JPG) of the signature.
        position (str, optional): Position on the page ('bottom-right' by default).
        outputName (str, optional): Base name for output PDF (default 'signed').

    Returns:
        JSON:
            - success (bool): True if signing succeeded.
            - filename (str): Server filename of signed PDF.
            - downloadName (str): Suggested download name.

    Raises:
        400: If required files are missing or invalid format.
        500: On any error during PDF signing.
    """
    if 'pdf' not in request.files or 'signature' not in request.files:
        return jsonify({'error': 'PDF et signature requis'}), 400

    pdf_file = request.files['pdf']
    signature_file = request.files['signature']
    position = request.form.get('position', 'bottom-right')
    output_name = request.form.get('outputName', 'signed')
    output_name = secure_filename(output_name) or 'signed'

    if not allowed_file(pdf_file.filename) or not allowed_image(signature_file.filename):
        return jsonify({'error': 'Format de fichier invalide'}), 400

    try:
        timestamp = datetime.now().strftime('%H%M%S')

        # Sauvegarder le PDF
        pdf_temp = f"pdf_{timestamp}_{secure_filename(pdf_file.filename)}"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_temp)
        pdf_file.save(pdf_path)

        # Lire le PDF
        reader = PdfReader(pdf_path)
        first_page = reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)

        # Créer un PDF avec la signature
        sig_pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"sig_{timestamp}.pdf")
        c = canvas.Canvas(sig_pdf_path, pagesize=(page_width, page_height))

        # Calculer la position
        sig_width = 150  # Largeur de la signature
        sig_height = 50  # Hauteur de la signature
        margin = 30

        if position == 'bottom-right':
            x = page_width - sig_width - margin
            y = margin
        elif position == 'bottom-left':
            x = margin
            y = margin
        elif position == 'top-right':
            x = page_width - sig_width - margin
            y = page_height - sig_height - margin
        else:  # top-left
            x = margin
            y = page_height - sig_height - margin

        # Dessiner la signature
        c.drawImage(signature_file, x, y, width=sig_width, height=sig_height, mask='auto', preserveAspectRatio=True)
        c.save()

        # Fusionner avec chaque page
        sig_reader = PdfReader(sig_pdf_path)
        sig_page = sig_reader.pages[0]
        writer = PdfWriter()

        for page in reader.pages:
            page.merge_page(sig_page)
            writer.add_page(page)

        # Sauvegarder le résultat
        output_filename = f"{output_name}_{timestamp}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

        return jsonify({
            'success': True,
            'filename': output_filename,
            'downloadName': f"{output_name}.pdf"
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/check_pdf_pages', methods=['POST'])
def check_pdf_pages():
    """Check the number of pages in a PDF file.

    Args:
        file (file): PDF file to check.

    Returns:
        JSON:
            - success (bool): True if check succeeded.
            - pages (int): Number of pages in the PDF.

    Raises:
        400: If no file is provided.
        500: On any error during PDF reading.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400

    file = request.files['file']

    try:
        # Lire directement depuis le stream
        reader = PdfReader(file.stream)
        page_count = len(reader.pages)

        return jsonify({
            'success': True,
            'pages': page_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- AJOUTER DANS LA SECTION ROUTES D'INTERFACE ---



# --- AJOUTER DANS LA SECTION ROUTES API ---

@app.route('/api/pdf-to-docx', methods=['POST'])
def pdf_to_docx_action():
    data = request.json or {}
    filename = data.get('file')
    output_name = data.get('outputName', '').strip()

    if not filename:
        return jsonify({'error': 'Aucun fichier PDF fourni'}), 400

    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'Fichier introuvable'}), 404

    base_name = secure_filename(output_name) or 'document_converti'
    if not base_name.lower().endswith('.docx'):
        download_name = f"{base_name}.docx"
    else:
        download_name = base_name

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    internal_filename = f"{os.path.splitext(download_name)[0]}_{timestamp}.docx"
    internal_path = os.path.join(app.config['UPLOAD_FOLDER'], internal_filename)

    try:
        converter = Converter(pdf_path)
        converter.convert(internal_path, start=0, end=None)
        converter.close()
    except Exception as e:
        return jsonify({'error': f'Conversion impossible: {e}'}), 500

    return jsonify({
        'success': True,
        'filename': internal_filename,
        'downloadName': download_name
    })
@app.route('/api/pdf_to_jpeg', methods=['POST'])
def pdf_to_jpeg_action():
    """Convert a PDF (up to 30 pages) into JPEG images and return as a ZIP.

    Args:
        file (file): PDF file to convert.
        outputName (str, optional): Base name for output ZIP (default 'images_pdf').

    Returns:
        JSON:
            - success (bool): True if conversion succeeded.
            - filename (str): Server filename of ZIP containing images.
            - downloadName (str): Suggested download name for user.
            - image_count (int): Number of pages converted to JPEG.

    Raises:
        400: If no file provided, invalid format, or PDF pages cannot be read.
        500: If pdf2image is missing or any error occurs during conversion.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    output_name = request.form.get('outputName', 'images_pdf')
    output_name = secure_filename(output_name) or 'images_pdf'

    if not allowed_file(file.filename):
        return jsonify({'error': 'Format de fichier invalide'}), 400

    try:


        timestamp = datetime.now().strftime('%H%M%S')
        temp_pdf = f"temp_{timestamp}_{secure_filename(file.filename)}"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_pdf)
        file.save(temp_path)

        # Convertir en images (max 30 pages via last_page)
        # dpi=200 est un bon compromis qualité/poids
        images = convert_from_path(
            temp_path,
            dpi=200,
            fmt='jpeg',
            first_page=1,
            last_page=30
        )

        if not images:
            return jsonify({'error': 'Impossible de lire les pages du PDF'}), 400

        # Créer un ZIP en mémoire ou sur disque
        zip_filename = f"{output_name}_{timestamp}.zip"
        zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_filename)

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for i, image in enumerate(images, 1):
                # Sauvegarder l'image en mémoire pour l'ajouter au ZIP sans écrire sur le disque
                img_buffer = io.BytesIO()
                image.save(img_buffer, format='JPEG', quality=90)
                img_buffer.seek(0)

                # Nom dans le zip : page_001.jpg, page_002.jpg...
                img_filename = f"page_{i:03d}.jpg"
                zipf.writestr(img_filename, img_buffer.read())

        return jsonify({
            'success': True,
            'filename': zip_filename,
            'downloadName': f"{output_name}.zip",
            'image_count': len(images)
        })

    except ImportError:
        return jsonify({'error': 'Le module pdf2image est manquant sur le serveur.'}), 500
    except Exception as e:
        return jsonify({'error': f"Erreur de conversion : {str(e)}"}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download a file from the server.

    Args:
        filename (str): Internal server filename to download.
        name (str, optional, query param): Suggested download name for the file.

    Returns:
        File: The requested file as an attachment.

    Raises:
        404: If the requested file does not exist on the server.
    """
    download_name = request.args.get('name', filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=download_name)
    return jsonify({'error': 'Fichier introuvable'}), 404

@app.route('/api/page_numbers', methods=['POST'])
def page_number_action():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier PDF'}), 400

        file = request.files['file']
        position = request.form.get('position', 'bottom-center')

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Format invalide'}), 400

        # 🔹 حفظ PDF مؤقت
        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        file.save(temp_input.name)
        temp_input.close()

        reader = PdfReader(temp_input.name)
        writer = PdfWriter()

        for i, page in enumerate(reader.pages, start=1):
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            overlay_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name

            c = canvas.Canvas(overlay_path, pagesize=(w, h))
            c.setFont("Helvetica", 10)   # ✅ مهم جدًا
            text = str(i)

            if position == 'bottom-left':
                x, y = 40, 30
                c.drawString(x, y, text)
            elif position == 'bottom-right':
                x, y = w - 40
                c.drawRightString(x, 30, text)
            else:  # bottom-center
                c.drawCentredString(w / 2, 30, text)

            c.save()  # ✅ إغلاق صحيح

            overlay_reader = PdfReader(overlay_path)
            page.merge_page(overlay_reader.pages[0])
            writer.add_page(page)

            os.remove(overlay_path)

        output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        with open(output_path, "wb") as f:
            writer.write(f)

        return send_file(
            output_path,
            as_attachment=True,
            download_name="numero.pdf"
        )

    except Exception as e:
        import traceback
        traceback.print_exc()   # 🔥 سيظهر الخطأ الحقيقي في التيرمينال
        return jsonify({'error': 'Erreur serveur'}), 500
    

@app.route('/api/capture_region', methods=['POST'])
def api_capture_region():
    """API endpoint to capture a region from PDF"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'File must be a PDF'}), 400
        
        # Get all data
        page = request.form.get('page', '0')
        x = request.form.get('x', '0')
        y = request.form.get('y', '0')
        width = request.form.get('width', '100')
        height = request.form.get('height', '100')
        # viewer_width et viewer_height ne sont plus nécessaires
        scale_factor = request.form.get('scale_factor', '1.0') # <-- NOUVEAU
        format = request.form.get('format', 'PNG')
        
        # Convert to appropriate types
        try:
            page_num = int(page)
            x_pos = float(x)
            y_pos = float(y)
            region_width = float(width)
            region_height = float(height)
            display_scale = float(scale_factor) # <-- NOUVEAU
        except ValueError as ve:
            return jsonify({'error': f'Invalid coordinate values: {str(ve)}'}), 400
        
        # Read PDF file
        pdf_bytes = file.read()
        
        # Extract region
        image_bytes, mime_type = extract_pdf_region(
            pdf_bytes,
            page_num,
            x_pos,
            y_pos,
            region_width,
            region_height,
            display_scale, # Passez le facteur d'échelle directement
            format=format
        )
        
        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if format.upper() in ['JPEG', 'JPG']:
            filename = f'capture_{timestamp}.jpg'
        else:
            filename = f'capture_{timestamp}.png'
        
        # Return image
        return send_file(
            io.BytesIO(image_bytes),
            mimetype=mime_type,
            as_attachment=True,
            download_name=filename
        )
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"API Error: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/capture_multiple', methods=['POST'])
def capture_multiple_regions():
    """API endpoint to capture multiple regions and return as ZIP"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'File must be a PDF'}), 400
        
        # Get JSON data for multiple regions
        regions_data = request.form.get('regions', '[]')
        
        try:
            regions = json.loads(regions_data)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid regions data'}), 400
        
        if not regions:
            return jsonify({'error': 'No regions specified'}), 400
        
        pdf_bytes = file.read()
        
        # Create a ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, region in enumerate(regions):
                try:
                    page_num = region.get('page', 0)
                    x = float(region.get('x', 0))
                    y = float(region.get('y', 0))
                    width = float(region.get('width', 100))
                    height = float(region.get('height', 100))
                    format = region.get('format', 'PNG')
                    
                    # Extract the region
                    image_bytes, mime_type = extract_pdf_region(
                        pdf_bytes,
                        page_num,
                        x,
                        y,
                        width,
                        height,
                        display_scale=2,
                        format=format
                    )
                    
                    # Determine file extension
                    if 'jpeg' in mime_type or 'jpg' in mime_type:
                        ext = 'jpg'
                    else:
                        ext = 'png'
                    
                    # Add to ZIP
                    filename = f'capture_{i+1:03d}.{ext}'
                    zip_file.writestr(filename, image_bytes)
                    
                except Exception as e:
                    # Skip failed regions but continue with others
                    continue
        
        zip_buffer.seek(0)
        
        # Return ZIP file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'captures_{timestamp}.zip'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def extract_pdf_region(pdf_bytes, page_num, x_pixels, y_pixels, width_pixels, height_pixels, 
                     display_scale, format='PNG'): # viewer_width/height retirés
    """
    Extrait une région d'une page PDF en utilisant le facteur d'échelle du Canvas.
    """
    pdf_document = None
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_document[page_num]
        
        page_width_points = page.rect.width
        page_height_points = page.rect.height
        
        # 1. Conversion Pixels Canvas -> Points PDF (simple ratio)
        # Points = Pixels / Scale
        x_points = x_pixels / display_scale
        y_points = y_pixels / display_scale
        width_points = width_pixels / display_scale
        height_points = height_pixels / display_scale
        
        # La conversion Y n'est plus nécessaire si on suppose que PDF.js 
        # rend le PDF avec l'origine (0,0) en haut à gauche (ce qui est standard pour Canvas).
        # Si vous rencontrez un décalage vertical, réactivez: y_points = page_height_points - y_points - height_points

        # Définir le rectangle à extraire (en PDF points)
        # (x0, y0, x1, y1)
        x0 = max(0.0, x_points)
        y0 = max(0.0, y_points)
        x1 = min(page_width_points, x_points + width_points)
        y1 = min(page_height_points, y_points + height_points)

        rect = fitz.Rect(x0, y0, x1, y1)

        # Validate rect dimensions
        rect_width = rect.x1 - rect.x0
        rect_height = rect.y1 - rect.y0
        if rect_width <= 0 or rect_height <= 0:
            raise ValueError(f"Invalid extraction rectangle (width={rect_width}, height={rect_height}). Check selection and scale.")

        # Rendu haute résolution (par ex. 300 DPI)
        output_scale = 300.0 / 72.0
        mat = fitz.Matrix(output_scale, output_scale)

        try:
            pix = page.get_pixmap(matrix=mat, clip=rect)
        except Exception as e_pix:
            # Log detailed info and re-raise a clearer error
            print(f"get_pixmap failed: page_size={page_width_points}x{page_height_points}, rect={rect}, scale={display_scale}, error={e_pix}")
            raise
        
        # Convert to bytes
        if format.upper() == 'JPEG' or format.upper() == 'JPG':
            img_bytes = pix.tobytes("jpeg")
            mime_type = 'image/jpeg'
        else:
            img_bytes = pix.tobytes("png")
            mime_type = 'image/png'
        
        print(f"Generated image: {pix.width}x{pix.height} pixels")
        
        # IMPORTANT: Keep document open until we're done with pix
        # The pixmap contains the image data, we can now close the document
        pdf_document.close()
        pdf_document = None
        
        return img_bytes, mime_type
        
    except Exception as e:
        print(f"Error in extract_pdf_region: {e}")
        raise Exception(f"Failed to extract region from PDF: {str(e)}")
    finally:
        if pdf_document:
            pdf_document.close()


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)