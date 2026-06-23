"""
server.py
=========

Backend HTTP para "Modulo 1 - Practica rapida".

Este archivo expone, vía HTTP/JSON, exactamente la misma lógica que antes
corría embebida dentro de la app nativa (pywebview) en
`prueba_de_aplicacion_con_modulo1.py`. La lógica matemática NO se modifica:
se reutiliza `modulo1_backend.py` tal cual.

Por qué existe este archivo
----------------------------
GitHub Pages solo puede servir archivos estáticos (HTML/CSS/JS) — no puede
ejecutar Python. Por lo tanto, para subir la app "como página web" hace
falta separarla en dos partes:

  1. Un FRONTEND estático (index.html) que se sube a GitHub Pages.
  2. Un BACKEND con Python+SymPy (este archivo) que corre en algún servicio
     que sí ejecute Python (Render, Railway, PythonAnywhere, Fly.io, etc.)
     porque GitHub Pages no puede hacerlo.

El frontend (index.html) llama a este backend vía `fetch()` en vez de usar
`window.pywebview.api.call_api(...)`.

Cómo correrlo localmente
-------------------------
    pip install flask flask-cors
    python server.py
    # Sirve en http://127.0.0.1:8000

Cómo desplegarlo (ejemplo con Render.com, gratuito)
----------------------------------------------------
    1. Sube este archivo + modulo1_backend.py + requirements.txt a un repo.
    2. En Render: New > Web Service > conecta el repo.
    3. Build command:  pip install -r requirements.txt
    4. Start command:  gunicorn server:app
    5. Copia la URL pública que te da Render (ej. https://tu-app.onrender.com)
       y pégala en la constante BACKEND_URL al inicio del <script> de index.html.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
import traceback

from flask import Flask, jsonify, request
from flask_cors import CORS

import modulo1_backend as modulo1

APP_TITLE = "Módulo 1 – Práctica rápida"

app = Flask(__name__)
# CORS abierto: el frontend vive en otro dominio (GitHub Pages).
# Si se quiere restringir, cambiar origins=["https://tu-usuario.github.io"].
CORS(app, resources={r"/api/*": {"origins": "*"}})


def _options_payload() -> dict:
    return {
        "title": APP_TITLE,
        "topics": getattr(modulo1, "TOPICS", {}),
        "subtypes": getattr(modulo1, "SUBTYPES_BY_TOPIC", {}),
        "defaultExamSubtypes": getattr(modulo1, "DEFAULT_EXAM_SUBTYPES_BY_TOPIC", {}),
        "difficultyCategories": getattr(modulo1, "TOPIC_DIFFICULTY_CATEGORIES", {}),
        "productNotableNames": getattr(modulo1, "PRODUCT_NOTABLE_NAMES", []),
        "expandableSubtypes": list(getattr(modulo1, "EXPANDABLE_SUBTYPES", [])),
        "quickModes": [
            {"label": "Factorización", "topic": "factorizacion", "subtype": "", "description": "Todos los métodos mezclados."},
            {"label": "Ecuaciones", "topic": "ecuaciones", "subtype": "", "description": "Lineales, cuadráticas y análisis."},
            {"label": "Conversiones", "topic": "conversiones", "subtype": "", "description": "Temperatura, masa, distancia y más."},
            {"label": "Inecuaciones", "topic": "inecuaciones", "subtype": "", "description": "Lineales, cuadraticas y racionales."},
            {"label": "Valor absoluto", "topic": "valor_absoluto", "subtype": "", "description": "Ecuaciones, inecuaciones y casos multiples."},
            {"label": "Racionalización", "topic": "racionalizacion", "subtype": "", "description": "Numerador o denominador."},
            {"label": "Binomio de Newton", "topic": "binomio_newton", "subtype": "", "description": "Coeficiente, término, desarrollo y más."},
        ],
    }


@app.route("/", methods=["GET"])
def health():
    # Endpoint simple para confirmar que el backend está vivo (útil para Render/Railway health checks).
    return jsonify({"status": "ok", "service": "modulo1-backend"})


@app.route("/api/options", methods=["GET"])
def api_options():
    return jsonify({"success": True, "data": _options_payload()})


@app.route("/api/exercise", methods=["POST"])
def api_exercise():
    try:
        data = request.get_json(force=True) or {}
        topic = data.get("topic") or "factorizacion"
        subtype_raw = data.get("subtype") or None
        seed = data.get("seed") or None
        difficulty = data.get("difficulty") or None
        direction = data.get("direction") or None
        seen_fps = data.get("seen_fingerprints") or None
        subtype = subtype_raw
        if subtype_raw and ":" in subtype_raw:
            parts = subtype_raw.split(":", 1)
            subtype = parts[0] or None
            direction = parts[1] or direction

        exercise = modulo1.generate_exercise(
            topic, subtype=subtype, seed=seed,
            difficulty=difficulty, direction=direction,
            seen_fingerprints=seen_fps,
        )
        return jsonify({"success": True, "data": {"exercise": exercise}})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 200


@app.route("/api/check", methods=["POST"])
def api_check():
    try:
        data = request.get_json(force=True) or {}
        exercise = data.get("exercise")
        answer = data.get("answer", "")
        if not isinstance(exercise, dict):
            return jsonify({"success": False, "error": "Falta el ejercicio a validar."})
        result = modulo1.validate_answer(exercise, answer)
        return jsonify({"success": True, "data": {"result": result}})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 200


@app.route("/api/exam", methods=["POST"])
def api_exam():
    try:
        data = request.get_json(force=True) or {}
        topic = data.get("topic") or "factorizacion"
        quantity = int(data.get("quantity") or 5)
        subtypes = data.get("subtypes") or None
        seed = data.get("seed") or None
        difficulty = data.get("difficulty") or None
        exam = modulo1.generate_exam(topic, quantity, seed=seed, subtypes=subtypes, difficulty=difficulty)
        return jsonify({"success": True, "data": {"exam": exam}})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 200


@app.route("/api/exam/pdf", methods=["POST"])
def api_exam_pdf():
    try:
        data = request.get_json(force=True) or {}
        exam = data.get("exam")
        include_answer_key = bool(data.get("include_answer_key", True))
        if not isinstance(exam, dict):
            return jsonify({"success": False, "error": "Falta el examen a exportar."})

        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        try:
            modulo1.export_exam_pdf(exam, temp_path, include_answer_key=include_answer_key)
            with open(temp_path, "rb") as f:
                pdf_bytes = f.read()
        except Exception as e:
            return jsonify({"success": False, "error": f"Error del backend: {str(e)}"})
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        title = str(exam.get("title", "Examen"))
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "Examen"
        filename = f"{safe_name}.pdf"

        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        return jsonify({"success": True, "data": {"pdf_b64": pdf_b64, "filename": filename}})
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(exc)}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
