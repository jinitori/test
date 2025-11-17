# Base 이미지
FROM python:3.10-slim

# 필수 패키지 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 작업폴더
WORKDIR /app

# 파일 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Flask는 $PORT 로 실행해야 함
ENV PORT=8080

# Flask 실행
CMD ["python", "main.py"]
