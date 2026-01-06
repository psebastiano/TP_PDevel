import base64
import json
import traceback
import uuid

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
import fitz

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

@app.route('/tool/pipeline')
def pipeline_interface():
    return render_template('pipeline.html')

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


@app.route('/tool/protect')
def protect_interface():
    return render_template('protect.html')

@app.route('/tool/pdf_to_jpeg')
def pdf_to_jpeg_interface():
    return render_template('pdf_to_jpeg.html')

@app.route('/tool/img_to_pdf')
def img_to_pdf_interface():
    return render_template('img_to_pdf.html')

@app.route('/tool/page_number')
def page_number_interface():
    return render_template('page_number.html')

@app.route('/screenshot')
def screenshot_pdf():
    return render_template('pdf_screenshot.html')

@app.route('/tool/compress')
def compress_interface():
    return render_template('compress.html')

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


@app.route('/api/pipeline', methods=['POST'])
def pipeline_action():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    pipeline_json = request.form.get('pipeline', '[]')

    try:
        actions = json.loads(pipeline_json)
    except:
        return jsonify({'error': 'JSON invalide'}), 400

    if not actions:
        return jsonify({'error': 'Aucune action'}), 400

    try:
        timestamp = datetime.now().strftime('%H%M%S')
        current_filename = f"pipe_start_{timestamp}_{secure_filename(file.filename)}"
        current_path = os.path.join(app.config['UPLOAD_FOLDER'], current_filename)
        file.save(current_path)

        final_extension = "pdf"

        for i, action in enumerate(actions):
            # Si l'étape précédente a produit un ZIP, on ne peut plus continuer
            if final_extension == "zip":
                return jsonify({
                                   'error': 'Les blocs "Diviser" ou "PDF vers JPEG" terminent le processus (création ZIP). Ils doivent être en dernière position.'}), 400

            action_type = action.get('type')

            # Diviser et PDF2JPEG produisent maintenant des ZIP
            step_ext = "zip" if (action_type == 'pdf2jpeg' or action_type == 'split') else "pdf"

            next_filename = f"pipe_step{i}_{timestamp}.{step_ext}"
            next_path = os.path.join(app.config['UPLOAD_FOLDER'], next_filename)

            process_pipeline_step(action, current_path, next_path)

            current_path = next_path
            current_filename = next_filename
            final_extension = step_ext

        return jsonify({
            'success': True,
            'filename': current_filename,
            'downloadName': f"resultat_pipeline.{final_extension}"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def apply_action(node, input_path, output_path):
    """Exécute une action unitaire sur un fichier"""
    action_type = node.get('type')
    params = node.get('params', {})

    # Lecture générique
    try:
        reader = PdfReader(input_path)
    except:
        # Si le fichier n'est pas un PDF (ex: après conversion docx), on gère au cas par cas
        reader = None

    writer = PdfWriter()

    if action_type == 'rotate':
        angle = int(params.get('angle', 90))
        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)
        with open(output_path, 'wb') as f:
            writer.write(f)

    elif action_type == 'protect':
        password = params.get('password', '123456')
        for page in reader.pages: writer.add_page(page)
        writer.encrypt(password)
        with open(output_path, 'wb') as f:
            writer.write(f)

    elif action_type == 'watermark':
        text = params.get('text', 'CONFIDENTIEL')
        # Création d'un filigrane temporaire (simplifié pour l'exemple)
        if len(reader.pages) > 0:
            p = reader.pages[0]
            wm_path = output_path + "_temp_wm.pdf"
            c = canvas.Canvas(wm_path, pagesize=(float(p.mediabox.width), float(p.mediabox.height)))
            c.setFont("Helvetica-Bold", 60)
            c.setFillColor(colors.grey, alpha=0.5)
            c.drawCentredString(float(p.mediabox.width) / 2, float(p.mediabox.height) / 2, text)
            c.save()

            wm_reader = PdfReader(wm_path)
            for page in reader.pages:
                page.merge_page(wm_reader.pages[0])
                writer.add_page(page)
            if os.path.exists(wm_path): os.remove(wm_path)
        else:
            for page in reader.pages: writer.add_page(page)
        with open(output_path, 'wb') as f:
            writer.write(f)

    elif action_type == 'pdf-to-docx':
        # Conversion qui change l'extension
        docx_out = output_path.replace('.pdf', '.docx')
        cv = Converter(input_path)
        cv.convert(docx_out, start=0, end=None)
        cv.close()
        # On renomme pour que la suite du pipeline trouve le fichier au chemin attendu "output_path"
        # Astuce : Si l'étape d'après attend un PDF, ça plantera, mais c'est logique.
        if os.path.exists(docx_out):
            if os.path.exists(output_path): os.remove(output_path)
            os.rename(docx_out, output_path)

    elif action_type == 'split':
        # Le split est spécial, il ne génère pas UN fichier de sortie ici,
        # mais la logique de graphe va gérer les deux fichiers.
        # Cette fonction ne fait rien pour le split, voir 'process_graph_node'
        pass

    else:
        # Action inconnue ou simple passe-plat
        if reader:
            for p in reader.pages: writer.add_page(p)
            with open(output_path, 'wb') as f:
                writer.write(f)


def process_graph_node(current_file, node_id, nodes, connections, results_collector):
    node = nodes.get(node_id)
    if not node: return

    unique_suffix = uuid.uuid4().hex[:6]
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"proc_{node_id}_{unique_suffix}.pdf")

    print(f"--- Traitement noeud {node_id} ({node['type']}) ---")

    # --- ACTION : SPLIT (DIVISER) ---
    if node['type'] == 'split':
        split_page = int(node['params'].get('splitPage', 1))
        try:
            reader = PdfReader(current_file)
            total = len(reader.pages)
            split_page = max(1, min(split_page, total))

            # Partie 1
            p1 = output_path.replace('.pdf', '_p1.pdf')
            w1 = PdfWriter()
            for i in range(split_page): w1.add_page(reader.pages[i])
            with open(p1, 'wb') as f:
                w1.write(f)

            # Partie 2
            p2 = output_path.replace('.pdf', '_p2.pdf')
            w2 = PdfWriter()
            for i in range(split_page, total): w2.add_page(reader.pages[i])
            with open(p2, 'wb') as f:
                w2.write(f)

            # Routage
            has_child = False
            for conn in connections:
                if conn['source'] == node_id:
                    has_child = True
                    if conn['sourceHandle'] == 'output_1':  # Haut
                        process_graph_node(p1, conn['target'], nodes, connections, results_collector)
                    elif conn['sourceHandle'] == 'output_2':  # Bas
                        process_graph_node(p2, conn['target'], nodes, connections, results_collector)

            if not has_child:
                results_collector.append((p1, f"split_haut_{unique_suffix}.pdf"))
                results_collector.append((p2, f"split_bas_{unique_suffix}.pdf"))

        except Exception as e:
            print(f"Erreur Split: {e}")
            traceback.print_exc()
        return

    # --- ACTIONS STANDARDS ---
    try:
        reader = PdfReader(current_file)
        writer = PdfWriter()

        if node['type'] == 'rotate':
            angle = int(node['params'].get('angle', 90))
            for page in reader.pages:
                page.rotate(angle)
                writer.add_page(page)
            with open(output_path, 'wb') as f:
                writer.write(f)

        elif node['type'] == 'protect':
            pwd = node['params'].get('password', '1234')
            for page in reader.pages: writer.add_page(page)
            writer.encrypt(pwd)
            with open(output_path, 'wb') as f:
                writer.write(f)

        # --- ACTION : SIGNATURE (NOUVEAU) ---
        elif node['type'] == 'sign':
            # Récupération du Base64 de l'image
            file_data = node['params'].get('fileData')
            position = node['params'].get('position', 'bottom-right')

            if file_data and ',' in file_data:
                # 1. Sauvegarde temp de l'image
                header, encoded = file_data.split(",", 1)
                data = base64.b64decode(encoded)
                sig_img_path = output_path + "_sig.png"
                with open(sig_img_path, "wb") as f:
                    f.write(data)

                # 2. Application
                img_obj = ImageReader(sig_img_path)

                for i, page in enumerate(reader.pages):
                    # On signe la dernière page seulement (comportement classique)
                    if i == len(reader.pages) - 1:
                        w, h = float(page.mediabox.width), float(page.mediabox.height)
                        ov_path = output_path + "_overlay.pdf"
                        c = canvas.Canvas(ov_path, pagesize=(w, h))

                        # Taille signature (fixe 20% largeur page)
                        sig_w = w * 0.20
                        aspect = img_obj.getSize()[1] / img_obj.getSize()[0]
                        sig_h = sig_w * aspect
                        margin = 30

                        if position == 'bottom-left':
                            x, y = margin, margin
                        elif position == 'bottom-center':
                            x, y = (w - sig_w) / 2, margin
                        else:
                            x, y = w - margin - sig_w, margin  # bottom-right

                        c.drawImage(img_obj, x, y, width=sig_w, height=sig_h, mask='auto')
                        c.save()

                        ov_reader = PdfReader(ov_path)
                        page.merge_page(ov_reader.pages[0])
                        if os.path.exists(ov_path): os.remove(ov_path)

                    writer.add_page(page)

                if os.path.exists(sig_img_path): os.remove(sig_img_path)
            else:
                # Pas d'image fournie, on copie juste
                for p in reader.pages: writer.add_page(p)

            with open(output_path, 'wb') as f:
                writer.write(f)

        elif node['type'] == 'watermark':
            txt = node['params'].get('text', 'COPY')
            if len(reader.pages) > 0:
                p = reader.pages[0]
                wm_path = output_path + "_wm.pdf"
                create_text_watermark(txt, wm_path, float(p.mediabox.width), float(p.mediabox.height))
                wm_reader = PdfReader(wm_path)
                wm_page = wm_reader.pages[0]
                for page in reader.pages:
                    page.merge_page(wm_page)
                    writer.add_page(page)
                if os.path.exists(wm_path): os.remove(wm_path)
            else:
                for p in reader.pages: writer.add_page(p)
            with open(output_path, 'wb') as f:
                writer.write(f)

        elif node['type'] == 'pdf-to-docx':
            docx = output_path.replace('.pdf', '.docx')
            cv = Converter(current_file)
            cv.convert(docx, start=0, end=None)
            cv.close()
            output_path = docx

        else:
            # Passe-plat
            for p in reader.pages: writer.add_page(p)
            with open(output_path, 'wb') as f:
                writer.write(f)

    except Exception as e:
        print(f"Erreur Action {node['type']}: {e}")
        traceback.print_exc()
        return

    # Suite du graphe
    next_conns = [c for c in connections if c['source'] == node_id]
    if not next_conns:
        ext = '.docx' if 'docx' in output_path else '.pdf'
        fname = f"result_{node['type']}_{unique_suffix}{ext}"
        results_collector.append((output_path, fname))
    else:
        for conn in next_conns:
            process_graph_node(output_path, conn['target'], nodes, connections, results_collector)


