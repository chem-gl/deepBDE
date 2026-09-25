# DeepBDE Django Backend — Especificación y Plan de Acción

## Resumen

Backend Django versionado (v1) orientado únicamente a inferencia, expone una API RESTful para:

* Predicción de energías de disociación de enlaces (BDE) usando DeepBDE.
* Visualización de estructuras 2D con RDKit.
* Generación de fragmentos moleculares en SMILES o XYZ.
* Exportación de SMILES y XYZ de todos los fragmentos generados por escisión de enlaces simples (checkbox en el frontend).
* **Nuevo:** Generación de informes PDF con LaTeX (django-tex).

Este backend NO realiza entrenamiento del modelo, solo usa un modelo preentrenado integrado como submódulo.

## Estructura Recomendada

deepbde_backend/
├── DeepBDE/         # submódulo oficial
├── predictor/       # app Django con lógica de predicción
├── main.py          # punto de arranque del servidor
├── requirements.txt
├── Dockerfile
├── .env             # variables de entorno
├── tests/           # pruebas automatizadas
└── README.rst

## Requisitos

* Python ≥ 3.10 (pyenv)
* Sistema (Ubuntu/Debian): build-essential, libglib2.0-0, libsm6, libxrender1, texlive-full, latexmk
* Python (ver requirements.txt):
  - django>=4.x
  - djangorestframework
  - django-tex  # generación de PDFs con LaTeX
  - rdkit
  - torch   # o tensorflow según DeepBDE
  - numpy
  - pandas
  - pillow
  - dgl     # instalar con CUDA
  - scikit-learn
* DeepBDE: ver DeepBDE/requirements.txt
* drf-yasg (OpenAPI/Swagger)
* PyJWT (autenticación JWT)

## Instalación y Configuración dentro del mismo docker

1. Dependencias del sistema y pyenv

   sudo apt update && \
   sudo apt install -y build-essential libglib2.0-0 libsm6 libxrender1
   pyenv install 3.10.14
   pyenv local 3.10.14

2. Entorno virtual

   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -r DeepBDE/requirements.txt
   pip install dgl -f https://data.dgl.ai/wheels/torch-2.3/repo.html

3. Proyecto Django

   django-admin startproject deepbde_api .
   python manage.py startapp predictor

4. settings.py

   Añadir a INSTALLED_APPS: predictor, rest_framework
   CORS_ALLOWED_ORIGINS = [
     "http://localhost:4200"
     # Añade aquí el dominio real de tu frontend en producción, por ejemplo:
     # "https://frontend.tudominio.com"
   ]

5. Instalar TeX Live y latexmk para generación de PDFs:

   sudo apt install -y texlive-full latexmk

## Autenticación y Seguridad

* JWT en header Authorization: Bearer <token> (PyJWT)
* Rate limiting vía DRF Throttles
* Validación estricta y sanitización de entrada
* CORS restringido a dominios confiables

## Documentación OpenAPI

* Generar documentación automática con drf-yasg
* Exponer en /api/v1/docs/

## Formato de Respuesta Unificado

Todas las respuestas siguen:

```
{
  "status": "success" | "error",
  "data": { … },
  "error": {
    "code": "ERR_CODE",
    "message": "Descripción amigable"
  }
}
```

## Variables de Entorno (.env)

SECRET_KEY=…
DJANGO_ALLOWED_HOSTS=…
MODEL_PATH=…       # ruta al modelo DeepBDE
REDIS_URL=…        # si se usa caching
RATE_LIMIT=10/m    # llamadas por minuto

## Logging y Rotación

Configurar en settings.py:

* Handler de archivo con rotación por tamaño
* Niveles: DEBUG (dev), INFO (prod)

## Endpoints API v1

