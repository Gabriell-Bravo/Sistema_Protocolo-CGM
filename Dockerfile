FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Dependências do sistema. GDAL/PROJ/binutils saíram: o projeto não usa
# GeoDjango, e eles aumentavam a imagem em centenas de MB.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar e instalar dependências Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar o código da aplicação
COPY . /app/

# Criar diretórios necessários
RUN mkdir -p /app/staticfiles_build /app/mediafiles

EXPOSE 8800

CMD ["gunicorn", "--bind", "0.0.0.0:8800", "protocolo_project.wsgi:application"]