@app.route('/api/pipeline_drawflow', methods=['POST'])
def pipeline_drawflow_exec():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Fichier manquant'}), 400

        print("Reception requête Drawflow...")
        raw_json = request.form.get('drawflow_data')
        if not raw_json: return jsonify({'error': 'JSON manquant'}), 400

        data = json.loads(raw_json)
        nodes_raw = data['drawflow']['Home']['data']

        nodes_dict = {}
        edges_list = []
        all_targets = set()

        for nid_str, n_data in nodes_raw.items():
            nid = int(nid_str)
            nodes_dict[nid] = {'type': n_data['name'], 'params': n_data.get('data', {})}

            for out_name, out_data in n_data.get('outputs', {}).items():
                for conn in out_data.get('connections', []):
                    edges_list.append({
                        'source': nid,
                        'target': int(conn['node']),
                        'sourceHandle': out_name  # "output_1" ou "output_2"
                    })
                    all_targets.add(int(conn['node']))

        # Sauvegarde Source
        file = request.files['file']
        root_path = os.path.join(app.config['UPLOAD_FOLDER'], f"root_{uuid.uuid4().hex}.pdf")
        file.save(root_path)

        start_nodes = [nid for nid in nodes_dict.keys() if nid not in all_targets]
        if not start_nodes: return jsonify({'error': 'Reliez au moins un bloc !'}), 400

        results = []
        for start_id in start_nodes:
            process_graph_node(root_path, start_id, nodes_dict, edges_list, results)

        if not results:
            return jsonify({'error': 'Aucun résultat généré.'}), 500

        zip_name = f"Resultats_{uuid.uuid4().hex[:6]}.zip"
        zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_name)

        with zipfile.ZipFile(zip_path, 'w') as z:
            for path, name in results:
                if os.path.exists(path): z.write(path, name)

        return jsonify({'success': True, 'filename': zip_name, 'downloadName': 'Pipeline_Result.zip'})

    except Exception as e:
        print("ERREUR FATALE:")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/pipeline_graph', methods=['POST'])
