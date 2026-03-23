web: cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: cd backend && celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO
beat: cd backend && celery -A app.tasks.celery_app:celery_app beat --loglevel=INFO