1. **POST /api/v1/predict/**
   * Entrada:
     ```json
     { "smiles": "CCO" }
     ```
   * Salida (`data`):
     ```json
     {
       "image": "data:image/png;base64,iVBORw0KGgo...",
       "bonds": [ { "idx": 1, "atoms": [0,1], "bde": 113.4 } ]
     }
     ```
   * Errores: `ERR_SMILES_INVALID`, `ERR_INTERNAL`

2. **POST /api/v1/predict/single/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_idx": 1 }
     ```
   * Salida (`data`):
     ```json
     { "bde": 113.7 }
     ```
   * Errores: `ERR_BOND_OUT_OF_RANGE`, `ERR_SMILES_INVALID`

3. **POST /api/v1/predict/multiple/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_indices": [1,2] }
     ```
   * Salida (`data`):
     ```json
     { "bonds": [ { "idx": 1, "bde": 112.3 }, { "idx": 2, "bde": 110.5 } ] }
     ```

4. **POST /api/v1/fragment/smiles/**
   * Entrada:
     ```json
     { "smiles": "CCO", "all_bonds": true }
     ```
   * Salida (`data`):
     ```json
     {
       "parent": "CCO",
       "fragments": ["[CH3]", "[OH]"],
       "all_fragments": [
         { "bond_idx": 0, "fragments": ["CC", "O"] },
         { "bond_idx": 1, "fragments": ["C", "CO"] }
       ]
     }
     ```

5. **POST /api/v1/fragment/xyz/**
   * Entrada:
     ```json
     { "smiles": "CCO", "all_bonds": true }
     ```
   * Salida (`data`):
     ```
     3
     
     C 0.000 0.000 0.000
     C 1.200 0.000 0.000
     O 2.400 0.000 0.000
     
     1
     
     O 0.000 0.000 0.000
     ```
     (Cada bloque XYZ separado por línea en blanco)

6. **POST /api/v1/predict/check/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_idx": 1, "products": ["[CH3]", "[OH]"] }
     ```
   * Salida (`data`):
     ```json
     { "bde": 113.7 }
     ```
   * Error:
     ```json
     {
       "status": "error",
       "data": null,
       "error": {
         "code": "ERR_PRODUCTS_MISMATCH",# DeepBDE Django Backend — Especificación y Plan de Acción

## Resumen

Backend Django versionado (v1) orientado únicamente a inferencia, expone una API RESTful para:

* Predicción de energías de disociación de enlaces (BDE) usando DeepBDE.
* Visualización de estructuras 2D con RDKit.
* Generación de fragmentos moleculares en SMILES o XYZ.
* **Nuevo:** Opciones para exportar SMILES y XYZ de todos los fragmentos generados por la escisión de enlaces simples (checkbox en el frontend).

Este backend NO realiza entrenamiento del modelo, solo usa un modelo preentrenado integrado como submódulo.

## Estructura Recomendada

deepbde_backend/
├── DeepBDE/         # submódulo oficial
├── predictor/       # app Django con lógica de predicción
├── main.py          # punto de arranque del servidor
├── requirements.txt
├── Dockerfile
├── .env             # variables de entorno
├── tests/           # pruebas automatizadas
└── README.rst

## Requisitos

* Python ≥ 3.10 (gestión de versiones con pyenv)
* Sistema (Ubuntu/Debian): build-essential, libglib2.0-0, libsm6, libxrender1
* Python (ver requirements.txt):
  - django>=4.x
  - djangorestframework
  - rdkit
  - torch   # o tensorflow según DeepBDE
  - numpy
  - pandas
  - pillow
  - dgl     # instalar con CUDA
* DeepBDE: ver DeepBDE/requirements.txt

## Instalación y Configuración dentro del mismo docker

1. Dependencias del sistema y pyenv

   sudo apt update && \
   sudo apt install -y build-essential libglib2.0-0 libsm6 libxrender1
   pyenv install 3.10.14
   pyenv local 3.10.14

2. Entorno virtual

   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -r DeepBDE/requirements.txt
   pip install dgl -f https://data.dgl.ai/wheels/torch-2.3/repo.html

3. Proyecto Django

   django-admin startproject deepbde_api .
   python manage.py startapp predictor

4. settings.py

   Añadir a INSTALLED_APPS: predictor, rest_framework
   CORS_ALLOWED_ORIGINS = [
     "http://localhost:4200"
     # Añade aquí el dominio real de tu frontend en producción, por ejemplo:
     # "https://frontend.tudominio.com"
   ]

## Formato de Respuesta Unificado

Todas las respuestas siguen:

```
{
  "status": "success" | "error",
  "data": { … },
  "error": {
    "code": "ERR_CODE",
    "message": "Descripción amigable"
  }
}
```

## Variables de Entorno (.env)

SECRET_KEY=…
DJANGO_ALLOWED_HOSTS=…
MODEL_PATH=…       # ruta al modelo DeepBDE
REDIS_URL=…        # si se usa caching
RATE_LIMIT=10/m    # llamadas por minuto

## Logging y Rotación

Configurar en settings.py:

* Handler de archivo con rotación por tamaño
* Niveles: DEBUG (dev), INFO (prod)

## Endpoints API v1

1. **POST /api/v1/predict/**
   * Entrada:
     ```json
     { "smiles": "CCO" }
     ```
   * Salida (`data`):
     ```json
     {
       "image": "data:image/png;base64,iVBORw0KGgo...",
       "bonds": [ { "idx": 1, "atoms": [0,1], "bde": 113.4 } ]
     }
     ```
   * Errores: `ERR_SMILES_INVALID`, `ERR_INTERNAL`

2. **POST /api/v1/predict/single/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_idx": 1 }
     ```
   * Salida (`data`):
     ```json
     { "bde": 113.7 }
     ```
   * Errores: `ERR_BOND_OUT_OF_RANGE`, `ERR_SMILES_INVALID`

3. **POST /api/v1/predict/multiple/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_indices": [1,2] }
     ```
   * Salida (`data`):
     ```json
     { "bonds": [ { "idx": 1, "bde": 112.3 }, { "idx": 2, "bde": 110.5 } ] }
     ```

4. **POST /api/v1/fragment/smiles/**
   * Entrada:
     ```json
     { "smiles": "CCO", "all_bonds": true }
     ```
   * Salida (`data`):
     ```json
     {
       "parent": "CCO",
       "fragments": ["[CH3]", "[OH]"],
       "all_fragments": [
         { "bond_idx": 0, "fragments": ["CC", "O"] },
         { "bond_idx": 1, "fragments": ["C", "CO"] }
       ]
     }
     ```

5. **POST /api/v1/fragment/xyz/**
   * Entrada:
     ```json
     { "smiles": "CCO", "all_bonds": true }
     ```
   * Salida (`data`):
     ```
     3
     
     C 0.000 0.000 0.000
     C 1.200 0.000 0.000
     O 2.400 0.000 0.000
     
     1
     
     O 0.000 0.000 0.000
     ```
     (Cada bloque XYZ separado por línea en blanco)

6. **POST /api/v1/predict/check/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_idx": 1, "products": ["[CH3]", "[OH]"] }
     ```
   * Salida (`data`):
     ```json
     { "bde": 113.7 }
     ```
   * Error:
     ```json
     {
       "status": "error",
       "data": null,
       "error": {
         "code": "ERR_PRODUCTS_MISMATCH",
         "message": "Los productos no corresponden al corte indicado."
       }
     }
     ```

7. **POST /api/v1/infer/all/**
   * Entrada:
     ```json
     { "smiles": "CCO" }
     ```
   * Salida (`data`):
     ```json
     { "bonds": [ { "idx": 0, "bde": 110.2 }, { "idx": 1, "bde": 112.3 } ] }
     ```

8. **GET /api/v1/info/**
   * Salida (`data`):
     ```json
     { "model_version": "v1.0.2", "arxiv": "https://arxiv.org/abs/2306.12345", "loaded_at": "2025-07-30T13:00:00Z" }
     ```

9. **GET /api/v1/status/**
   * Salida (`data`):
     ```json
     { "deepbde_submodule": "initialized", "gpu_available": true, "uptime": "2h34m" }
     ```

10. **GET /api/v1/health/**
    * Respuesta: `200 OK`

11. **GET /api/v1/metrics/**
    * Salida: métricas Prometheus

## Notas sobre fragmentación avanzada

- Los endpoints `/api/v1/fragment/smiles/` y `/api/v1/fragment/xyz/` deben soportar la opción de devolver todos los fragmentos generados por escisión de enlaces simples, tanto en formato SMILES como XYZ.
- El backend debe usar RDKit y utilidades DeepBDE para obtener los fragmentos y convertirlos a XYZ.
- El frontend puede mostrar estas opciones como checkboxes para el usuario.

## Manejo de Errores

* 400 Bad Request: SMILES inválido, JSON mal formado
* 401 Unauthorized: token JWT inválido o ausente
* 403 Forbidden: permisos insuficientes
* 404 Not Found: recurso no existe
* 422 Unprocessable Entity: índice(s) fuera de rango
* 429 Too Many Requests: rate limit excedido
* 500 Internal Server Error: fallo interno (loggear detalles)

## Ejemplo de Error

```
{
  "status": "error",
  "data": null,
  "error": {
    "code": "ERR_SMILES_INVALID",
    "message": "El SMILES proporcionado no es válido."
  }
}
```

## Plan de Acción

1. **Integración de Submódulo**
   * Inicializar y validar importación de DeepBDE.
   * Envolver `infer.py`, `multi_infer.py`, `infer_all.py` como funciones en `predictor/utils/model_runner.py`.

2. **Desarrollo de Endpoints**
   * Crear serializadores y validadores en `predictor/serializers.py`.
   * Definir rutas en `predictor/urls.py` y vistas en `predictor/views.py`.
   * Probar con `curl` o Postman, verificando esquemas y códigos de error.

3. **Seguridad y Operaciones**
   * Configurar JWT, rate limiting y CORS.
   * Asegurar variables de entorno y logging.

4. **Documentación OpenAPI**
   * Generar `schema.yaml` o `swagger.json` con drf-yasg.
   * Exponer en `/api/v1/docs/`.

5. **Dockerización y Despliegue VPS**
   * Completar `Dockerfile` e incluir submódulo.
   * Añadir `docker-compose.yml` si se utiliza Redis.
   * Desplegar con NGINX reverso y HTTPS Let’s Encrypt.

6. **Pruebas & QA**
   * Desarrollar tests unitarios e integración en `tests/`.
   * Integrar en CI (GitHub Actions o runner self-hosted).

7. **Mantenimiento & Extensión**
   * Planificar batch‑processing, caching (Redis), colas asíncronas (Celery).
   * Recoger feedback del frontend e iterar mejoras.

## Notas finales

* Aísla lógica DeepBDE en `predictor/utils/model_runner.py`.
* Usar procesos o hilos para evitar bloqueo.
* Mantener versiones sincronizadas entre submódulo y entorno.
* Incluir ejemplos de petición/respuesta en README final.

         "message": "Los productos no corresponden al corte indicado."
       }
     }
     ```

7. **POST /api/v1/infer/all/**
   * Entrada:
     ```json
     { "smiles": "CCO" }
     ```
   * Salida (`data`):
     ```json
     { "bonds": [ { "idx": 0, "bde": 110.2 }, { "idx": 1, "bde": 112.3 } ] }
     ```

8. **GET /api/v1/info/**
   * Salida (`data`):
     ```json
     { "model_version": "v1.0.2", "arxiv": "https://arxiv.org/abs/2306.12345", "loaded_at": "2025-07-30T13:00:00Z" }
     ```

9. **GET /api/v1/status/**
   * Salida (`data`):
     ```json
     { "deepbde_submodule": "initialized", "gpu_available": true, "uptime": "2h34m" }
     ```

10. **GET /api/v1/health/**
    * Respuesta: `200 OK`

11. **GET /api/v1/metrics/**
    * Salida: métricas Prometheus

12. **POST /api/v1/download_report/**
   * Entrada:
     ```json
     { "smiles": "CCO", "bond_idx": 1, "format": "pdf" }
     ```
   * Salida: PDF generado con LaTeX, descargable.
   * Errores: `ERR_REPORT_FAILED`

## Notas sobre integración DeepBDE y advertencias

* El submódulo DeepBDE debe estar correctamente clonado y accesible.
* Documenta advertencias conocidas de scikit-learn y PyTorch en el README.
* El backend debe manejar errores de importación y dependencias.

## Recomendaciones para el Frontend

* Usar RDKit.js para manipulación y visualización de moléculas en Angular.
* Recibir imágenes, SMILES y XYZ del backend y renderizarlos en el frontend.
* Implementar checkboxes para exportar todos los fragmentos SMILES/XYZ.
* Documentar ejemplos de integración en el README del frontend.

## Pruebas y QA

* Probar todos los endpoints con curl/Postman, incluyendo /api/v1/download_report/
* Desarrollar tests unitarios e integración en tests/
* Configurar CI/CD con GitHub Actions para ejecutar pytest y verificar integración

## Docker y despliegue

* El Dockerfile debe instalar TeX Live, latexmk, pyenv, venv, y clonar DeepBDE.
* Incluir configuración de .env y variables necesarias.

## Ejemplo de Error

```
{
  "status": "error",
  "data": null,
  "error": {
    "code": "ERR_SMILES_INVALID",
    "message": "El SMILES proporcionado no es válido."
  }
}
```

## Plan de Acción

1. **Integración de Submódulo**
   * Inicializar y validar importación de DeepBDE.
   * Envolver `infer.py`, `multi_infer.py`, `infer_all.py` como funciones en `predictor/utils/model_runner.py`.

2. **Desarrollo de Endpoints**
   * Crear serializadores y validadores en `predictor/serializers.py`.
   * Definir rutas en `predictor/urls.py` y vistas en `predictor/views.py`.
   * Probar con `curl` o Postman, verificando esquemas y códigos de error.

3. **Seguridad y Operaciones**
   * Configurar JWT, rate limiting y CORS.
   * Asegurar variables de entorno y logging.

4. **Documentación OpenAPI**
   * Generar `schema.yaml` o `swagger.json` con drf-yasg.
   * Exponer en `/api/v1/docs/`.

5. **Dockerización y Despliegue VPS**
   * Completar `Dockerfile` e incluir submódulo.
   * Añadir `docker-compose.yml` si se utiliza Redis.
   * Desplegar con NGINX reverso y HTTPS Let’s Encrypt.

6. **Pruebas & QA**
   * Desarrollar tests unitarios e integración en `tests/`.
   * Integrar en CI (GitHub Actions o runner self-hosted).

7. **Mantenimiento & Extensión**
   * Planificar batch‑processing, caching (Redis), colas asíncronas (Celery).
   * Recoger feedback del frontend e iterar mejoras.

## Notas finales

* Aísla lógica DeepBDE en `predictor/utils/model_runner.py`.
* Usar procesos o hilos para evitar bloqueo.
* Mantener versiones sincronizadas entre submódulo y entorno.
* Incluir ejemplos de petición/respuesta en README final.
* Documentar advertencias y dependencias en README.
* Documentar integración RDKit.js y frontend en README