def pipeline_graph_exec():
    if 'file' not in request.files:
        return jsonify({'error': 'Fichier manquant'}), 400

    # Récupération des données du graphe
    graph_data = json.loads(request.form.get('graph'))
    nodes_list = graph_data.get('nodes', [])  # Liste [{id, type, data: {params...}}]
    edges_list = graph_data.get('edges', [])  # Liste [{source, target, sourceHandle}]

    # Transformation en dictionnaire pour accès rapide par ID
    nodes_dict = {n['id']: {'type': n['type'], 'params': n['data']} for n in nodes_list}

    # Sauvegarde du fichier source (Racine)
    file = request.files['file']
    root_filename = f"root_{uuid.uuid4().hex}.pdf"
    root_path = os.path.join(app.config['UPLOAD_FOLDER'], root_filename)
    file.save(root_path)

    final_results = []  # Liste [(filepath, filename_for_zip)]

    # Trouver le(s) nœud(s) de départ (ceux qui n'ont pas de source dans edges)
    # Dans notre UI, l'utilisateur relie le bloc "START" (virtuel ou premier drop)
    # Pour simplifier : on cherche les nœuds qui ne sont "target" d'aucun lien
    targets = set(e['target'] for e in edges_list)
    start_nodes = [nid for nid in nodes_dict.keys() if nid not in targets]

    if not start_nodes:
        return jsonify({'error': 'Aucun point de départ trouvé (cycle ?)'}), 400

    # Lancer le traitement pour chaque branche racine
    for start_id in start_nodes:
        process_graph_node(root_path, start_id, nodes_dict, edges_list, final_results)

    # Création du ZIP final
    zip_name = f"Workflow_Result_{uuid.uuid4().hex[:6]}.zip"
    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], zip_name)

    with zipfile.ZipFile(zip_path, 'w') as z:
        for fpath, fname in final_results:
            if os.path.exists(fpath):
                z.write(fpath, fname)

    return jsonify({
        'success': True,
        'filename': zip_name,
        'downloadName': 'Resultats_Workflow.zip'
    })


