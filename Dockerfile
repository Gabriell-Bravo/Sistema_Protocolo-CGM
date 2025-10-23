FROM python:3.11-slim-buster

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt \
&& pip list # Adicionado para debug: mostra o que foi instalado




COPY . /app/ 

EXPOSE 8800

CMD ["gunicorn", "--bind", "0.0.0.0:8800", "protocolo_project.wsgi:application"]