#!/bin/bash
set -e

export PYTHONPATH=/app/deepbde:$PYTHONPATH

# Export OpenAPI YAML to public folder before starting the server
python manage.py spectacular --file api/public/openapi.yaml

# Run migrations
python manage.py migrate

# Start the server
python manage.py runserver 0.0.0.0:8000