def process_pipeline_step(action, input_path, output_path):
    action_type = action.get('type')

    # --- CAS 1 : PDF VERS JPEG (ZIP) ---
    if action_type == 'pdf2jpeg':
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(input_path, dpi=150, fmt='jpeg')
            with zipfile.ZipFile(output_path, 'w') as zipf:
                for i, image in enumerate(images, 1):
                    img_buffer = io.BytesIO()
                    image.save(img_buffer, format='JPEG', quality=85)
                    img_buffer.seek(0)
                    zipf.writestr(f"page_{i:03d}.jpg", img_buffer.read())
            return
        except ImportError:
            raise Exception("Module pdf2image manquant")

    # Lecture PDF standard pour les autres actions
    try:
        reader = PdfReader(input_path)
    except:
        raise Exception("Impossible de lire le fichier (ce n'est pas un PDF valide).")

    # --- CAS 2 : DIVISER (SPLIT) -> ZIP ---
    if action_type == 'split':
        split_page = int(action.get('splitPage', 1))
        total_pages = len(reader.pages)

        # Sécurité index
        if split_page < 1: split_page = 1
        if split_page >= total_pages: split_page = total_pages - 1

        writer1 = PdfWriter()
        writer2 = PdfWriter()

        # Partie 1
        for i in range(split_page):
            writer1.add_page(reader.pages[i])

        # Partie 2
        for i in range(split_page, total_pages):
            writer2.add_page(reader.pages[i])

        # On crée les fichiers temporaires pour les zipperr
        ts = datetime.now().strftime('%f')
        p1_path = os.path.join(app.config['UPLOAD_FOLDER'], f"split_p1_{ts}.pdf")
        p2_path = os.path.join(app.config['UPLOAD_FOLDER'], f"split_p2_{ts}.pdf")

        with open(p1_path, "wb") as f1:
            writer1.write(f1)
        with open(p2_path, "wb") as f2:
            writer2.write(f2)

        # Création du ZIP final
        with zipfile.ZipFile(output_path, 'w') as zipf:
            zipf.write(p1_path, "partie_1.pdf")
            zipf.write(p2_path, "partie_2.pdf")

        # Nettoyage
        try:
            os.remove(p1_path)
            os.remove(p2_path)
        except:
            pass
        return

    # --- CAS AUTRES (Un seul PDF en sortie) ---
    writer = PdfWriter()

    if action_type == 'rotate':
        angle = int(action.get('angle', 90))
        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)

    elif action_type == 'watermark':
        text = action.get('text', 'CONFIDENTIEL')
        if len(reader.pages) > 0:
            p = reader.pages[0]
            wm_path = input_path + "_wm.pdf"
            create_text_watermark(text, wm_path, float(p.mediabox.width), float(p.mediabox.height))
            wm_reader = PdfReader(wm_path)
            wm_page = wm_reader.pages[0]
            for page in reader.pages:
                page.merge_page(wm_page)
                writer.add_page(page)
            if os.path.exists(wm_path): os.remove(wm_path)
        else:
            for p in reader.pages: writer.add_page(p)

    elif action_type == 'signature':
        img_data = action.get('fileData', '')
        pos = action.get('position', 'bottom-right')
        if img_data and ',' in img_data:
            try:
                img_bytes = base64.b64decode(img_data.split(',')[1])
                ts = datetime.now().strftime('%f')
                sig_path = os.path.join(app.config['UPLOAD_FOLDER'], f"sig_{ts}.png")
                with open(sig_path, "wb") as f:
                    f.write(img_bytes)

                img_obj = ImageReader(sig_path)
                total_pages = len(reader.pages)

                for i, page in enumerate(reader.pages):
                    if i == total_pages - 1:
                        w, h = float(page.mediabox.width), float(page.mediabox.height)
                        ov_path = sig_path + ".pdf"
                        c = canvas.Canvas(ov_path, pagesize=(w, h))
                        tw = w * 0.20
                        aspect = img_obj.getSize()[1] / img_obj.getSize()[0]
                        th = tw * aspect
                        margin = 30

                        if pos == 'bottom-right':
                            x, y = w - margin - tw, margin
                        elif pos == 'bottom-left':
                            x, y = margin, margin
                        else:
                            x, y = w - margin - tw, margin

                        c.drawImage(img_obj, x, y, width=tw, height=th, mask='auto')
                        c.save()

                        ov_reader = PdfReader(ov_path)
                        page.merge_page(ov_reader.pages[0])
                        if os.path.exists(ov_path): os.remove(ov_path)
                    writer.add_page(page)
                if os.path.exists(sig_path): os.remove(sig_path)
            except:
                for p in reader.pages: writer.add_page(p)
        else:
            for p in reader.pages: writer.add_page(p)
    else:
        # Copie par défaut
        for p in reader.pages: writer.add_page(p)

    with open(output_path, 'wb') as f:
        writer.write(f)
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
    if 'pdf' not in request.files or 'signature' not in request.files:
        return jsonify({'error': 'PDF et image de signature requis'}), 400

    pdf_file = request.files['pdf']
    sig_file = request.files['signature']
    position = request.form.get('position', 'bottom-right')
    target_page_str = request.form.get('targetPage', 'last')

    # Coordonnées/échelle optionnelles
    pos_x_raw = request.form.get('posX')
    pos_y_raw = request.form.get('posY')
    sig_scale_raw = request.form.get('sigScale', '25')
    try:
        pos_x_pct = float(pos_x_raw) if pos_x_raw is not None else None
        pos_y_pct = float(pos_y_raw) if pos_y_raw is not None else None
        sig_scale_pct = float(sig_scale_raw)
    except ValueError:
        return jsonify({'error': 'Coordonnées ou taille invalides'}), 400

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
        img = ImageReader(sig_path)
        total_pages = len(reader.pages)

        # Déterminer quelles pages signer
        if target_page_str == 'all':
            pages_to_sign = set(range(total_pages))
        elif target_page_str == 'last':
            pages_to_sign = {total_pages - 1}
        else:
            # Page spécifique (1-indexed vers 0-indexed)
            try:
                page_num = int(target_page_str) - 1
                if 0 <= page_num < total_pages:
                    pages_to_sign = {page_num}
                else:
                    pages_to_sign = {total_pages - 1}
            except ValueError:
                pages_to_sign = {total_pages - 1}

        for i, page in enumerate(reader.pages):
            if i in pages_to_sign:
                w = float(page.mediabox.width)
                h = float(page.mediabox.height)

                overlay_path = os.path.join(app.config['UPLOAD_FOLDER'], f"overlay_{ts}_{i}_{os.urandom(4).hex()}.pdf")
                c = canvas.Canvas(overlay_path, pagesize=(w, h))

                target_width = max(20.0, min(w, (sig_scale_pct / 100.0) * w))
                iw, ih = img.getSize()
                aspect = ih / iw
                target_height = target_width * aspect

                margin = 36.0

                if pos_x_pct is not None and pos_y_pct is not None:
                    x = (pos_x_pct / 100.0) * w
                    y = (pos_y_pct / 100.0) * h
                    x = max(0.0, min(w - target_width, x))
                    y = max(0.0, min(h - target_height, y))
                else:
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

                overlay_reader = PdfReader(overlay_path)
                overlay_page = overlay_reader.pages[0]
                page.merge_page(overlay_page)

                try:
                    os.remove(overlay_path)
                except Exception:
                    pass

            writer.add_page(page)

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
        import traceback
        traceback.print_exc()
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


