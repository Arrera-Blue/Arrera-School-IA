FROM python:3.14.7-slim

# dépendances d'abord : cette couche est mise en cache tant que requirements.txt ne bouge pas
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# un utilisateur non privilégié : le conteneur n'a aucune raison de tourner en root
RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . .
USER app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "generateur.interface.api:app", "--host", "127.0.0.1", "--port", "8000"]

