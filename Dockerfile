# Instagram Bot — uretim imaji
FROM python:3.12-slim

# Sistem bagimliliklari (instagrapi/pillow icin gerekli olabilir)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Once bagimliliklar (katman onbellegi icin)
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama
COPY . .
RUN pip install --no-cache-dir .

# Veri (SQLite, oturumlar, loglar) kalici hacimde tutulmali
VOLUME ["/app/data"]

# Web paneli portu
EXPOSE 8787

# Varsayilan: zamanlayici daemon. Panel icin: command'i "dashboard --host 0.0.0.0" yap.
ENTRYPOINT ["igbot"]
CMD ["run"]