@app.route('/api/protect', methods=['POST'])
def protect_action():
    """Protège un PDF par mot de passe et renvoie le fichier sécurisé."""
    data = request.json or {}
    filename = data.get('file')
    password = (data.get('password') or '')
    confirm_password = (data.get('confirmPassword') or '')
    output_name = (data.get('outputName') or '')

    if not filename:
        return jsonify({'error': 'Aucun fichier PDF fourni'}), 400
    if not password:
        return jsonify({'error': 'Mot de passe manquant'}), 400
    if password != confirm_password:
        return jsonify({'error': 'Les mots de passe ne correspondent pas'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Le mot de passe doit contenir au moins 8 caractères'}), 400
    if len(password) > 50:
        return jsonify({'error': 'Le mot de passe ne doit pas contenir plus de 50 caractères'}), 400

    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'Fichier introuvable'}), 404

    base_name = secure_filename(output_name) or 'document_protege'
    download_name = base_name if base_name.lower().endswith('.pdf') else f"{base_name}.pdf"

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    internal_filename = f"{os.path.splitext(download_name)[0]}_{timestamp}.pdf"
    internal_path = os.path.join(app.config['UPLOAD_FOLDER'], internal_filename)

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

       
        # Chiffrement 128 bits pour une protection standard et compatible
        writer.encrypt(password)

        with open(internal_path, "wb") as f:
            writer.write(f)
    except Exception as e:
        return jsonify({'error': f'Protection impossible: {e}'}), 500

    return jsonify({
        'success': True,
        'filename': internal_filename,
        'downloadName': download_name
    })

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
        # Diagnostic log: print received parameters to server console for debugging
        try:
            print(f"[DEBUG capture_region] page={page_num}, x={x_pos}, y={y_pos}, width={region_width}, height={region_height}, display_scale={display_scale}")
            # also print the raw form for completeness
            print(f"[DEBUG form] {dict(request.form)}")
        except Exception:
            pass
        
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

