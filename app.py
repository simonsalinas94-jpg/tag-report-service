import csv
import io
import os
import base64
from collections import defaultdict
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_RIGHT

app = Flask(__name__)
CORS(app)

CONCESIONARIA_MAP = {'CN': 'Costanera Norte', 'NOR': 'Autopista Nororiente'}

# Colors
DARK     = colors.HexColor('#0b0f1a')
TEAL     = colors.HexColor('#00e5c3')
LIGHT_BG = colors.HexColor('#f4f6f9')
MID      = colors.HexColor('#6b7a99')
WHITE    = colors.white
BORDER   = colors.HexColor('#dde3ed')

def parse_csv(content_bytes):
    text = content_bytes.decode('ISO-8859-1')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    return list(reader)

def generate_pdf(all_rows, fechas_visita, semana):
    # Filter by visit dates
    rows = [r for r in all_rows if r['Fecha'].strip() in fechas_visita]
    if not rows:
        return None, "No hay transacciones para las fechas indicadas"

    by_date = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_date[r['Fecha'].strip()][r['NombreCorto'].strip()].append({
            'hora': r['Hora'].strip(),
            'punto': r['PuntoCobro'].strip(),
            'importe': int(r['Importe'].strip())
        })

    total_general = sum(int(r['Importe']) for r in rows)
    total_by_conc = defaultdict(int)
    for r in rows:
        total_by_conc[r['NombreCorto'].strip()] += int(r['Importe'])

    dates_sorted = sorted(by_date.keys(), key=lambda d: datetime.strptime(d, '%d-%m-%Y'))
    patente = rows[0]['Patente'].strip()
    tag_num = rows[0]['TAG'].strip()

    # Styles
    label_s   = ParagraphStyle('l',  fontSize=8,  fontName='Helvetica-Bold', textColor=MID)
    value_s   = ParagraphStyle('v',  fontSize=13, fontName='Helvetica-Bold', textColor=DARK)
    title_s   = ParagraphStyle('t',  fontSize=17, fontName='Helvetica-Bold', textColor=DARK, spaceAfter=3)
    sub_s     = ParagraphStyle('sb', fontSize=9,  fontName='Helvetica',      textColor=MID,  spaceAfter=2)
    section_s = ParagraphStyle('sc', fontSize=11, fontName='Helvetica-Bold', textColor=DARK, spaceBefore=12, spaceAfter=5)
    small_s   = ParagraphStyle('sm', fontSize=8,  fontName='Helvetica',      textColor=MID)
    teal_s    = ParagraphStyle('tl', fontSize=15, fontName='Helvetica-Bold', textColor=TEAL)
    head_s    = ParagraphStyle('h',  fontSize=9,  fontName='Helvetica-Bold', textColor=WHITE)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    story = []

    # Header
    story.append(Paragraph('Comprobante de Gastos TAG', title_s))
    story.append(Paragraph('Visitas a Centros de Datos · Amazon Web Services Chile', sub_s))
    story.append(Paragraph(f'Semana: {semana}', sub_s))
    story.append(Paragraph(f'Días de visita: {", ".join(dates_sorted)}', sub_s))
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width='100%', thickness=2, color=TEAL, spaceAfter=10))

    # Summary
    summary_data = [
        [Paragraph('<b>PATENTE</b>', label_s), Paragraph('<b>TAG N°</b>', label_s),
         Paragraph('<b>TOTAL SEMANA</b>', label_s), Paragraph('<b>VIAJES</b>', label_s),
         Paragraph('<b>DÍAS</b>', label_s)],
        [Paragraph(patente, value_s),
         Paragraph(tag_num[:10], ParagraphStyle('v2', fontSize=10, fontName='Helvetica-Bold', textColor=DARK)),
         Paragraph(f'${total_general:,.0f}'.replace(',','.'), teal_s),
         Paragraph(str(len(rows)), value_s),
         Paragraph(str(len(dates_sorted)), value_s)],
    ]
    st = Table(summary_data, colWidths=[3*cm, 4*cm, 4.2*cm, 2.2*cm, 2.2*cm])
    st.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT_BG),
        ('BACKGROUND', (2,0), (2,1), colors.HexColor('#e8fdf9')),
        ('BOX', (0,0), (-1,-1), 1, BORDER),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 8), ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10), ('LINEABOVE', (2,0), (2,1), 2, TEAL),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.4*cm))

    # By concesionaria
    story.append(Paragraph('Resumen por Concesionaria', section_s))
    conc_data = [['Concesionaria', 'Código', 'Transacciones', 'Total ($)']]
    for code, total in sorted(total_by_conc.items()):
        count = sum(1 for r in rows if r['NombreCorto'].strip() == code)
        conc_data.append([CONCESIONARIA_MAP.get(code, code), code, str(count),
                          f'${total:,.0f}'.replace(',','.')])
    conc_data.append(['', '', 'TOTAL SEMANA', f'${total_general:,.0f}'.replace(',','.')])
    ct = Table(conc_data, colWidths=[6*cm, 2.5*cm, 4*cm, 5*cm])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), DARK), ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#e8fdf9')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'), ('TEXTCOLOR', (3,-1), (3,-1), TEAL),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [WHITE, LIGHT_BG]),
        ('BOX', (0,0), (-1,-1), 1, BORDER), ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 7), ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('ALIGN', (2,0), (-1,-1), 'CENTER'), ('ALIGN', (3,0), (3,-1), 'RIGHT'),
    ]))
    story.append(ct)
    story.append(Spacer(1, 0.4*cm))

    # Detail
    story.append(Paragraph('Detalle de Transacciones por Día de Visita', section_s))
    detail_data = [['Fecha', 'Hora', 'Concesionaria', 'Punto de Cobro', 'Importe ($)']]
    for fecha in dates_sorted:
        day_total = 0
        first = True
        for conc_code, txns in sorted(by_date[fecha].items()):
            for t in sorted(txns, key=lambda x: x['hora']):
                detail_data.append([fecha if first else '', t['hora'],
                    CONCESIONARIA_MAP.get(conc_code, conc_code), t['punto'],
                    f"${t['importe']:,.0f}".replace(',','.')])
                day_total += t['importe']
                first = False
        detail_data.append(['', '', '', f'Subtotal {fecha}',
                            f"${day_total:,.0f}".replace(',','.')])

    dt = Table(detail_data, colWidths=[2.5*cm, 1.8*cm, 4.5*cm, 3.5*cm, 3.2*cm], repeatRows=1)
    dts = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), DARK), ('TEXTCOLOR', (0,0), (-1,0), WHITE),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOX', (0,0), (-1,-1), 1, BORDER), ('INNERGRID', (0,0), (-1,-1), 0.3, BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8), ('ALIGN', (4,0), (4,-1), 'RIGHT'),
    ])
    for i, row in enumerate(detail_data[1:], 1):
        if row[3].startswith('Subtotal'):
            dts.add('BACKGROUND', (0,i), (-1,i), colors.HexColor('#f0fdf9'))
            dts.add('FONTNAME', (0,i), (-1,i), 'Helvetica-Bold')
            dts.add('TEXTCOLOR', (4,i), (4,i), TEAL)
            dts.add('LINEABOVE', (0,i), (-1,i), 0.5, TEAL)
        elif i % 2 == 0:
            dts.add('BACKGROUND', (0,i), (-1,i), LIGHT_BG)
    dt.setStyle(dts)
    story.append(dt)
    story.append(Spacer(1, 0.4*cm))

    # Reimbursement line
    story.append(HRFlowable(width='100%', thickness=1, color=BORDER, spaceAfter=8))
    story.append(Paragraph('Para ingresar en reporte semanal AWS:',
        ParagraphStyle('rl', fontSize=9, fontName='Helvetica-Bold', textColor=MID, spaceAfter=4)))
    reemb_data = [
        [Paragraph('<b>Categoría</b>', head_s), Paragraph('<b>Descripción</b>', head_s),
         Paragraph('<b>Período</b>', head_s), Paragraph('<b>Monto</b>', head_s)],
        [Paragraph('TAG / Peajes', small_s),
         Paragraph(f'Visitas a Data Centers AWS · Patente {patente}', small_s),
         Paragraph(semana, small_s),
         Paragraph(f'<b>${total_general:,.0f}</b>'.replace(',','.'),
                   ParagraphStyle('rm', fontSize=11, fontName='Helvetica-Bold', textColor=TEAL))],
    ]
    rt = Table(reemb_data, colWidths=[3.5*cm, 6.5*cm, 3.5*cm, 4*cm])
    rt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), DARK),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#f0fdf9')),
        ('BOX', (0,0), (-1,-1), 1.5, TEAL),
        ('INNERGRID', (0,0), (-1,-1), 0.5, BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 9), ('BOTTOMPADDING', (0,0), (-1,-1), 9),
        ('LEFTPADDING', (0,0), (-1,-1), 10), ('ALIGN', (3,0), (3,-1), 'RIGHT'),
    ]))
    story.append(rt)

    # Footer
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=BORDER, spaceAfter=6))
    footer_data = [[
        Paragraph(f'Generado automáticamente · {datetime.now().strftime("%d/%m/%Y %H:%M")}', small_s),
        Paragraph('Adjuntar como comprobante en línea TAG del reporte semanal',
                  ParagraphStyle('fr', fontSize=8, fontName='Helvetica', textColor=MID, alignment=TA_RIGHT))
    ]]
    ft = Table(footer_data, colWidths=[9*cm, 8.5*cm])
    ft.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    story.append(ft)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    return pdf_bytes, None


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/generar-reporte', methods=['POST'])
def generar_reporte():
    """
    Expects multipart/form-data with:
    - csv_files: one or more CSV files
    - fechas_visita: comma-separated dates e.g. "09-03-2026,12-03-2026"
    - semana: e.g. "09/03/2026 - 13/03/2026"
    """
    try:
        # Get parameters
        fechas_str = request.form.get('fechas_visita', '')
        semana = request.form.get('semana', '')

        if not fechas_str or not semana:
            return jsonify({'error': 'Faltan parámetros: fechas_visita y semana son requeridos'}), 400

        fechas_visita = [f.strip() for f in fechas_str.split(',')]

        # Read all CSV files
        all_rows = []
        files = request.files.getlist('csv_files')
        if not files:
            return jsonify({'error': 'No se recibieron archivos CSV'}), 400

        for f in files:
            rows = parse_csv(f.read())
            all_rows.extend(rows)

        # Generate PDF
        pdf_bytes, error = generate_pdf(all_rows, fechas_visita, semana)
        if error:
            return jsonify({'error': error}), 400

        # Return as base64 for Make.com
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        total = sum(int(r['Importe']) for r in all_rows if r['Fecha'].strip() in fechas_visita)

        return jsonify({
            'success': True,
            'pdf_base64': pdf_b64,
            'total': total,
            'total_formateado': f'${total:,.0f}'.replace(',','.'),
            'semana': semana,
            'fechas_visita': fechas_visita,
            'filename': f'TAG_AWS_{semana.replace("/","").replace(" ","").replace("-","_")}.pdf'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analizar-propiedad', methods=['POST'])
def analizar_propiedad():
    try:
        import anthropic
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        direccion   = data.get('direccion', '')
        ciudad      = data.get('ciudad', '')
        operacion   = data.get('operacion', 'flipping')
        precio      = data.get('precio', '')
        superficie  = data.get('superficie', '')
        dormitorios = data.get('dormitorios', '')
        antiguedad  = data.get('antiguedad', '')
        observaciones = data.get('observaciones', '')

        if not direccion:
            return jsonify({'error': 'La dirección es requerida'}), 400

        precio_ufm2 = ''
        if precio and superficie:
            try:
                precio_ufm2 = f"{float(precio)/float(superficie):.1f} UF/m²"
            except:
                pass

        prompt = f"""Eres un experto en inversión inmobiliaria en Chile, especializado en análisis de riesgo para flipping y compra de departamentos en Santiago, Viña del Mar y Concón.

Analiza esta propiedad para BTS Investments:

DATOS DE LA PROPIEDAD:
- Dirección: {direccion}
- Ciudad/Zona: {ciudad}
- Operación objetivo: {operacion}
- Precio pedido: {precio + ' UF' if precio else 'no especificado'}
- Superficie: {superficie + ' m²' if superficie else 'no especificada'}
- Precio UF/m²: {precio_ufm2 or 'no calculable'}
- Dormitorios: {dormitorios}
- Antigüedad: {antiguedad}
- Observaciones del evaluador: {observaciones or 'ninguna'}

Investiga y analiza los siguientes factores usando tu conocimiento del mercado chileno:

1. PRECIO VS MERCADO: ¿El precio UF/m² está sobre, bajo o en línea con el sector? ¿Cuál es el rango típico en esa zona?
2. STOCK SIN VENDER: ¿Hay señales de sobreoferta en el edificio o zona? ¿Proyectos con muchas unidades disponibles hace tiempo?
3. ENTORNO Y SEGURIDAD: ¿Cómo es la percepción de seguridad del sector? ¿Hay reportes de delincuencia o problemas sociales?
4. CONECTIVIDAD Y TRANSPORTE: ¿Acceso a metro, buses, autopistas? ¿Distancia a servicios clave?
5. PROYECTOS NUEVOS EN LA ZONA: ¿Hay nuevos desarrollos que podrían competir o que indiquen crecimiento del sector?
6. FACTORES OCULTOS: ¿Qué cosas que no se ven en fotos podrían afectar negativamente la venta? (ruido, obras, industrias cercanas, inundaciones históricas, estigma del sector)

Responde EXACTAMENTE en este formato:

SCORE: [VERDE / AMARILLO / ROJO]

PRECIO VS MERCADO:
[análisis de 2-3 líneas]

STOCK SIN VENDER:
[análisis de 2-3 líneas]

ENTORNO Y SEGURIDAD:
[análisis de 2-3 líneas]

CONECTIVIDAD Y TRANSPORTE:
[análisis de 2-3 líneas]

PROYECTOS NUEVOS EN LA ZONA:
[análisis de 2-3 líneas]

FACTORES OCULTOS:
[análisis de 2-3 líneas]

RECOMENDACIÓN:
[1 párrafo con recomendación clara: Proceder / Investigar más / Descartar, con justificación]

ALERTAS CLAVE:
[lista de 3-5 puntos concretos que BTS debe verificar antes de decidir]"""

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1500,
            messages=[{'role': 'user', 'content': prompt}]
        )

        result_text = message.content[0].text
        score_match = result_text.upper().find('SCORE:')
        score = 'AMARILLO'
        if score_match != -1:
            snippet = result_text[score_match:score_match+20].upper()
            if 'VERDE' in snippet:
                score = 'VERDE'
            elif 'ROJO' in snippet:
                score = 'ROJO'

        return jsonify({
            'success': True,
            'analysis': result_text,
            'score': score,
            'direccion': direccion,
            'ciudad': ciudad
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/evento-agente', methods=['POST'])
def evento_agente():
    try:
        import anthropic
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        system = data.get('system', '')
        messages = data.get('messages', [])

        if not messages:
            return jsonify({'error': 'No se recibieron mensajes'}), 400

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=4000,
            system=system,
            messages=messages
        )

        response_text = message.content[0].text
        return jsonify({'success': True, 'response': response_text})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/buscar-propiedades', methods=['POST'])
def buscar_propiedades():
    try:
        import requests as req
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        ciudad = data.get('ciudad', 'Santiago')
        precio_max_uf = float(data.get('precioMax', 5000))
        precio_min_uf = float(data.get('precioMin', 0))
        sup_min = float(data.get('supMin', 0))
        dorms = int(data.get('dorms', 0))

        UF_VALUE = 38500

        # Get Meli credentials
        app_id = os.environ.get('MELI_APP_ID')
        secret_key = os.environ.get('MELI_SECRET_KEY')
        if not app_id or not secret_key:
            return jsonify({'error': 'Credenciales de Mercado Libre no configuradas'}), 500

        # Get access token
        token_resp = req.post(
            'https://api.mercadolibre.com/oauth/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={'grant_type': 'client_credentials', 'client_id': app_id, 'client_secret': secret_key},
            timeout=10
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get('access_token')
        if not access_token:
            return jsonify({'error': 'No se pudo obtener token de Mercado Libre'}), 500

        headers = {'Authorization': f'Bearer {access_token}', 'User-Agent': 'Mozilla/5.0'}

        # Use text search - more reliable for Chilean real estate
        dorms_text = f' {dorms} dormitorios' if dorms > 0 else ''
        query = f'departamento venta{dorms_text} {ciudad}'
        encoded_query = req.utils.quote(query)
        url = f'https://api.mercadolibre.com/sites/MLC/search?q={encoded_query}&limit=50&sort=date_desc'

        search_resp = req.get(url, headers=headers, timeout=15)
        search_resp.raise_for_status()
        results = search_resp.json().get('results', [])

        props = []
        for item in results:
            price = item.get('price', 0)
            currency = item.get('currency_id', 'CLP')
            if not price:
                continue

            # Convert to UF
            if currency == 'UF':
                price_uf = price
            else:
                price_uf = price / UF_VALUE

            # Filter by price range
            if precio_max_uf > 0 and price_uf > precio_max_uf:
                continue
            if precio_min_uf > 0 and price_uf < precio_min_uf:
                continue

            superficie = 0
            dormitorios = 0
            bathrooms = 0

            for attr in item.get('attributes', []):
                aid = attr.get('id', '')
                val = attr.get('value_name', '') or ''
                if aid in ('TOTAL_AREA', 'COVERED_AREA'):
                    try:
                        v = float(val.replace('m²','').replace(',','.').strip())
                        if v > superficie: superficie = v
                    except: pass
                elif aid == 'BEDROOMS':
                    try: dormitorios = int(val)
                    except: pass
                elif aid == 'BATHROOMS':
                    try: bathrooms = int(val)
                    except: pass

            if sup_min > 0 and superficie > 0 and superficie < sup_min:
                continue

            ufm2 = round(price_uf / superficie, 2) if superficie > 0 else 0

            dias = 0
            date_created = item.get('date_created', '')
            if date_created:
                try:
                    from datetime import timezone
                    created = datetime.fromisoformat(date_created.replace('Z', '+00:00'))
                    dias = (datetime.now(timezone.utc) - created).days
                except: pass

            address = item.get('address', {})
            city_name = address.get('city_name', '') or address.get('state_name', '') or ciudad

            props.append({
                'id': item.get('id', ''),
                'titulo': item.get('title', ''),
                'precio': round(price_uf, 1),
                'moneda': currency,
                'superficie': superficie,
                'dormitorios': dormitorios,
                'bathrooms': bathrooms,
                'ufm2': ufm2,
                'diasPublicado': dias,
                'ciudad': city_name,
                'url': item.get('permalink', ''),
                'thumbnail': item.get('thumbnail', '')
            })

        return jsonify({'success': True, 'results': props, 'total': len(props)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/buscar-oportunidades', methods=['POST'])
def buscar_oportunidades():
    try:
        import anthropic
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        ciudad = data.get('ciudad', 'Santiago')
        precio_max = data.get('precioMax', '5000')
        precio_min = data.get('precioMin', '1000')
        dorms = data.get('dorms', '2')
        sup_min = data.get('supMin', '40')
        comuna = data.get('comuna', '')

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500

        location = f'{comuna}, {ciudad}' if comuna else ciudad

        prompt = f"""Eres un experto en inversión inmobiliaria en Chile para BTS Investments.

Busca en Portal Inmobiliario Chile (portalinmobiliario.com), Toctoc.com y Mercado Libre inmuebles Chile los 3 departamentos en venta más interesantes como oportunidades de flipping en {location} con estos criterios:
- Precio: {precio_min} a {precio_max} UF
- Dormitorios mínimo: {dorms}
- Superficie mínima: {sup_min} m²

Prioriza propiedades con:
1. Precio por m² bajo el promedio de la zona
2. Tiempo prolongado en el mercado

Para cada propiedad entrega un análisis conciso. Responde SOLO con este JSON sin texto adicional:

{{
  "ciudad": "{location}",
  "promedioUFm2Zona": "XX.X",
  "propiedades": [
    {{
      "ranking": 1,
      "score": 8.0,
      "titulo": "Departamento en ...",
      "direccion": "Calle X, Comuna Y",
      "precio_uf": 3200,
      "superficie": 65,
      "dormitorios": 2,
      "ufm2": 49.2,
      "ufm2_vs_zona": "-12% bajo mercado",
      "dias_publicado": "estimado 90+ días",
      "url": "https://...",
      "analisis": {{
        "precio_mercado": "2 líneas de análisis",
        "entorno_seguridad": "2 líneas de análisis",
        "conectividad": "2 líneas de análisis",
        "proyectos_zona": "2 líneas de análisis",
        "factores_ocultos": "2 líneas de análisis",
        "perfil_comprador": "1 línea"
      }},
      "recomendacion": "Proceder / Investigar más / Descartar con justificación en 2 líneas",
      "proximos_pasos": ["paso 1", "paso 2", "paso 3"],
      "score_breakdown": {{
        "precio_vs_mercado": 8,
        "potencial_revalorizacion": 7,
        "factores_cualitativos": 8,
        "liquidez": 7
      }}
    }}
  ],
  "recomendacion_top": "2 líneas sobre la mejor oportunidad",
  "alertas_generales": ["alerta 1", "alerta 2"]
}}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=3000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{'role': 'user', 'content': prompt}]
        )

        full_text = ''
        for block in message.content:
            if hasattr(block, 'text'):
                full_text += block.text

        import re
        import json as json_lib
        json_match = re.search(r'\{[\s\S]*\}', full_text)
        if not json_match:
            return jsonify({'error': 'No se pudo parsear la respuesta', 'raw': full_text[:500]}), 500

        result = json_lib.loads(json_match.group(0))
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/recetas', methods=['POST'])
def recetas():
    try:
        import anthropic
        import json as json_lib

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        ingredientes_texto = data.get('ingredientes', '')
        imagen_base64 = data.get('imagen_base64', '')
        imagen_tipo = data.get('imagen_tipo', 'image/jpeg')
        comida = data.get('comida', 'cualquier comida')
        comensales = int(data.get('comensales', 1))
        meal_prep = data.get('meal_prep', False)
        restricciones = data.get('restricciones', [])

        restricciones_str = ', '.join(restricciones) if restricciones else 'ninguna'
        porciones_str = f"{comensales} persona{'s' if comensales > 1 else ''}"
        if meal_prep:
            porciones_str += " + meal prep para el día siguiente"

        prompt = f"""Eres un chef y nutricionista experto. El usuario quiere cocinar {comida}.

RESTRICCIONES ALIMENTARIAS: {restricciones_str}
PORCIONES: {porciones_str}

{"El usuario tiene estos ingredientes disponibles: " + ingredientes_texto if ingredientes_texto else "Analiza la imagen para identificar los ingredientes disponibles."}

Tu tarea:
1. Identifica los ingredientes disponibles
2. Propón 3 recetas posibles, simples y saludables
3. El usuario elegirá una — por ahora presenta las 3 opciones

Responde SOLO con este JSON sin texto adicional:

{{
  "ingredientes_detectados": ["ingrediente 1", "ingrediente 2"],
  "recetas": [
    {{
      "id": 1,
      "nombre": "Nombre de la receta",
      "descripcion": "1-2 líneas atractivas",
      "tiempo_preparacion": "20 min",
      "dificultad": "Fácil",
      "calorias_por_porcion": 450,
      "proteina_g": 35,
      "carbohidratos_g": 40,
      "grasas_g": 12,
      "emoji": "🍳"
    }},
    {{
      "id": 2,
      "nombre": "Nombre de la receta",
      "descripcion": "1-2 líneas atractivas",
      "tiempo_preparacion": "15 min",
      "dificultad": "Muy fácil",
      "calorias_por_porcion": 380,
      "proteina_g": 28,
      "carbohidratos_g": 35,
      "grasas_g": 10,
      "emoji": "🥗"
    }},
    {{
      "id": 3,
      "nombre": "Nombre de la receta",
      "descripcion": "1-2 líneas atractivas",
      "tiempo_preparacion": "30 min",
      "dificultad": "Media",
      "calorias_por_porcion": 520,
      "proteina_g": 40,
      "carbohidratos_g": 45,
      "grasas_g": 15,
      "emoji": "🍲"
    }}
  ]
}}"""

        # Build message content
        if imagen_base64:
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": imagen_tipo,
                        "data": imagen_base64
                    }
                },
                {"type": "text", "text": prompt}
            ]
        else:
            content = prompt

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1500,
            messages=[{'role': 'user', 'content': content}]
        )

        full_text = message.content[0].text
        import re
        json_match = re.search(r'\{[\s\S]*\}', full_text)
        if not json_match:
            return jsonify({'error': 'No se pudo procesar la respuesta'}), 500

        result = json_lib.loads(json_match.group(0))
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/receta-detalle', methods=['POST'])
def receta_detalle():
    try:
        import anthropic
        import json as json_lib

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        receta_nombre = data.get('receta_nombre', '')
        ingredientes = data.get('ingredientes_detectados', [])
        comensales = int(data.get('comensales', 1))
        meal_prep = data.get('meal_prep', False)
        restricciones = data.get('restricciones', [])

        restricciones_str = ', '.join(restricciones) if restricciones else 'ninguna'
        porciones = comensales * 2 if meal_prep else comensales
        porciones_str = f"{porciones} porciones"
        if meal_prep:
            porciones_str += f" ({comensales} para ahora + {comensales} meal prep)"

        prompt = f"""Eres un chef y nutricionista experto.

El usuario eligió hacer: {receta_nombre}
Ingredientes disponibles: {', '.join(ingredientes)}
Porciones a preparar: {porciones_str}
Restricciones: {restricciones_str}

Genera la receta completa y detallada. Responde SOLO con este JSON:

{{
  "nombre": "{receta_nombre}",
  "porciones": {porciones},
  "tiempo_total": "25 min",
  "dificultad": "Fácil",
  "ingredientes": [
    {{"nombre": "Pechuga de pollo", "cantidad": "400", "unidad": "g"}},
    {{"nombre": "Aceite de oliva", "cantidad": "2", "unidad": "cucharadas"}}
  ],
  "pasos": [
    {{"numero": 1, "titulo": "Preparar los ingredientes", "descripcion": "Descripción clara del paso en 1-2 líneas.", "tiempo": "5 min"}},
    {{"numero": 2, "titulo": "Cocinar", "descripcion": "Descripción clara del paso.", "tiempo": "15 min"}}
  ],
  "macros_por_porcion": {{
    "calorias": 450,
    "proteina_g": 35,
    "carbohidratos_g": 40,
    "grasas_g": 12,
    "fibra_g": 5
  }},
  "macros_totales": {{
    "calorias": 900,
    "proteina_g": 70,
    "carbohidratos_g": 80,
    "grasas_g": 24
  }},
  "consejos": ["consejo 1", "consejo 2"],
  "conservacion": "Se conserva hasta 3 días en el refrigerador en recipiente hermético."
}}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': prompt}]
        )

        full_text = message.content[0].text
        import re
        json_match = re.search(r'\{[\s\S]*\}', full_text)
        if not json_match:
            return jsonify({'error': 'No se pudo procesar la respuesta'}), 500

        result = json_lib.loads(json_match.group(0))
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/menu-semanal', methods=['POST'])
def menu_semanal():
    try:
        import anthropic
        import json as json_lib

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            return jsonify({'error': 'API key no configurada'}), 500

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No se recibieron datos'}), 400

        modo = data.get('modo', 'ingredientes')
        ingredientes = data.get('ingredientes', '')
        dias = data.get('dias', ['Lunes','Martes','Miércoles','Jueves','Viernes'])
        comidas = data.get('comidas', ['Almuerzo','Cena'])
        comensales = int(data.get('comensales', 2))
        restriccion = data.get('restriccion', '')

        dias_str = ', '.join(dias)
        comidas_str = ', '.join(comidas)
        restriccion_str = restriccion or 'ninguna'

        if modo == 'ingredientes':
            contexto = f"El usuario tiene estos ingredientes: {ingredientes}. Planifica usando principalmente estos ingredientes."
        else:
            contexto = "Sugiere recetas variadas y saludables. Genera lista de compras completa."

        prompt = f"""Eres un chef y nutricionista experto.

{contexto}

Días: {dias_str} | Comidas: {comidas_str} | Comensales: {comensales} | Restricciones: {restriccion_str}

Genera un menú semanal variado y saludable. Solo nombres y macros, sin recetas detalladas.

Responde SOLO con este JSON:

{{
  "plan": [
    {{
      "dia": "Lunes",
      "comidas": [
        {{
          "tipo": "Almuerzo",
          "nombre": "Pollo al limón con arroz",
          "descripcion": "Pollo jugoso con arroz integral y vegetales salteados",
          "emoji": "🍋",
          "calorias": 450,
          "proteina_g": 35,
          "carbohidratos_g": 40,
          "grasas_g": 12,
          "tiempo_preparacion": "25 min",
          "dificultad": "Fácil"
        }}
      ]
    }}
  ],
  "lista_compras": {{
    "Proteínas": [{{"nombre": "Pechuga de pollo", "cantidad": "1.5 kg"}}],
    "Verduras y frutas": [{{"nombre": "Tomates", "cantidad": "6 unidades"}}],
    "Granos y cereales": [{{"nombre": "Arroz integral", "cantidad": "500 g"}}],
    "Lácteos": [],
    "Otros": [{{"nombre": "Aceite de oliva", "cantidad": "1 botella"}}]
  }},
  "tip_semana": "Consejo nutricional breve."
}}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=2500,
            messages=[{'role': 'user', 'content': prompt}]
        )

        full_text = message.content[0].text
        import re
        json_match = re.search(r'\{[\s\S]*\}', full_text)
        if not json_match:
            return jsonify({'error': 'No se pudo procesar la respuesta'}), 500

        raw_json = json_match.group(0)
        try:
            result = json_lib.loads(raw_json)
        except json_lib.JSONDecodeError:
            try:
                cleaned = re.sub(r',\s*([}\]])', r'\1', raw_json)
                result = json_lib.loads(cleaned)
            except json_lib.JSONDecodeError as je:
                return jsonify({'error': f'Error parseando respuesta: {str(je)}'}), 500

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
