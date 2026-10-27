"""Configuracao de conexao com os dois bancos (docker-compose)."""

PG_DSN = "host=localhost port=5432 dbname=dac2pc user=dac password=dac123"
MONGO_URI = "mongodb://localhost:27017/?directConnection=true"
MONGO_DB = "dac2pc"
