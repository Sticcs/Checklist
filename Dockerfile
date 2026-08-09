# --- Stage 1: build the React frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime serving the API + the built frontend ---
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend-build /frontend/dist frontend/dist

# main.py's FRONTEND_DIST resolves to ../../frontend/dist relative to
# backend/app/main.py, i.e. /app/frontend/dist - matches the layout above.
WORKDIR /app/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
