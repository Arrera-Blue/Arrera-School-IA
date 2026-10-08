# 1. llama-cpp-python, compilé pour le processeur de la machine qui construit l'image (GGML_NATIVE) : sur le VPS,
#    les instructions AVX2/AVX-512 de ses vCPU. Les outils de compilation restent dans cette étape.
#    Une image construite ainsi ne convient qu'à des processeurs de la même famille : sur un autre poste
#    (PC enseignant), la reconstruire sur place.
FROM python:3.14.7-slim AS llama
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
RUN CMAKE_ARGS="-DGGML_NATIVE=ON" pip wheel --no-cache-dir --no-deps --wheel-dir /roues llama-cpp-python==0.3.36

# 2. l'image du générateur
FROM python:3.14.7-slim

# OpenMP : llama.cpp répartit le calcul sur les cœurs avec lui
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# dépendances d'abord : cette couche est mise en cache tant que requirements.txt ne bouge pas ;
# llama-cpp-python vient de la roue compilée à l'étape 1 (PyPI n'en fournit que les sources)
WORKDIR /app
COPY --from=llama /roues /roues
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --find-links /roues -r requirements.txt \
    && rm -rf /roues

# un utilisateur non privilégié : le conteneur n'a aucune raison de tourner en root
RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . .
USER app

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "generateur.interface.api:app", "--host", "127.0.0.1", "--port", "8000"]
