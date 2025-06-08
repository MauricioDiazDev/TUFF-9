#!/bin/bash
#
# Genera la estructura de carpetas de tu proyecto,
# omitiendo el directorio “venv” y mostrando solo carpetas y archivos .py.
#
# Úsalo ejecutando:
#   chmod +x mostrar_estructura.sh
#   ./mostrar_estructura.sh
#
# (Debe ejecutarse desde la raíz de tu proyecto.)

find . \
  -path "./venv" -prune -o \
  -type d -print -o \
  -type f -name "*.py" -print | \
  # Elimina el prefijo “./” y aplica identación según niveles
  sed 's|^\./||' | \
  awk -F/ '{
    indent = ""
    for (i = 1; i < NF; i++) indent = indent "    "
    print indent $NF
  }'