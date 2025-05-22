<h2><strong>Luis Angelo Hernandez Centti</strong></h2>

mkdir -p grafana/provisioning/datasources

create env:

python -m venv lgtmotel

source lgtmotel/bin/activate

pip install -r requirements.txt

pip install --upgrade pip

python3 app.py

mkdir tempo-data

docker-compose down -v
docker-compose up -d

docker-compose ps
