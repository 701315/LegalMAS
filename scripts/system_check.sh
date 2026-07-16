#!/usr/bin/env bash

echo "=========================================================="
echo "           STELOOM / LEGALMAS SYSTEM REPORT"
echo "=========================================================="

echo
echo "===== SYSTEM ====="
uname -a
echo
lsb_release -a 2>/dev/null || cat /etc/os-release

echo
echo "===== CPU ====="
lscpu | grep -E "Model name|CPU\(s\)|Thread|Core"

echo
echo "===== MEMORY ====="
free -h

echo
echo "===== GPU ====="
lspci | grep -iE "vga|3d|display|nvidia"

echo
echo "===== DISKS ====="
df -h

echo
echo "===== DOCKER ====="
docker --version
docker compose version 2>/dev/null

echo
echo "===== DOCKER CONTAINERS ====="
docker ps -a

echo
echo "===== DOCKER IMAGES ====="
docker images

echo
echo "===== DOCKER VOLUMES ====="
docker volume ls

echo
echo "===== DOCKER NETWORKS ====="
docker network ls

echo
echo "===== PYTHON ====="
python3 --version
pip3 --version

echo
echo "===== NODE ====="
node -v 2>/dev/null
npm -v 2>/dev/null

echo
echo "===== GIT ====="
git --version

echo
echo "===== OLLAMA ====="
ollama --version 2>/dev/null
ollama list 2>/dev/null

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

if [ -z "$PROJECT_ROOT" ]; then
    PROJECT_ROOT="$(pwd)"
fi

echo
echo "=========================================================="
echo "PROJECT: $PROJECT_ROOT"
echo "=========================================================="

cd "$PROJECT_ROOT"

echo
echo "===== PROJECT STRUCTURE ====="
find . -maxdepth 2 \
! -path "./.git*" \
! -path "./node_modules*" \
! -path "./venv*" \
! -path "./.venv*" \
| sort

echo
echo "===== ENV FILES ====="
find . -name ".env*" | sort

echo
echo "===== DOCKER FILES ====="
find . \( \
-name "Dockerfile" \
-o -name "docker-compose.yml" \
-o -name "docker-compose.yaml" \
-o -name "compose.yaml" \
\) | sort

echo
echo "===== DOCKER COMPOSE CONFIG ====="
docker compose config 2>/dev/null

echo
echo "===== GIT STATUS ====="
git status --short

echo
echo "===== GIT REMOTES ====="
git remote -v

echo
echo "===== BRANCH ====="
git branch --show-current

echo
echo "===== LOCAL DATABASES ====="
find . -type d \
\( \
-name "chroma" \
-o -name "chromadb" \
-o -name "qdrant" \
-o -name "postgres" \
-o -name "pgdata" \
-o -name "milvus" \
-o -name "weaviate" \
-o -name "data" \
\)

echo
echo "===== LARGE DIRECTORIES ====="
du -h --max-depth=2 . | sort -h | tail -30

echo
echo "===== RUNNING PORTS ====="
ss -tulpn | grep LISTEN

echo
echo "=========================================================="
echo "END OF REPORT"
echo "=========================================================="

