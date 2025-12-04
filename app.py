from flask import Flask, render_template, request, send_file, jsonify
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

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['ALLOWED_IMAGE_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_IMAGE_EXTENSIONS']


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


@app.route('/tool/pdf_to_jpeg')
def pdf_to_jpeg_interface():
    return render_template('pdf_to_jpeg.html')


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
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"src_{index}_{timestamp_global}_{filename}")
                file.save(source_path)

                source_reader = PdfReader(source_path)
                first_page = source_reader.pages[0]
                page_width = first_page.mediabox.width
                page_height = first_page.mediabox.height

                watermark_pdf_name = f"wm_temp_{index}_{timestamp_global}.pdf"
                watermark_path = os.path.join(app.config['UPLOAD_FOLDER'], watermark_pdf_name)
                create_text_watermark(watermark_text, watermark_path, page_width, page_height)

                watermark_reader = PdfReader(watermark_path)
                watermark_page = watermark_reader.pages[0]
                writer = PdfWriter()

                for page in source_reader.pages:
                    page.merge_page(watermark_page)
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
        # Nécessite l'installation de pdf2image : pip install pdf2image
        # Et Poppler doit être installé sur le système.


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


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)