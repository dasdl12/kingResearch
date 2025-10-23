# Railway Procfile for DeerFlow Backend
# This file tells Railway how to start the application

# Release phase: Initialize database before starting the server
release: python scripts/init_railway_db.py

# Web server
web: python server.py --host 0.0.0.0 --port $PORT

