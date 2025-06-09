import os
from datetime import datetime
from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

def generar_pdf_reportes(personas, matriculas):
    """
    Crea un PDF con detalle de personas y matrículas seleccionadas.
    Devuelve la ruta relativa (desde MEDIA_ROOT) del PDF generado.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_dir = os.path.join(settings.MEDIA_ROOT, 'utilidades', 'pdf')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_name = f"pdf_{timestamp}.pdf"
    pdf_path = os.path.join(pdf_dir, pdf_name)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    y = height - 40

    # --- Sección Personas ---
    if personas:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Personas Seleccionadas")
        y -= 30
        for p in personas:
            # Foto principal
            if p.foto_principal:
                img_path = os.path.join(settings.MEDIA_ROOT, p.foto_principal.name)
                try:
                    img = ImageReader(img_path)
                    c.drawImage(img, 50, y-80, width=100, height=100, preserveAspectRatio=True)
                except Exception:
                    pass
            # Texto con datos
            text = c.beginText(160, y)
            text.setFont("Helvetica", 12)
            text.textLine(f"Nombre: {p.nombre} {p.apellidos}")
            text.textLine(f"DNI: {p.dni}")
            text.textLine(f"Nac.: {p.fecha_nacimiento}   Sexo: {p.sexo}")
            text.textLine(f"Nacionalidad: {p.nacionalidad}")
            text.textLine(f"En busca y captura: {'Sí' if p.en_busca_captura else 'No'}")
            c.drawText(text)
            y -= 120
            if y < 120:
                c.showPage()
                y = height - 40

    # --- Sección Matrículas ---
    if matriculas:
        c.showPage()
        y = height - 40
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Matrículas Seleccionadas")
        y -= 30
        for m in matriculas:
            text = c.beginText(50, y)
            text.setFont("Helvetica", 12)
            text.textLine(f"Número: {m.numero}")
            text.textLine(f"País: {m.pais}")
            text.textLine(f"Robado: {'Sí' if m.esta_robado else 'No'}")
            text.textLine(f"Delitos: {m.delitos or '—'}")
            text.textLine(
                "Propietarios: " +
                (", ".join(str(p) for p in m.propietarios.all()) or "—")
            )
            text.textLine(f"Creada: {m.fecha_creacion}   Última vez vista: {m.ultima_vez_vista}")
            c.drawText(text)
            y -= 110
            if y < 120:
                c.showPage()
                y = height - 40

    c.save()
    # ruta relativa
    return os.path.relpath(pdf_path, settings.MEDIA_ROOT)
