import os

# Evita dependencias del IDE y asegura que tests no requieran credenciales reales.
os.environ.setdefault("OPENAI_API_KEY", "test")