@app.route('/api/img_to_pdf', methods=['POST'])
def img_to_pdf_action():
    """Convert an image (PNG, JPG) to PDF."""
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    if not file or not allowed_image(file.filename):
        return jsonify({'error': 'Format image invalide (PNG, JPG requis)'}), 400

    try:
        timestamp = datetime.now().strftime('%H%M%S')
        clean_name = secure_filename(file.filename)
        
        src_path = os.path.join(app.config['UPLOAD_FOLDER'], f"src_img_{timestamp}_{clean_name}")
        file.save(src_path)
        
        output_filename = f"img_conv_{timestamp}_{os.path.splitext(clean_name)[0]}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        # Convert image to PDF using ReportLab
        img = ImageReader(src_path)
        w, h = img.getSize()
        
        c = canvas.Canvas(output_path, pagesize=(w, h))
        c.drawImage(src_path, 0, 0, width=w, height=h)
        c.save()

        return jsonify({
            'success': True,
            'filename': output_filename,
            'downloadName': os.path.splitext(clean_name)[0] + ".pdf"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f"Erreur conversion : {str(e)}"}), 500

@app.route('/api/compress', methods=['POST'])
def compress_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier PDF'}), 400

        file = request.files['file']

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Format invalide'}), 400

        input_path = tempfile.mktemp(suffix=".pdf")
        output_path = tempfile.mktemp(suffix=".pdf")

        file.save(input_path)

        reader = PdfReader(input_path)
        writer = PdfWriter()

        for page in reader.pages:
            page.compress_content_streams()
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)

        return send_file(
            output_path,
            as_attachment=True,
            download_name="compressed.pdf"
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_preview_image(pdf_bytes, page_num=0, max_size=800):
    """
    Generate a preview image of a PDF page for display in the browser
    
    Args:
        pdf_bytes: PDF file as bytes
        page_num: Page number to preview
        max_size: Maximum dimension of the preview image
    
    Returns:
        Base64 encoded image data
    """
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if page_num >= len(pdf_document):
            page_num = 0
            
        page = pdf_document[page_num]
        
        # Calculate scale to fit within max_size
        rect = page.rect
        scale_x = max_size / rect.width
        scale_y = max_size / rect.height
        scale = min(scale_x, scale_y, 1.0)  # Don't scale up beyond original
        
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Convert to base64 for web display
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        base64_img = base64.b64encode(img_bytes.read()).decode('utf-8')
        
        pdf_document.close()
        
        return f"data:image/png;base64,{base64_img}"
        
    except Exception as e:
        raise Exception(f"Failed to generate preview: {str(e)}")

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5000)