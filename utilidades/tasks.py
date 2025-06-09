# utilidades/tasks.py

import os
import csv
from datetime import datetime
from pathlib import Path

from celery import shared_task
from django.conf import settings

from .models import BulkCheck, Report, SearchHistory


@shared_task(bind=True)
def bulk_check_task(self, bulkcheck_id):
    """
    Toma un BulkCheck, lee su input_file (CSV con una columna 'value'),
    para cada fila añade una columna 'result' indicando True/False según
    exista la matrícula o persona marcada como robada/en busca,
    y escribe un CSV de salida asignándolo a result_file.
    """
    bc = BulkCheck.objects.get(pk=bulkcheck_id)
    input_path = Path(settings.MEDIA_ROOT) / bc.input_file.name
    output_name = f"result_{input_path.stem}.csv"
    output_dir = Path(settings.MEDIA_ROOT) / "checks" / datetime.now().strftime("%Y/%m/%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name

    # Definir header de salida igual al de entrada + 'result'
    with open(input_path, newline='', encoding='utf-8') as fin, \
         open(output_path, 'w', newline='', encoding='utf-8') as fout:

        reader = csv.reader(fin)
        writer = csv.writer(fout)

        headers = next(reader, None)
        if headers:
            writer.writerow(headers + ['result'])
        else:
            # si no hay cabecera, asumimos una sola columna
            writer.writerow(['value', 'result'])

        for row in reader:
            value = row[0].strip()
            if bc.check_type == 'matricula':
                from matriculas.models import Matricula
                exists = Matricula.objects.filter(numero=value, esta_robado=True).exists()
            else:  # 'persona'
                from personas.models import Persona
                exists = Persona.objects.filter(dni=value, en_busca_captura=True).exists()

            writer.writerow(row + [str(exists)])

    # Guardar resultado en el modelo
    rel_path = output_path.relative_to(settings.MEDIA_ROOT)
    bc.result_file.name = str(rel_path)
    bc.save()
    return {'result_file': bc.result_file.name}

