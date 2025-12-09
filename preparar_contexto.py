import os

# Configuración
# Nombres de carpetas o archivos que NO queremos leer
IGNORE_DIRS = {'venv', '.venv', 'env', '.git', '__pycache__', 'node_modules', 'dist', 'build', '.idea', '.vscode'}
IGNORE_FILES = {'package-lock.json', 'yarn.lock', '.DS_Store', 'preparar_contexto.py', 'poetry.lock'}
# Extensiones que SÍ queremos leer (ajusta según tu proyecto)
ALLOWED_EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.txt', '.md', '.json', '.sh', '.yml', '.yaml', '.sql', 'Dockerfile'}

OUTPUT_FILE = 'TODO_EL_PROYECTO.txt'

def is_text_file(filename):
    return any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)

def main():
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        # Escribimos un encabezado explicativo
        outfile.write(f"--- CONTEXTO DEL PROYECTO ---\n")
        outfile.write(f"Estructura de archivos aplanada para análisis.\n\n")

        for root, dirs, files in os.walk('.'):
            # Filtrar carpetas ignoradas
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                
                if is_text_file(file):
                    file_path = os.path.join(root, file)
                    # Normalizamos la ruta para que se vea bonita
                    relative_path = os.path.relpath(file_path, '.')
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            
                            # Escribimos el delimitador y el nombre del archivo
                            outfile.write(f"\n{'='*50}\n")
                            outfile.write(f"ARCHIVO: {relative_path}\n")
                            outfile.write(f"{'='*50}\n")
                            outfile.write(content + "\n")
                            print(f"Procesado: {relative_path}")
                    except Exception as e:
                        print(f"Error leyendo {relative_path}: {e}")

    print(f"\n¡Listo! Todo el código está en '{OUTPUT_FILE}'. Sube ese archivo al chat.")

if __name__ == "__main__":
    main()